import { apiClient } from './client';
import type { HealthResponse, QuotaStatusResponse } from './types';

export const checkHealth = async (): Promise<HealthResponse> => {
    const response = await apiClient.get<HealthResponse>('/');
    return response.data;
};

export const getQuotaStatus = async (): Promise<QuotaStatusResponse> => {
    const response = await apiClient.get<QuotaStatusResponse>('/quota/status');
    return response.data;
};
