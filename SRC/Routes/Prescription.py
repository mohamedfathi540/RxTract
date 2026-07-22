from fastapi import APIRouter, Depends, UploadFile, status, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
import os
import tempfile
import logging
from Helpers.Config import get_settings, settings
from Utils.sse_helpers import progress_event, result_event, error_event
from Controllers.PrescriptionController import PrescriptionController
from Controllers.NLPController import NLPController
from Models.enums.ResponsEnums import ResponseSignal
from Models.Project_Model import projectModel
from Models.Chunk_Model import ChunkModel
from Models.Asset_Model import AssetModel
from Models.DB_Schemes import dataChunk, Asset, Project
from Models.enums.AssetTypeEnum import assettypeEnum
from Stores.LLM.LLMEnums import DocumentTypeEnum
from Controllers.SecurityController import limiter, config_limit, SecurityController

logger = logging.getLogger("uvicorn.error")

prescription_router = APIRouter(
    prefix="/api/v1/prescription",
    tags=["api_v1", "prescription"],
)

public_prescription_router = APIRouter(
    prefix="/api/v1",
    tags=["api_v1", "public", "extract"],
)

# Allowed image types for prescription uploads
ALLOWED_IMAGE_TYPES = [
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/pdf",
]


class PrescriptionChatRequest(BaseModel):
    text: str
    limit: Optional[int] = 5
    project_id: int

class RenameRequest(BaseModel):
    title: str



