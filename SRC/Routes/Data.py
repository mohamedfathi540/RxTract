from fastapi import FastAPI,APIRouter,Depends,UploadFile,status,Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
import os
from Helpers.Config import get_settings,settings
from Controllers import datacontroller ,projectcontroller ,processcontroller,NLPController
import aiofiles
from Models import ResponseSignal
import logging
from .Schemes.Date_Schemes import ProcessRequest
from Models.Project_Model import projectModel
from Models.DB_Schemes import dataChunk ,Asset
from Models.Chunk_Model import ChunkModel
from Models.Asset_Model import AssetModel
from Models.enums.AssetTypeEnum import assettypeEnum
from Utils.rate_limit import limiter, config_limit
from Utils.security import get_current_user


logger = logging.getLogger("uvicorn.error")

data_router = APIRouter(
    prefix = "/api/v1/data",
    tags = ["api_v1","data"]

)

@data_router.post("/upload/{project_id}")
@limiter.limit(config_limit("RATE_LIMIT_UPLOAD"))
async def upload_data (request :Request,project_id : int ,file : UploadFile ,
                       user=Depends(get_current_user),
                       app_settings : settings = Depends(get_settings))  :


    project_model = await projectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
    )

    # validate the file properties

    data_controller = datacontroller()
    is_valid ,result_signal = data_controller.validate_uploaded_file(file = file) 
    
    if not is_valid : 
       return JSONResponse(
           status_code = status.HTTP_400_BAD_REQUEST ,
           content={
                "signal": result_signal        }
           )    
    
    project_dir_path = projectcontroller().get_project_path(project_id = project_id )
    file_path, file_id = data_controller.genrate_unique_filepath(org_filename=file.filename ,project_id=project_id )



    try :
        async with aiofiles.open(file_path, "wb") as f :
            while chunk := await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE) :
                await f.write(chunk)

    except Exception as E :

        logger.error(f"Error while uploading the file : {E}")
        
        return JSONResponse(
           content={
                "signal": ResponseSignal.FILE_NOT_UPLOADED.value   }
           )    
    
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    asset_resource = Asset(asset_project_id=project.project_id,
                            asset_type=assettypeEnum.FILE.value,
                            asset_name=file_id,
                            asset_size=os.path.getsize(file_path))
    asset_record = await asset_model.create_asset(asset=asset_resource)

    return JSONResponse(
           content={
                "signal": ResponseSignal.FILE_UPLOADED.value,
                "file_id" : str(asset_record.asset_id)             }
           )


@data_router.delete("/asset/{project_id}/{file_id}")
@limiter.limit(config_limit("RATE_LIMIT_UPLOAD"))
async def delete_asset(request: Request, project_id: int, file_id: str):
    """Remove an asset (and its chunks/vectors) from the project. file_id can be asset_id (integer) or asset_name (e.g. filename)."""
    project_model = await projectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_or_create_one(project_id=project_id)
    if not project:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"signal": ResponseSignal.PROJECT_NOT_FOUND.value},
        )
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    chunk_model = await ChunkModel.create_instance(db_client=request.app.db_client)
    try:
        asset_id_int = int(file_id)
        asset = await asset_model.get_asset_by_id(asset_id=asset_id_int)
    except ValueError:
        asset = await asset_model.get_asset_record(
            asset_project_id=project.project_id, asset_name=file_id
        )
    if not asset or asset.asset_project_id != project.project_id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"signal": ResponseSignal.ASSET_NOT_FOUND.value},
        )
    asset_id = asset.asset_id
    chunk_ids = await chunk_model.get_chunk_ids_by_asset_id(asset_id)
    if chunk_ids:
        nlp_controller = NLPController(
            genration_client=request.app.genration_client,
            embedding_client=request.app.embedding_client,
            vectordb_client=request.app.vectordb_client,
            template_parser=request.app.template_parser,
        )
        collection_name = nlp_controller.create_collection_name(project_id=project.project_id)
        await request.app.vectordb_client.delete_by_chunk_ids(collection_name, chunk_ids)
    await chunk_model.delete_chunks_by_asset_id(asset_id)
    await asset_model.delete_asset(asset_id)
    return JSONResponse(
        content={"signal": ResponseSignal.ASSET_DELETED.value, "asset_id": asset_id},
    )


@data_router.delete("/project/{project_id}/assets")
@limiter.limit(config_limit("RATE_LIMIT_UPLOAD"))
async def delete_all_assets(request: Request, project_id: int):
    """Remove all file assets (and their chunks/vectors) from the project."""
    project_model = await projectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_or_create_one(project_id=project_id)
    if not project:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"signal": ResponseSignal.PROJECT_NOT_FOUND.value},
        )
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    chunk_model = await ChunkModel.create_instance(db_client=request.app.db_client)
    assets = await asset_model.get_all_project_asset(
        asset_project_id=project.project_id,
        asset_type=assettypeEnum.FILE.value,
    )
    if not assets:
        return JSONResponse(
            content={
                "signal": ResponseSignal.ASSETS_DELETED.value,
                "deleted_count": 0,
            },
        )
    nlp_controller = NLPController(
        genration_client=request.app.genration_client,
        embedding_client=request.app.embedding_client,
        vectordb_client=request.app.vectordb_client,
        template_parser=request.app.template_parser,
    )
    collection_name = nlp_controller.create_collection_name(project_id=project.project_id)
    deleted_count = 0
    for asset in assets:
        asset_id = asset.asset_id
        chunk_ids = await chunk_model.get_chunk_ids_by_asset_id(asset_id)
        if chunk_ids:
            await request.app.vectordb_client.delete_by_chunk_ids(
                collection_name, chunk_ids
            )
        await chunk_model.delete_chunks_by_asset_id(asset_id)
        await asset_model.delete_asset(asset_id)
        deleted_count += 1
    if deleted_count and project_id == getattr(settings, "LEARNING_BOOKS_PROJECT_ID", None):
        try:
            await request.app.vectordb_client.delete_collection(
                collection_name=collection_name
            )
        except Exception:
            pass
        try:
            from Stores.Sparse import BM25Index
            BM25Index.delete_index(project.project_id)
        except Exception:
            pass
    return JSONResponse(
        content={
            "signal": ResponseSignal.ASSETS_DELETED.value,
            "deleted_count": deleted_count,
        },
    )


