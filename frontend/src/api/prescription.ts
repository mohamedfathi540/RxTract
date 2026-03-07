import type { PrescriptionResponse, PrescriptionChatRequest, PrescriptionChatResponse } from './types';
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
