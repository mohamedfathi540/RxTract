from pydantic_settings import BaseSettings ,SettingsConfigDict
from typing import List, Optional

class settings (BaseSettings):

    APP_NAME: str 
    APP_VERSION: str

    FILE_ALLOWED_TYPES :list
    FILE_MAX_SIZE :int
    FILE_DEFAULT_CHUNK_SIZE :int

    POSTGRES_USER : str
    POSTGRES_PASSWORD : str
    POSTGRES_HOST : str
    POSTGRES_PORT : str
    POSTGRES_MAIN_DB : str

    
    GENRATION_BACKEND : str
    EMBEDDING_BACKEND : str
    OCR_BACKEND : str = "LLAMAPARSE"
    OCR_MODEL_ID : Optional[str] = "gemini-2.0-flash"
    REFINEMENT_LLM_MODEL : Optional[str] = None
 
    OPENAI_API_KEY : Optional[str] = None
    OPENAI_BASE_URL : Optional[str] = None
    COHERE_API_KEY : Optional[str] = None
    GEMINI_API_KEY : Optional[str] = None
    GEMINI_API_VERSION : str = "v1"
    LLAMA_CLOUD_API_KEY : Optional[str] = None
    OLLAMA_BASE_URL : Optional[str] = None
    HUGGINGFACE_API_KEY : Optional[str] = None

    GENRATION_MODEL_ID_LITERAL : Optional[List[str]] = None
    EMBEDDING_MODEL_ID_LITERAL : Optional[List[str]] = None
    GENRATION_MODEL_ID : Optional[str] = None
    EMBEDDING_MODEL_ID : Optional[str] = None
    EMBEDDING_SIZE : Optional[int] = None


    INPUT_DEFUALT_MAX_CHARACTERS : Optional[int] = None
    GENRATED_DEFUALT_MAX_OUTPUT_TOKENS : Optional[int] = None
    GENRATION_DEFUALT_TEMPERATURE : Optional[float] = None 

    VECTORDB_BACKEND_LITERAL : Optional[List[str]] = None
    VECTORDB_BACKEND : str 
    VECTORDB_PATH : str
    VECTORDB_DISTANCE_METHOD : Optional[str] = None
    VECTORDB_PGVEC_INDEX_THRESHOLD : int = 4

    # Documentation Processing Settings
    DOC_CHUNK_SIZE : int = 1000
    DOC_OVERLAP_SIZE : int = 200
    DEFAULT_PROJECT_ID : int = 1

    # Prescription Analyzer chunk parameters
    PRESCRIPTION_CHUNK_SIZE : int = 300
    PRESCRIPTION_OVERLAP_SIZE : int = 50

    # Vision OCR generation parameters
    OCR_MAX_OUTPUT_TOKENS : int = 8192
    OCR_TEMPERATURE : float = 0.2

    # Web Scraping Configuration
    SCRAPING_MAX_PAGES : int = 1000
    SCRAPING_RATE_LIMIT : float = 0.1
    SCRAPING_USER_AGENT : str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    SCRAPING_TIMEOUT : int = 120
    SCRAPING_EMBED_BATCH_SIZE : int = 50
    SCRAPING_EMBED_DURING : int = 1
    SCRAPING_DEBUG : int = 0
    SCRAPING_USE_BROWSER : int = 1
    SCRAPING_CONCURRENCY : int = 1
    SCRAPING_IGNORE_ROBOTS : int = 1
    SCRAPING_NO_RESULTS_PHRASES : list = [
        '0 results', 'no product', 'no result', 'not found',
        'we couldn\'t find', 'we could not find', 'unable to find',
        'لم يتم العثور', 'لا توجد نتائج', 'عفوا', 'sorry, we can\'t find',
        'no products were found', 'no matching records found', 'we searched really hard',
    ]

    # Medicine Matcher (Fuzzy DB Matching)
    MEDICINE_MATCHER_ENABLED : bool = False
    MEDICINE_MATCHER_TOKEN_SET_THRESHOLD : int = 90
    MEDICINE_MATCHER_PARTIAL_THRESHOLD : int = 90
    MEDICINE_MATCHER_FIRST_WORD_THRESHOLD : int = 88

    # Pharmacy product search (for medicine URL scraping)
    PHARMACY_BASE_URL : str = "https://dwaprices.com/"
    PHARMACY_LOOKUP_TIMEOUT : float = 10.0


    DEFUALT_LANGUAGE : str = "en"
    PRIMARY_LANGUAGE : str = "en"


    # Chunking defaults for learning books (large references)
    LEARNING_BOOKS_CHUNK_SIZE : int = 2000
    LEARNING_BOOKS_OVERLAP_SIZE : int = 200

    # Optional JSON mapping of filename (or pattern) to domain for chunk metadata e.g. {"statistics.pdf": "statistics", "ml-intro.pdf": "ml"}
    BOOK_DOMAIN_MAPPING : Optional[str] = None

    # Hybrid search (dense + BM25): 0 = only BM25, 1 = only dense
    HYBRID_SEARCH_ENABLED : bool = True
    HYBRID_SEARCH_ALPHA : float = 0.6

    # BM25 index persistence directory (default: under SRC/data/bm25)
    BM25_INDEX_DIR : Optional[str] = None

    # ── Authentication / JWT ──
    JWT_SECRET : str = "change-me-in-production"
    JWT_ALGORITHM : str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES : int = 60

    # ── Rate Limits (per user unless noted) ──
    RATE_LIMIT_AUTH : str = "10/minute"          # per IP
    RATE_LIMIT_UPLOAD : str = "20/minute"
    RATE_LIMIT_QUERY : str = "30/minute"
    RATE_LIMIT_PRESCRIPTION : str = "10/minute"

    # ── Daily Usage Quotas (0 = unlimited) ──
    QUOTA_DAILY_QUERIES : int = 200
    QUOTA_DAILY_PRESCRIPTIONS : int = 30
    QUOTA_DAILY_API_CALLS : int = 100
    RATE_LIMIT_API : str = "30/minute"

    # ── Email Verification (Brevo) ──
    BREVO_API_KEY : Optional[str] = None
    SENDER_EMAIL : str = "noreply@yourdomain.com"
    FRONTEND_URL : str = "http://localhost:5173"

    # ── Pharmacy Agent / Correction Controller ──
    # Model used by MedicineCorrectionController for OCR name correction.
    # Defaults to gemini-2.5-flash (fast, cheap, accurate).
    CORRECTION_MODEL_ID : str = "gemini-2.5-flash"
    # Model used by PharmacyAgentController for multi-turn agentic chat.
    # Defaults to gemini-2.5-pro (best reasoning for medical context).
    AGENT_MODEL_ID : str = "gemini-2.5-pro"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra="ignore")

def get_settings () :
    return settings()
