from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from Routes import Base
from Routes import Data
from Routes import NLP
from Routes import Prescription
from Routes import Auth
from Helpers.Config import get_settings
from Stores.LLM.LLMProviderFactory import LLMProviderFactory
from Stores.VectorDB.VectorDBProviderFactory import VectorDBProviderFactory
from Stores.LLM.Templates.template_parser import template_parser as TemplateParser
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from Utils.metrics import setup_metrics
from Utils.security import get_current_user
from Utils.rate_limit import limiter

# ── Create FastAPI instance ─────────────────────────────────────────
app = FastAPI()

# Rate-limit middleware & error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5777", "http://localhost:3000", "http://localhost:8000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
setup_metrics(app)


# ── Startup event ───────────────────────────────────────────────────
@app.on_event("startup")
async def startup_span():
    settings = get_settings()

    postgres_connection = (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DB}"
    )
    app.db_engine = create_async_engine(postgres_connection, pool_pre_ping=True)
    app.db_client = sessionmaker(
        app.db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # LLM Provider Factory
    llm_provider_factory = LLMProviderFactory(settings)
    vectordb_provider_factory = VectorDBProviderFactory(config=settings, db_client=app.db_client)

    # Generation Client
    app.genration_client = llm_provider_factory.create(provider=settings.GENRATION_BACKEND)
    app.genration_client.set_genration_model(model_id=settings.GENRATION_MODEL_ID)

    # Embedding Client
    app.embedding_client = llm_provider_factory.create(provider=settings.EMBEDDING_BACKEND)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_SIZE,
    )

    # OCR Client (for prescription analysis)
    ocr_backend = getattr(settings, "OCR_BACKEND", "LLAMAPARSE").upper()
    app.ocr_client = llm_provider_factory.create_ocr(ocr_backend=ocr_backend)

    # VectorDB Client
    app.vectordb_client = vectordb_provider_factory.create(provider=settings.VECTORDB_BACKEND)
    await app.vectordb_client.connect()

    # Template Parser
    app.template_parser = TemplateParser(
        language=settings.PRIMARY_LANGUAGE,
        default_language=settings.DEFUALT_LANGUAGE,
    )


# ── Shutdown event ──────────────────────────────────────────────────
@app.on_event("shutdown")
async def shutdown_span():
    await app.db_engine.dispose()
    await app.vectordb_client.disconnect()


# ── Include Routers ─────────────────────────────────────────────────

# Public routes (no auth required)
app.include_router(Base.base_router)
app.include_router(Auth.auth_router)

# Protected routes (JWT required)
app.include_router(Data.data_router, dependencies=[Depends(get_current_user)])
app.include_router(NLP.nlp_router, dependencies=[Depends(get_current_user)])
app.include_router(Prescription.prescription_router, dependencies=[Depends(get_current_user)])


# ── Rate-limited health endpoint ────────────────────────────────────
@app.get("/api/health")
@limiter.limit("5/minute")
async def health_check(request: Request):
    return {"status": "ok"}


# ── Quota status endpoint (authenticated users) ────────────────────
from Utils.rate_limit import get_user_quota_status

@app.get("/api/v1/quota/status", dependencies=[Depends(get_current_user)])
async def quota_status(request: Request, user=Depends(get_current_user)):
    return await get_user_quota_status(request, user)