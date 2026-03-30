import { apiClient, uploadFileWithProgress } from './client';
import type { UploadResponse, ProcessRequest, ProcessResponse } from './types';

export const uploadFile = async (
    projectId: number,
    file: File,
    onProgress?: (progress: number) => void
): Promise<UploadResponse> => {
    const response = await uploadFileWithProgress(
        `/data/upload/${projectId}`,
        file,
        onProgress
    );
    return response.data;
};

export const processFiles = async (
    projectId: number,
    request: ProcessRequest
): Promise<ProcessResponse> => {
    const response = await apiClient.post<ProcessResponse>(
        `/data/process/${projectId}`,
        request
    );
    return response.data;
};

export const resetProject = async (
    projectId: number
): Promise<void> => {
    await apiClient.delete(
        `/data/project/${projectId}/assets`
    );
};

export const searchMedicine = async (
    query: string,
    limit: number = 15
): Promise<import('./types').SearchMedicineResponse> => {
    const response = await apiClient.get<import('./types').SearchMedicineResponse>(
        `/data/search-medicine`,
        { params: { query, limit } }
    );
    return response.data;
};