@data_router.post("/process/{project_id}")
@limiter.limit(config_limit("RATE_LIMIT_UPLOAD"))
async def process_endpoint (request :Request ,project_id :int ,process_request : ProcessRequest) :

    settings = get_settings()
    chunk_size = process_request.chunk_size
    overlap_size = process_request.overlap_size
    if project_id == getattr(settings, "LEARNING_BOOKS_PROJECT_ID", None):
        chunk_size = getattr(settings, "LEARNING_BOOKS_CHUNK_SIZE", 2000)
        overlap_size = getattr(settings, "LEARNING_BOOKS_OVERLAP_SIZE", 200)
    if chunk_size is None:
        chunk_size = 100
    if overlap_size is None:
        overlap_size = 20
    do_reset = process_request.Do_reset

    project_model =await projectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
    )

    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    project_files_ids = {}

    nlp_controller = NLPController(
        genration_client=request.app.genration_client,
        embedding_client=request.app.embedding_client,
        vectordb_client=request.app.vectordb_client,
        template_parser=request.app.template_parser 
    )

    if process_request.file_id:
        try:
            file_id_int = int(process_request.file_id)
            asset_record = await asset_model.get_asset_by_id(asset_id=file_id_int)
        except ValueError:
            # If it's not a numeric ID, try looking up by name (backwards compatibility)
            asset_record = await asset_model.get_asset_record(asset_project_id=project_id,
                                                              asset_name=process_request.file_id)
        if asset_record is None :
            return JSONResponse(
            status_code = status.HTTP_400_BAD_REQUEST ,
            content={
                "signal": ResponseSignal.FILE_ID_ERROR.value})
        
        project_files_ids = {
            asset_record.asset_id : asset_record.asset_name
        }

    else :
        project_files_ids =await asset_model.get_all_project_asset(asset_project_id=project.project_id,
                                                                   asset_type=assettypeEnum.FILE.value)
        project_files_ids ={
            record.asset_id : record.asset_name
            for record in project_files_ids
        }
    
    if len (project_files_ids) == 0 :
        return JSONResponse(
            status_code = status.HTTP_400_BAD_REQUEST ,
            content={
                "signal": ResponseSignal.NO_FILE_ERROR.value})


    Process_Controller = processcontroller(project_id=project_id)   

    no_files = 0
    no_records = 0

    chunk_model = await ChunkModel.create_instance(db_client=request.app.db_client)


    if do_reset == 1 :
        #delete associated vectors collection
        collection_name = nlp_controller.create_collection_name(project_id=project.project_id)
        _ = await request.app.vectordb_client.delete_collection(collection_name=collection_name)
        #delete associated chunks
        _ = await chunk_model.delete_chunk_by_project_id(project_id = project.project_id)
        if project_id == getattr(settings, "LEARNING_BOOKS_PROJECT_ID", None):
            try:
                from Stores.Sparse import BM25Index
                BM25Index.delete_index(project.project_id)
            except Exception:
                pass

    for asset_id, file_id in project_files_ids.items():
        try:
            file_content = await run_in_threadpool(Process_Controller.get_file_content, file_id=file_id)
        except Exception as e:
            err_msg = str(e)
            logger.error("Error while processing file %s: %s", file_id, err_msg)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": ResponseSignal.PROCESSING_FAILED.value,
                    "error": f"Failed to load file {file_id}. {err_msg}",
                    "hint": "PDF may be encrypted, corrupted, or unsupported; try an unprotected or re-exported copy.",
                },
            )

        if file_content is None:
            logger.error("Error while processing file: %s (file not found or not readable)", file_id)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": ResponseSignal.PROCESSING_FAILED.value,
                    "error": f"File not found or not readable: {file_id}. Check that the file exists in the project and has read permissions.",
                },
            )

        file_chunks = await run_in_threadpool(
            Process_Controller.process_file_content,
            file_content = file_content,
            file_id = file_id,
            chunk_size = chunk_size,
            overlap_size = overlap_size
            
        )

        if file_chunks is None or len(file_chunks) == 0:
            return JSONResponse(
            status_code = status.HTTP_400_BAD_REQUEST,
            content={
                    "signal": ResponseSignal.PROCESSING_FAILED.value,
                    "error": f"Processing resulted in 0 chunks for file {file_id}. Please check if the file contains readable text."
            }
            )

        file_chunks_records = [
            dataChunk(chunk_text = chunk.page_content ,
                    chunk_metadata = chunk.metadata,
                    chunk_order = i+1 ,
                    chunk_project_id = project.project_id ,
                    chunk_asset_id = asset_id
                    )
                    for i,chunk in enumerate(file_chunks)
        ]

        no_records += await chunk_model.insert_many_chunks(chunks = file_chunks_records)
        no_files += 1


    return JSONResponse(
           content={
                "signal": ResponseSignal.PROCESSING_DONE.value ,
                "Inserted_chunks" : no_records ,
                "processed_files" : no_files  })


   



