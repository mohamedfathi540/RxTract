import { create } from 'zustand';
import type { QuotaStatusResponse } from '../api/types';
import { getQuotaStatus } from '../api/base';

interface QuotaState {
    quota: QuotaStatusResponse | null;
    isLoading: boolean;
    error: string | null;
    fetchQuota: () => Promise<void>;
}

export const useQuotaStore = create<QuotaState>()((set) => ({
    quota: null,
    isLoading: false,
    error: null,

    fetchQuota: async () => {
        set({ isLoading: true, error: null });
        try {
            const data = await getQuotaStatus();
            set({ quota: data, isLoading: false });
        } catch (e) {
            set({ error: (e as Error).message, isLoading: false });
        }
    },
}));