@prescription_router.post("/analyze")
@limiter.limit(config_limit("RATE_LIMIT_PRESCRIPTION"))
async def analyze_prescription(request: Request, file: UploadFile,
                               user=Depends(SecurityController.require_quota("prescription"))):
    """
    Upload a prescription image, perform OCR, extract medicine names,
    and push the results into a NEW project in the RAG system.

    Returns the project_id so the frontend can use it for chat.
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": ResponseSignal.FILE_TYPE_NOT_SUPPORTED.value,
                "error": f"Unsupported file type: {file.content_type}. "
                         f"Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
            },
        )

    # Save uploaded file to persistent storage
    suffix = os.path.splitext(file.filename or "upload.jpg")[-1]
    import uuid
    filename = f"{uuid.uuid4().hex}{suffix}"
    UPLOAD_DIR = "/srv/dev-disk-by-uuid-e6e20b12-66d3-46ae-b011-1613226205a5/rxtract_uploads"
    file_path = os.path.join(UPLOAD_DIR, "prescriptions", filename)
    image_url = f"/api/v1/uploads/prescriptions/{filename}"

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # Run OCR pipeline
        controller = PrescriptionController(
            correction_ctrl=getattr(request.app, "correction_ctrl", None),
        )
        result = await controller.analyze_prescription(
            file_path=file_path,
            genration_client=request.app.genration_client,
            ocr_client=getattr(request.app, "ocr_client", None),
        )

        medicines = result.get("medicines", [])
        ocr_text = result.get("ocr_text", "")
        doctor_specialty = result.get("doctor_specialty", "Unknown")

        if not medicines:
            signal = ResponseSignal.PRESCRIPTION_NO_MEDICINES_FOUND.value
            return JSONResponse(
                content={
                    "signal": signal,
                    "doctor_specialty": doctor_specialty,
                    "ocr_text": ocr_text,
                    "medicines": [],
                    "project_id": None,
                }
            )

        # ── Create a new project for this analysis ──────────────
        project_model = await projectModel.create_instance(
            db_client=request.app.db_client
        )
        
        med_names = [m["name"] for m in medicines if "name" in m]
        if med_names:
            title = ", ".join(med_names[:3])
            if len(med_names) > 3:
                title += f" +{len(med_names) - 3} more"
        else:
            title = "New Prescription"
            
        new_project = await project_model.create_project(Project(title=title, user_id=user.id))
        pid = new_project.project_id
        logger.info("Created prescription project_id=%d", pid)

        # ── Create a virtual asset for the prescription ─────────
        asset_model = await AssetModel.create_instance(
            db_client=request.app.db_client
        )
        asset_record = await asset_model.create_asset(
            Asset(
                asset_project_id=pid,
                asset_type=assettypeEnum.PRESCRIPTION.value,
                asset_name=f"prescription_{pid}",
                asset_size=len(content),
                asset_config={"image_url": image_url},
            )
        )
        asset_id = asset_record.asset_id

        # ── Build text chunks from each medicine ────────────────
        chunk_records = []
        for i, med in enumerate(medicines):
            chunk_text = (
                f"Medicine: {med['name']}\n"
                f"Active Ingredient: {med.get('active_ingredient', 'Unknown')}\n"
                f"Dosage: {med.get('dosage', 'Unknown')}\n"
                f"Form: {med.get('form', 'Unknown')}\n"
            )
            chunk_records.append(
                dataChunk(
                    chunk_text=chunk_text,
                    chunk_metadata={
                        "source": "prescription_ocr",
                        "medicine_name": med["name"],
                        "active_ingredient": med.get("active_ingredient", "Unknown"),
                        "dosage": med.get("dosage", "Unknown"),
                        "form": med.get("form", "Unknown"),
                        "image_url": med.get("image_url", ""),
                        "product_url": med.get("product_url", ""),
                        "price": med.get("price", ""),
                        "candidates": med.get("candidates", []),
                    },
                    chunk_order=i + 1,
                    chunk_project_id=pid,
                    chunk_asset_id=asset_id,
                )
            )

        # Insert chunks into database
        chunk_model = await ChunkModel.create_instance(
            db_client=request.app.db_client
        )
        await chunk_model.insert_many_chunks(chunks=chunk_records)

        # ── Embed & index into VectorDB ─────────────────────────
        nlp_controller = NLPController(
            genration_client=request.app.genration_client,
            embedding_client=request.app.embedding_client,
            vectordb_client=request.app.vectordb_client,
            template_parser=request.app.template_parser,
        )

        # Reload chunks from DB (they now have IDs)
        db_chunks = await chunk_model.get_project_chunks(
            project_id=pid, page_no=1, page_size=500
        )

        if db_chunks:
            chunks_ids = [c.chunk_id for c in db_chunks]
            is_inserted, error_msg = await nlp_controller.index_into_vector_db(
                project=new_project, chunks=db_chunks, chunks_ids=chunks_ids,
                do_reset=True,
            )
            if not is_inserted:
                logger.error("Failed to index prescription chunks: %s", error_msg)
            else:
                logger.info(
                    "Indexed %d prescription chunks into project %d",
                    len(db_chunks), pid,
                )

        return JSONResponse(
            content={
                "signal": ResponseSignal.PRESCRIPTION_ANALYZED.value,
                "doctor_specialty": doctor_specialty,
                "ocr_text": ocr_text,
                "medicines": medicines,
                "project_id": pid,
            }
        )

    except Exception as e:
        logger.error("Error analyzing prescription: %s", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "signal": ResponseSignal.PRESCRIPTION_OCR_FAILED.value,
                "error": str(e),
            },
        )

    finally:
        pass # File is kept persistently

@prescription_router.post("/analyze-stream")
@limiter.limit(config_limit("RATE_LIMIT_PRESCRIPTION"))
async def analyze_prescription_stream(request: Request, file: UploadFile,
                                      user=Depends(SecurityController.require_quota("prescription"))):
    """
    Upload a prescription image and stream real-time progress via SSE.
    Each pipeline step sends a progress event, and the final result
    is sent at the end.
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        async def error_gen():
            yield error_event(
                f"Unsupported file type: {file.content_type}. "
                f"Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
            )
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # Read file content BEFORE entering the generator
    content = await file.read()
    suffix = os.path.splitext(file.filename or "upload.jpg")[-1]
    import uuid
    filename = f"{uuid.uuid4().hex}{suffix}"
    UPLOAD_DIR = "/srv/dev-disk-by-uuid-e6e20b12-66d3-46ae-b011-1613226205a5/rxtract_uploads"
    file_path = os.path.join(UPLOAD_DIR, "prescriptions", filename)
    image_url = f"/api/v1/uploads/prescriptions/{filename}"

    async def event_generator():
        try:
            # ── Step 1: Save uploaded file ──────────────────────────
            yield progress_event("upload", "Receiving image...", 5)

            with open(file_path, "wb") as f:
                f.write(content)

            yield progress_event("upload", "Image received", 10)

            # ── Steps 2-4: OCR pipeline (with progress callbacks) ──
            controller = PrescriptionController(
                correction_ctrl=getattr(request.app, "correction_ctrl", None),
            )

            # We use a queue to collect progress events from the controller callback
            progress_queue = asyncio.Queue()

            async def on_progress_cb(step, detail, percent):
                await progress_queue.put(progress_event(step, detail, percent))

            # Run the OCR pipeline in a background task
            pipeline_task = asyncio.create_task(
                controller.analyze_prescription(
                    file_path=file_path,
                    genration_client=request.app.genration_client,
                    ocr_client=getattr(request.app, "ocr_client", None),
                    on_progress=on_progress_cb,
                )
            )

            # Drain progress events while the pipeline runs
            while not pipeline_task.done():
                try:
                    event = await asyncio.wait_for(progress_queue.get(), timeout=0.3)
                    yield event
                except asyncio.TimeoutError:
                    pass

            # Drain any remaining events in the queue
            while not progress_queue.empty():
                yield await progress_queue.get()

            result = pipeline_task.result()

            medicines = result.get("medicines", [])
            ocr_text = result.get("ocr_text", "")
            doctor_specialty = result.get("doctor_specialty", "Unknown")

            if not medicines:
                signal = ResponseSignal.PRESCRIPTION_NO_MEDICINES_FOUND.value
                yield result_event({
                    "signal": signal,
                    "doctor_specialty": doctor_specialty,
                    "ocr_text": ocr_text,
                    "medicines": [],
                    "project_id": None,
                })
                return

            # ── Step 5: Create project & index ──────────────────────
            yield progress_event("indexing", "Saving results & indexing for chat...", 80)

            project_model = await projectModel.create_instance(
                db_client=request.app.db_client
            )
            
            med_names = [m["name"] for m in medicines if "name" in m]
            if med_names:
                title = ", ".join(med_names[:3])
                if len(med_names) > 3:
                    title += f" +{len(med_names) - 3} more"
            else:
                title = "New Prescription"
                
            new_project = await project_model.create_project(Project(title=title, user_id=user.id))
            pid = new_project.project_id
            logger.info("Created prescription project_id=%d", pid)

            asset_model = await AssetModel.create_instance(
                db_client=request.app.db_client
            )
            asset_record = await asset_model.create_asset(
                Asset(
                    asset_project_id=pid,
                    asset_type=assettypeEnum.PRESCRIPTION.value,
                    asset_name=f"prescription_{pid}",
                    asset_size=len(content),
                    asset_config={"image_url": image_url},
                )
            )
            asset_id = asset_record.asset_id

            chunk_records = []
            for i, med in enumerate(medicines):
                chunk_text = (
                    f"Medicine: {med['name']}\n"
                    f"Active Ingredient: {med.get('active_ingredient', 'Unknown')}\n"
                    f"Dosage: {med.get('dosage', 'Unknown')}\n"
                    f"Form: {med.get('form', 'Unknown')}\n"
                )
                chunk_records.append(
                    dataChunk(
                        chunk_text=chunk_text,
                        chunk_metadata={
                            "source": "prescription_ocr",
                            "medicine_name": med["name"],
                            "active_ingredient": med.get("active_ingredient", "Unknown"),
                            "dosage": med.get("dosage", "Unknown"),
                            "form": med.get("form", "Unknown"),
                            "image_url": med.get("image_url", ""),
                            "product_url": med.get("product_url", ""),
                            "price": med.get("price", ""),
                            "candidates": med.get("candidates", []),
                        },
                        chunk_order=i + 1,
                        chunk_project_id=pid,
                        chunk_asset_id=asset_id,
                    )
                )

            chunk_model = await ChunkModel.create_instance(
                db_client=request.app.db_client
            )
            await chunk_model.insert_many_chunks(chunks=chunk_records)

            yield progress_event("indexing", "Building vector index...", 90)

            nlp_controller = NLPController(
                genration_client=request.app.genration_client,
                embedding_client=request.app.embedding_client,
                vectordb_client=request.app.vectordb_client,
                template_parser=request.app.template_parser,
            )

            db_chunks = await chunk_model.get_project_chunks(
                project_id=pid, page_no=1, page_size=500
            )

            if db_chunks:
                chunks_ids = [c.chunk_id for c in db_chunks]
                is_inserted, error_msg = await nlp_controller.index_into_vector_db(
                    project=new_project, chunks=db_chunks, chunks_ids=chunks_ids,
                    do_reset=True,
                )
                if not is_inserted:
                    logger.error("Failed to index prescription chunks: %s", error_msg)
                else:
                    logger.info(
                        "Indexed %d prescription chunks into project %d",
                        len(db_chunks), pid,
                    )

            yield progress_event("complete", "Analysis complete!", 100)
            yield result_event({
                "signal": ResponseSignal.PRESCRIPTION_ANALYZED.value,
                "doctor_specialty": doctor_specialty,
                "ocr_text": ocr_text,
                "medicines": medicines,
                "project_id": pid,
            })

        except Exception as e:
            logger.error("Error in analyze-stream: %s", e, exc_info=True)
            yield error_event(str(e))

        finally:
            pass # File is kept persistently

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



