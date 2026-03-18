import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { useSettingsStore } from '../stores/settingsStore';
import { useAuthStore } from '../stores/authStore';
import { useToastStore } from '../stores/toastStore';
import { useQuotaStore } from '../stores/quotaStore';

// Create axios instance
const createApiClient = (): AxiosInstance => {
    const client = axios.create({
        baseURL: '', // Will be set per-request
        timeout: 120000, // 2 minutes default
        headers: {
            'Content-Type': 'application/json',
        },
    });

    // Request interceptor to add base URL and auth token from stores
    client.interceptors.request.use(
        (config) => {
            const { apiUrl } = useSettingsStore.getState();
            config.baseURL = apiUrl;

            // Inject JWT token if available
            const { token } = useAuthStore.getState();
            if (token) {
                config.headers.Authorization = `Bearer ${token}`;
            }

            return config;
        },
        (error) => Promise.reject(error)
    );

    // Response interceptor for error handling
    client.interceptors.response.use(
        (response) => response,
        (error: AxiosError) => {
            if (error.response) {
                // If 401 Unauthorized, clear auth state and redirect to login
                if (error.response.status === 401) {
                    useAuthStore.getState().logout();
                    window.location.href = '/login';
                    return Promise.reject(new Error('Session expired. Please log in again.'));
                }

                // If 429 Too Many Requests, surface a clear rate-limit message
                if (error.response.status === 429) {
                    const data = error.response.data as { detail?: string };
                    const msg = data?.detail || 'Rate limit exceeded. Please slow down and try again shortly.';
                    useToastStore.getState().addToast(msg, 'warning');
                    // Refresh quota display
                    useQuotaStore.getState().fetchQuota();
                    return Promise.reject(Object.assign(new Error(msg), { isRateLimit: true }));
                }

                const errorData = error.response.data as { signal?: string; Signal?: string; error?: string; detail?: string };
                const errorMessage = errorData.detail || errorData.signal || errorData.Signal || errorData.error || 'An error occurred';
                return Promise.reject(new Error(errorMessage));
            } else if (error.request) {
                return Promise.reject(new Error('No response from server. Please check if the API is running.'));
            } else {
                return Promise.reject(new Error(error.message));
            }
        }
    );

    return client;
};

export const apiClient = createApiClient();

// Helper function for file uploads with progress
export const uploadFileWithProgress = async (
    url: string,
    file: File,
    onProgress?: (progress: number) => void
) => {
    const { apiUrl } = useSettingsStore.getState();
    const { token } = useAuthStore.getState();
    const formData = new FormData();
    formData.append('file', file);

    const headers: Record<string, string> = {
        'Content-Type': 'multipart/form-data',
    };
    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }

    return axios.post(`${apiUrl}${url}`, formData, {
        headers,
        onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
                const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                onProgress(progress);
            }
        },
        timeout: 180010, // 3 minutes for OCR processing
    });
};

