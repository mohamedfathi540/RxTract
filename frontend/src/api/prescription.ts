import type { PrescriptionResponse, PrescriptionChatRequest, PrescriptionChatResponse, HistoryItem } from './types';
import axios from 'axios';
import { apiClient, uploadFileWithProgress } from './client';
import { useSettingsStore } from '../stores/settingsStore';
import { useAuthStore } from '../stores/authStore';

/** Progress event from the SSE stream */
export interface OcrProgressEvent {
    step: string;   // "upload" | "ocr" | "extraction" | "enrichment" | "indexing" | "complete"
    detail: string; // human-readable description
    progress: number; // 0-100
}

/**
 * Upload a prescription image and receive real-time progress
 * events via Server-Sent Events.
 */
export const analyzePrescriptionStream = (
    file: File,
    onProgress: (event: OcrProgressEvent) => void,
    onResult: (data: PrescriptionResponse) => void,
    onError: (error: string) => void,
): { abort: () => void } => {
    const { apiUrl } = useSettingsStore.getState();
    const { token } = useAuthStore.getState();

    const abortController = new AbortController();

    const formData = new FormData();
    formData.append('file', file);

    fetch(`${apiUrl}/prescription/analyze-stream`, {
        method: 'POST',
        headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
        signal: abortController.signal,
    })
        .then(async (response) => {
            if (!response.ok) {
                const text = await response.text();
                if (response.status === 429) {
                    // Show quota warning via toast, not a page-level error
                    const { useToastStore } = await import('../stores/toastStore');
                    const { useQuotaStore } = await import('../stores/quotaStore');
                    let msg = 'Rate limit exceeded. Please try again shortly.';
                    try { msg = JSON.parse(text).detail || msg; } catch {}
                    useToastStore.getState().addToast(msg, 'warning');
                    useQuotaStore.getState().fetchQuota();
                    onError(`__RATE_LIMIT__${msg}`);
                    return;
                }
                onError(`Server error: ${response.status} - ${text}`);
                return;
            }

            const reader = response.body?.getReader();
            if (!reader) {
                onError('Streaming not supported by browser');
                return;
            }

            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // SSE lines are separated by double newlines
                const lines = buffer.split('\n\n');
                // Keep the last incomplete chunk in the buffer
                buffer = lines.pop() || '';

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith('data: ')) continue;

                    try {
                        const json = JSON.parse(trimmed.slice(6));

                        if (json.type === 'progress') {
                            onProgress({
                                step: json.step,
                                detail: json.detail,
                                progress: json.progress,
                            });
                        } else if (json.type === 'result') {
                            onResult({
                                signal: json.signal,
                                ocr_text: json.ocr_text,
                                medicines: json.medicines,
                                project_id: json.project_id,
                            });
                        } else if (json.type === 'error') {
                            onError(json.error);
                        }
                    } catch {
                        // Ignore malformed lines
                    }
                }
            }
        })
        .catch((err) => {
            if (err.name !== 'AbortError') {
                onError(err.message || 'Connection failed');
            }
        });

    return { abort: () => abortController.abort() };
};

/** Legacy non-streaming endpoint (backward compatible) */
export const analyzePrescription = async (
    file: File,
    onProgress?: (progress: number) => void
): Promise<PrescriptionResponse> => {
    const response = await uploadFileWithProgress(
        '/prescription/analyze',
        file,
        onProgress
    );
    return response.data;
};

export const chatAboutPrescription = async (
    request: PrescriptionChatRequest
): Promise<PrescriptionChatResponse> => {
    const response = await apiClient.post<PrescriptionChatResponse>(
        '/prescription/chat',
        request,
        { timeout: 60000 }
    );
    return response.data;
};

/** SSE chunk event from the streaming chat endpoint */
export interface ChatStreamChunk {
    type: 'chunk' | 'done' | 'error';
    content?: string;
    message?: string;
}

/**
 * Stream a chat answer about a prescription via Server-Sent Events.
 *
 * Mirrors the pattern of analyzePrescriptionStream.
 *
 * @returns { abort } — call abort() to cancel mid-stream.
 */
export const chatAboutPrescriptionStream = (
    request: PrescriptionChatRequest,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (message: string) => void,
): { abort: () => void } => {
    const { apiUrl } = useSettingsStore.getState();
    const { token } = useAuthStore.getState();
    const abortController = new AbortController();

    fetch(`${apiUrl}/prescription/chat-stream`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(request),
        signal: abortController.signal,
    })
        .then(async (response) => {
            if (!response.ok) {
                const text = await response.text();
                if (response.status === 429) {
                    const { useToastStore } = await import('../stores/toastStore');
                    const { useQuotaStore } = await import('../stores/quotaStore');
                    let msg = 'Rate limit exceeded. Please try again shortly.';
                    try { msg = JSON.parse(text).detail || msg; } catch { /* ignore */ }
                    useToastStore.getState().addToast(msg, 'warning');
                    useQuotaStore.getState().fetchQuota();
                    onError(`__RATE_LIMIT__${msg}`);
                    return;
                }
                onError(`Server error: ${response.status} — ${text}`);
                return;
            }

            const reader = response.body?.getReader();
            if (!reader) {
                onError('Streaming not supported by this browser.');
                return;
            }

            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith('data: ')) continue;
                    try {
                        const json: ChatStreamChunk = JSON.parse(trimmed.slice(6));
                        if (json.type === 'chunk' && json.content !== undefined) {
                            onChunk(json.content);
                        } else if (json.type === 'done') {
                            onDone();
                        } else if (json.type === 'error') {
                            onError(json.message ?? 'Unknown streaming error.');
                        }
                    } catch {
                        // Ignore malformed SSE lines
                    }
                }
            }
        })
        .catch((err) => {
            if (err.name !== 'AbortError') {
                onError(err.message || 'Connection failed.');
            }
        });

    return { abort: () => abortController.abort() };
};

export const fetchHistory = async (): Promise<HistoryItem[]> => {
    const response = await apiClient.get<{ signal: string; history: HistoryItem[] }>('/prescription/history');
    return response.data.history || [];
};

export const renameItem = async (id: string, title: string): Promise<void> => {
    await apiClient.patch(`/prescription/${id}/rename`, { title });
};

export const togglePin = async (id: string): Promise<boolean> => {
    const response = await apiClient.patch<{ signal: string; is_pinned: boolean }>(`/prescription/${id}/pin`);
    return response.data.is_pinned;
};

export const deleteItem = async (id: string): Promise<void> => {
    await apiClient.delete(`/prescription/${id}`);
};

export const shareItem = async (id: string): Promise<string> => {
    const response = await apiClient.post<{ signal: string; share_token: string }>(`/prescription/${id}/share`);
    return response.data.share_token;
};

export const fetchPrescription = async (id: string): Promise<PrescriptionResponse> => {
    const response = await apiClient.get<PrescriptionResponse>(`/prescription/${id}`);
    return response.data;
};

export const fetchSharedPrescription = async (token: string): Promise<PrescriptionResponse> => {
    // Use axios directly to bypass the auth interceptor so unauthenticated users can access it
    const { apiUrl } = useSettingsStore.getState();
    const response = await axios.get<PrescriptionResponse>(`${apiUrl}/prescription/shared/${token}`);
    return response.data;
};