@prescription_router.post("/chat")
@limiter.limit(config_limit("RATE_LIMIT_QUERY"))
async def prescription_chat(request: Request, chat_request: PrescriptionChatRequest,
                            user=Depends(SecurityController.require_quota("query"))):
    """
    Chat about a specific prescription analysis.
    Uses the RAG system scoped to the project_id created from analyze.
    """
    # ── Prompt Guard: validate input ──
    is_safe, reason = SecurityController.validate_input(chat_request.text)
    if not is_safe:
        logger.warning("Prompt injection blocked: %s", reason)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"Signal": "PROMPT_INJECTION_BLOCKED", "Reason": reason},
        )

    pid = chat_request.project_id

    # Validate the project exists
    project_model = await projectModel.create_instance(
        db_client=request.app.db_client
    )

    async with request.app.db_client() as session:
        from sqlalchemy.future import select as sa_select
        result = await session.execute(
            sa_select(Project).where(Project.project_id == pid)
        )
        project = result.scalar_one_or_none()

    if not project:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"Signal": ResponseSignal.PROJECT_NOT_FOUND.value},
        )

    nlp_controller = NLPController(
        genration_client=request.app.genration_client,
        embedding_client=request.app.embedding_client,
        vectordb_client=request.app.vectordb_client,
        template_parser=request.app.template_parser,
    )

    answer, full_prompt, chat_history = await nlp_controller.answer_prescription_question(
        project=project,
        query=chat_request.text,
        limit=chat_request.limit,
    )

    if not answer:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"Signal": ResponseSignal.ANSWER_INDEX_ERROR.value},
        )

    # ── Prompt Guard: validate output ──
    output_safe, output_reason = SecurityController.validate_output(answer)
    if not output_safe:
        logger.warning("Output leak blocked: %s", output_reason)
        answer = "I can only help with questions about your prescription and medicines."

    return JSONResponse(
        content={
            "Signal": ResponseSignal.ANSWER_INDEX_DONE.value,
            "Answer": answer,
            "FullPrompt": full_prompt,
            "ChatHistory": chat_history,
        }
    )


