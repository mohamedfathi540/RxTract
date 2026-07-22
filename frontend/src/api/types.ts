// Request Types

export interface ProcessRequest {
    chunk_size: number;
    overlap_size: number;
    Do_reset: number;
    file_id?: string;
}

export interface PushRequest {
    do_reset: boolean;
}

export interface SearchRequest {
    text: string;
    limit: number;
}

// Response Types

export interface HealthResponse {
    app_name: string;
    app_version: string;
}

export interface UploadResponse {
    signal: string;
    file_id: string;
}

export interface ProcessResponse {
    signal: string;
    Inserted_chunks: number;
    processed_files: number;
}

export interface PushResponse {
    Signal: string;
    InsertedItemsCount: number;
}

export interface CollectionInfo {
    vectors_count?: number;
    points_count?: number;
    indexed_vectors_count?: number;
}

export interface IndexInfoResponse {
    Signal: string;
    CollectionInfo: CollectionInfo;
}

export interface SearchResult {
    text: string;
    score: number;
    metadata?: Record<string, unknown>;
}

export interface SearchResponse {
    Signal: string;
    Results: SearchResult[];
}

export interface AnswerResponse {
    Signal: string;
    Answer: string;
    FullPrompt: string;
    ChatHistory: unknown[];
}

export interface ErrorResponse {
    signal?: string;
    Signal?: string;
    error?: string;
}

// Chat Types

export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    timestamp: string;
    metadata?: {
        fullPrompt?: string;
        chatHistory?: unknown[];
    };
}

// Prescription Types

export interface Candidate {
    name: string;
    product_url: string;
    image_url: string;
}

export interface MedicineInfo {
    name: string;
    active_ingredient: string;
    dosage: string | null;
    form: string | null;
    image_url: string | null;
    product_url: string | null;
    price?: string;
    candidates?: Candidate[];
}

export interface PrescriptionResponse {
    signal: string;
    doctor_specialty?: string;
    ocr_text: string;
    medicines: MedicineInfo[];
    project_id: number | null;
    image_url?: string;
    project_title?: string;
}

export interface PrescriptionChatRequest {
    text: string;
    limit: number;
    project_id: number;
}

export interface PrescriptionChatResponse {
    Signal: string;
    Answer: string;
    FullPrompt: string;
    ChatHistory: unknown[];
}

// Upload Types

export interface UploadedFile {
    id: string;
    name: string;
    size: number;
    status: 'pending' | 'uploading' | 'uploaded' | 'error';
    error?: string;
}

// Quota Types

export interface QuotaUsage {
    used: number;
    limit: number;
}

export interface QuotaStatusResponse {
    date: string;
    queries: QuotaUsage;
    prescriptions: QuotaUsage;
    api_calls: QuotaUsage;
}

// Medicine Search Types

export interface SearchMedicineResult {
    trade_name: string;
    active_ingredient: string;
    image_url: string;
    product_url: string;
}

export interface SearchMedicineResponse {
    results: SearchMedicineResult[];
}

export interface HistoryItem {
    id: string;
    title: string;
    is_pinned: boolean;
    created_at: string | null;
    updated_at: string | null;
    share_token?: string | null;
}
