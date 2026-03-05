# RxTract Project Workflow

This document illustrates the end-to-end workflow of the RxTract RAG system, detailing the Data Ingestion Pipeline and the RAG Inference Pipeline.

## High-Level Workflow

The project consists of two main phases:
1.  **Data Ingestion**: Transforming raw documents into searchable vector embeddings.
2.  **RAG Inference**: Retrieving relevant contexts to answer user queries.

```mermaid
graph TD
    %% Styling
    classDef actor fill:#f9f,stroke:#333,stroke-width:2px;
    classDef frontend fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef backend fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef db fill:#fff3e0,stroke:#ef6c00,stroke-width:2px;
    classDef external fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;

    User((User)):::actor

    subgraph "Frontend Layer"
        UI[React UI]:::frontend
        UploadPage[Upload Page]:::frontend
        ChatPage[Chat Interface]:::frontend
    end

    subgraph "Backend Layer (FastAPI)"
        API[API Gateway]:::backend
        Processor[Document Processor]:::backend
        RAG[RAG Controller]:::backend
    end

    subgraph "Data Layer"
        VectorDB[(Vector DB\npgvector/Qdrant)]:::db
        DocStore[(Document Store)]:::db
    end

    subgraph "External Services"
        EmbedModels[Embedding Model]:::external
        LLM[LLM Provider]:::external
    end

    %% Ingestion Flow
    User -->|1. Upload Document| UploadPage
    UploadPage -->|POST /data/upload| API
    API -->|Save File| DocStore
    
    User -->|2. Process & Index| UploadPage
    UploadPage -->|POST /data/process| API
    API -->|Chunk Text| Processor
    Processor -->|POST /nlp/index/push| API
    API -->|Generate Embeddings| EmbedModels
    EmbedModels -->|Vector Embeddings| API
    API -->|Store Vectors| VectorDB

    %% Inference Flow
    User -->|3. Ask Question| ChatPage
    ChatPage -->|POST /nlp/index/answer| API
    API -->|Generate Query Embedding| EmbedModels
    EmbedModels -->|Query Vector| API
    API -->|Semantic Search| VectorDB
    VectorDB -->|Relevant Contexts| API
    API -->|Construct Prompt with Context| RAG
    RAG -->|Send Prompt| LLM
    LLM -->|Generated Answer| RAG
    RAG -->|Response| ChatPage
    ChatPage -->|Display Answer| User
```

## Detailed Process Flows

### 1. Data Ingestion Pipeline (Upload -> Index)

This process prepares the user's data for retrieval.

1.  **Upload**: User uploads a file (PDF, TXT, etc.).
    *   Endpoint: `POST /data/upload/{project_id}`
    *   Actions: File is validated and saved to the server's storage.
2.  **Process**: The system breaks the document into smaller chunks.
    *   Endpoint: `POST /data/process/{project_id}`
    *   Parameters: `chunk_size` (default: 100), `overlap_size` (default: 20).
    *   Actions: Text extraction and splitting.
3.  **Index**: Chunks are converted to vectors and stored.
    *   Endpoint: `POST /nlp/index/push/{project_id}`
    *   Actions: Calls Embedding Service -> Inserts into Vector DB.

### 2. RAG Inference Pipeline (Question -> Answer)

This is the "Final Result" delivery to the user.

1.  **User Query**: User types a question in the `ChatPage` or `LearningAssistantChatPage`.
2.  **Retrieval**:
    *   Endpoint: `POST /nlp/index/answer/{project_id}`
    *   Action: The question is embedded using the same model as the documents.
    *   Search: The system scans the Vector DB for chunks with high cosine similarity.
3.  **Generation**:
    *   Context Assembly: Retrieved chunks are combined into a system prompt.
    *   Prompt: "Answer the question based strictly on the context below..."
    *   LLM Call: The prompt is sent to OpenAI/Gemini/Cohere.
4.  **Result**: The LLM's text response is streamed or returned to the frontend.

## Key Components

*   **Learning Assistant**: A specialized view leveraging the RAG pipeline for a specific educational corpus.
*   **Learning Books Admin**: Management interface for the educational corpus assets.