@prescription_router.post("/chat-stream")
@limiter.limit(config_limit("RATE_LIMIT_QUERY"))
async def prescription_chat_stream(
    request: Request,
    chat_request: PrescriptionChatRequest,
    user=Depends(SecurityController.require_quota("query")),
):
    """
    Streaming variant of /chat — returns the LLM answer word-by-word via SSE.

    SSE event format:
        data: {"type": "chunk",  "content": "<word> "}
        data: {"type": "done"}
        data: {"type": "error",  "message": "<reason>"}

    Note: The answer is currently computed in full before streaming begins
    (simulated streaming).  To swap to real token-level streaming, replace the
    word-split loop below with async iteration over the LLM's stream response.
    """
    import json

    # ── Prompt Guard: validate input ──────────────────────────────────────────
    is_safe, reason = SecurityController.validate_input(chat_request.text)
    if not is_safe:
        logger.warning("Prompt injection blocked in /chat-stream: %s", reason)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"Signal": "PROMPT_INJECTION_BLOCKED", "Reason": reason},
        )

    pid = chat_request.project_id

    # ── Validate project exists ───────────────────────────────────────────────
    async with request.app.db_client() as session:
        from sqlalchemy.future import select as sa_select
        result = await session.execute(
            sa_select(Project).where(Project.project_id == pid)
        )
        project = result.scalar_one_or_none()

    if not project:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"Signal": ResponseSignal.PROJECT_NOT_FOUND.value},
        )

    async def generate():
        try:
            nlp_controller = NLPController(
                genration_client=request.app.genration_client,
                embedding_client=request.app.embedding_client,
                vectordb_client=request.app.vectordb_client,
                template_parser=request.app.template_parser,
            )

            answer, _, _ = await nlp_controller.answer_prescription_question(
                project=project,
                query=chat_request.text,
                limit=chat_request.limit,
            )

            if not answer:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No answer could be generated.'})}\n\n"
                return

            # ── Output Guard ──────────────────────────────────────────────────
            output_safe, output_reason = SecurityController.validate_output(answer)
            if not output_safe:
                logger.warning("Output leak blocked in /chat-stream: %s", output_reason)
                answer = "I can only help with questions about your prescription and medicines."

            # ── Simulated word-by-word stream ─────────────────────────────────
            # TODO: replace with real token-level streaming once LLM provider
            #       supports async token iteration (e.g. Gemini streaming API).
            words = answer.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error("Error in /chat-stream: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'An unexpected error occurred.'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@prescription_router.get("/history")
async def get_history(request: Request, user=Depends(SecurityController.get_current_user)):
    from Services.PrescriptionDBService import PrescriptionDBService
    db_service = PrescriptionDBService(request.app.db_client)
    # Pass user.id if available, otherwise just something
    user_id = user.id if hasattr(user, "id") else 0
    history = await db_service.get_history(user_id=user_id)
    return JSONResponse(content={"signal": "SUCCESS", "history": history})

@prescription_router.patch("/{project_id}/rename")
async def rename_prescription(project_id: str, payload: RenameRequest, request: Request, user=Depends(SecurityController.get_current_user)):
    from Services.PrescriptionDBService import PrescriptionDBService
    db_service = PrescriptionDBService(request.app.db_client)
    user_id = user.id if hasattr(user, "id") else None
    success = await db_service.rename_prescription(project_id, payload.title, user_id=user_id)
    if success:
        return JSONResponse(content={"signal": "SUCCESS"})
    return JSONResponse(status_code=404, content={"signal": "NOT_FOUND"})

@prescription_router.patch("/{project_id}/pin")
async def toggle_pin(project_id: str, request: Request, user=Depends(SecurityController.get_current_user)):
    from Services.PrescriptionDBService import PrescriptionDBService
    db_service = PrescriptionDBService(request.app.db_client)
    user_id = user.id if hasattr(user, "id") else None
    is_pinned = await db_service.toggle_pin(project_id, user_id=user_id)
    return JSONResponse(content={"signal": "SUCCESS", "is_pinned": is_pinned})

@prescription_router.delete("/{project_id}")
async def delete_prescription(project_id: str, request: Request, user=Depends(SecurityController.get_current_user)):
    from Services.PrescriptionDBService import PrescriptionDBService
    db_service = PrescriptionDBService(request.app.db_client)
    user_id = user.id if hasattr(user, "id") else None
    success = await db_service.soft_delete(project_id, user_id=user_id)
    if success:
        return JSONResponse(content={"signal": "SUCCESS"})
    return JSONResponse(status_code=404, content={"signal": "NOT_FOUND"})

@prescription_router.get("/{project_id}")
async def get_prescription(project_id: str, request: Request, user=Depends(SecurityController.get_current_user)):
    from Services.PrescriptionDBService import PrescriptionDBService
    db_service = PrescriptionDBService(request.app.db_client)
    data = await db_service.get_prescription(project_id)
    if not data or not data.get("medicines"):
        return JSONResponse(status_code=404, content={"signal": "NOT_FOUND"})
    return JSONResponse(content={
        "signal": "SUCCESS",
        "doctor_specialty": "Unknown", # Not stored explicitly in data chunks
        "ocr_text": data["ocr_text"],
        "medicines": data["medicines"],
        "image_url": data.get("image_url"),
        "project_id": int(project_id) if project_id.isdigit() else project_id
    })

@prescription_router.post("/{project_id}/share")
async def share_prescription(project_id: str, request: Request, user=Depends(SecurityController.get_current_user)):
    from Services.PrescriptionDBService import PrescriptionDBService
    db_service = PrescriptionDBService(request.app.db_client)
    user_id = user.id if hasattr(user, "id") else None
    token = await db_service.generate_share_token(project_id, user_id=user_id)
    if token:
        # Construct share URL based on frontend origin if available, or just return token
        return JSONResponse(content={"signal": "SUCCESS", "share_token": token})
    return JSONResponse(status_code=404, content={"signal": "NOT_FOUND"})


# ==============================================================================
# Public API-as-a-Service Endpoints
# ==============================================================================

@public_prescription_router.post("/extract")
@limiter.limit(config_limit("RATE_LIMIT_API"))
async def extract_prescription(
    request: Request,
    file: UploadFile,
    user=Depends(SecurityController.require_api_quota())
):
    """
    Public API endpoint to extract medicines from a prescription image.
    Secured by X-API-Key header.
    Returns only JSON (no project_id).
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": ResponseSignal.FILE_TYPE_NOT_SUPPORTED.value,
                "error": f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
            },
        )

    # Save uploaded file
    suffix = os.path.splitext(file.filename or "upload.jpg")[-1]
    import uuid
    filename = f"{uuid.uuid4().hex}{suffix}"
    UPLOAD_DIR = "/srv/dev-disk-by-uuid-e6e20b12-66d3-46ae-b011-1613226205a5/rxtract_uploads"
    file_path = os.path.join(UPLOAD_DIR, "prescriptions", filename)
    image_url = f"/api/v1/uploads/prescriptions/{filename}"

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # Run OCR pipeline
        controller = PrescriptionController(
            correction_ctrl=getattr(request.app, "correction_ctrl", None),
        )
        result = await controller.analyze_prescription(
            file_path=file_path,
            genration_client=request.app.genration_client,
            ocr_client=getattr(request.app, "ocr_client", None),
        )

        medicines = result.get("medicines", [])
        ocr_text = result.get("ocr_text", "")
        doctor_specialty = result.get("doctor_specialty", "Unknown")

        if not medicines:
            return JSONResponse(
                content={
                    "doctor_specialty": doctor_specialty,
                    "ocr_text": ocr_text,
                    "medicines": [],
                }
            )

        # Create project and index it (Full mode) so the consumer's user can chat later
        project_model = await projectModel.create_instance(db_client=request.app.db_client)
        med_names = [m["name"] for m in medicines if "name" in m]
        title = (", ".join(med_names[:3]) + (f" +{len(med_names) - 3} more" if len(med_names) > 3 else "")) if med_names else "API Prescription"
        
        new_project = await project_model.create_project(Project(title=title, user_id=user.id))
        pid = new_project.project_id

        asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
        asset_record = await asset_model.create_asset(Asset(
            asset_project_id=pid,
            asset_type=assettypeEnum.PRESCRIPTION.value,
            asset_name=f"prescription_{pid}",
            asset_size=len(content),
            asset_config={"image_url": image_url},
        ))
        asset_id = asset_record.asset_id

        chunk_records = []
        for i, med in enumerate(medicines):
            chunk_text = (
                f"Medicine: {med['name']}\\n"
                f"Active Ingredient: {med.get('active_ingredient', 'Unknown')}\\n"
                f"Dosage: {med.get('dosage', 'Unknown')}\\n"
                f"Form: {med.get('form', 'Unknown')}\\n"
            )
            chunk_records.append(dataChunk(
                chunk_text=chunk_text,
                chunk_metadata={
                    "source": "prescription_ocr",
                    "medicine_name": med["name"],
                    "active_ingredient": med.get("active_ingredient", "Unknown"),
                    "dosage": med.get("dosage", "Unknown"),
                    "form": med.get("form", "Unknown"),
                    "image_url": med.get("image_url", ""),
                    "product_url": med.get("product_url", ""),
                    "price": med.get("price", ""),
                    "candidates": med.get("candidates", []),
                },
                chunk_order=i + 1,
                chunk_project_id=pid,
                chunk_asset_id=asset_id,
            ))

        chunk_model = await ChunkModel.create_instance(db_client=request.app.db_client)
        await chunk_model.insert_many_chunks(chunks=chunk_records)

        nlp_controller = NLPController(
            genration_client=request.app.genration_client,
            embedding_client=request.app.embedding_client,
            vectordb_client=request.app.vectordb_client,
            template_parser=request.app.template_parser,
        )

        db_chunks = await chunk_model.get_project_chunks(project_id=pid, page_no=1, page_size=500)
        if db_chunks:
            chunks_ids = [c.chunk_id for c in db_chunks]
            await nlp_controller.index_into_vector_db(
                project=new_project, chunks=db_chunks, chunks_ids=chunks_ids, do_reset=True,
            )

        # Return ONLY the extracted JSON without project_id
        return JSONResponse(
            content={
                "doctor_specialty": doctor_specialty,
                "ocr_text": ocr_text,
                "medicines": medicines,
            }
        )

    except Exception as e:
        logger.error("Error in API extract: %s", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": str(e),
            },
        )

