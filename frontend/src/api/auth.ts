import axios from 'axios';
import { useSettingsStore } from '../stores/settingsStore';

// Auth types
export interface RegisterRequest {
    email: string;
    password: string;
}

export interface LoginRequest {
    email: string;
    password: string;
}

export interface AuthResponse {
    access_token: string;
    token_type: string;
}

export interface ApiKeyStatusResponse {
    has_key: boolean;
}

export interface ApiKeyGenerateResponse {
    api_key: string;
    message: string;
}

export interface MessageResponse {
    message: string;
}

// We use raw axios here (not apiClient) because auth endpoints
// don't need the Bearer token interceptor, EXCEPT for API Key management
// which requires JWT token, so we'll use apiClient for those.
import { apiClient } from './client';

const getBaseUrl = () => {
    const { apiUrl } = useSettingsStore.getState();
    // apiUrl is "/api/v1" — auth lives at "/api/v1/auth"
    return apiUrl;
};

export const authApi = {
    register: async (data: RegisterRequest): Promise<MessageResponse> => {
        const res = await axios.post<MessageResponse>(
            `${getBaseUrl()}/auth/register`,
            data
        );
        return res.data;
    },

    login: async (data: LoginRequest): Promise<AuthResponse> => {
        const res = await axios.post<AuthResponse>(
            `${getBaseUrl()}/auth/login`,
            data
        );
        return res.data;
    },

    verifyEmail: async (token: string): Promise<MessageResponse> => {
        const res = await axios.get<MessageResponse>(
            `${getBaseUrl()}/auth/verify`,
            { params: { token } }
        );
        return res.data;
    },

    resendVerification: async (email: string): Promise<MessageResponse> => {
        const res = await axios.post<MessageResponse>(
            `${getBaseUrl()}/auth/resend-verification`,
            { email }
        );
        return res.data;
    },

    // ── API Key Management (Requires JWT) ─────────────────────────
    generateApiKey: async (): Promise<ApiKeyGenerateResponse> => {
        const res = await apiClient.post<ApiKeyGenerateResponse>('/auth/api-key/generate');
        return res.data;
    },

    revokeApiKey: async (): Promise<MessageResponse> => {
        const res = await apiClient.delete<MessageResponse>('/auth/api-key/revoke');
        return res.data;
    },

    getApiKeyStatus: async (): Promise<ApiKeyStatusResponse> => {
        const res = await apiClient.get<ApiKeyStatusResponse>('/auth/api-key/status');
        return res.data;
    },
};
