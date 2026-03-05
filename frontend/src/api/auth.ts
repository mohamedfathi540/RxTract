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

export interface MessageResponse {
    message: string;
}

// We use raw axios here (not apiClient) because auth endpoints
// don't need the Bearer token interceptor.

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
};
