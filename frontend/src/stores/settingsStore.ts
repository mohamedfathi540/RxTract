import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ChatMessage, MedicineInfo } from '../api/types';

export interface PrescriptionResult {
    ocrText: string;
    medicines: MedicineInfo[];
    signal: string;
    previewDataUrl: string | null;
    projectId: number | null;
    doctorSpecialty?: string;
}

interface SettingsState {
    // Settings
    apiUrl: string;
    projectId: number;
    theme: 'dark' | 'light';

    // Chat History
    chatHistory: ChatMessage[];

    // Prescription Result (persisted across page switches)
    prescriptionResult: PrescriptionResult | null;

    // Actions
    setApiUrl: (url: string) => void;
    setProjectId: (id: number) => void;
    toggleTheme: () => void;
    addMessage: (message: ChatMessage) => void;
    clearHistory: () => void;
    setPrescriptionResult: (result: PrescriptionResult | null) => void;
}

export const useSettingsStore = create<SettingsState>()(
    persist(
        (set) => ({
            // Default values
            apiUrl: '/api/v1',
            projectId: 1,
            theme: 'dark',
            chatHistory: [],
            prescriptionResult: null,

            // Actions
            setApiUrl: (url) => set({ apiUrl: url }),

            setProjectId: (id) => set({ projectId: id }),

            toggleTheme: () => set((state) => ({
                theme: state.theme === 'dark' ? 'light' : 'dark'
            })),

            addMessage: (message) => set((state) => ({
                chatHistory: [...state.chatHistory, message].slice(-50), // Keep last 50 messages
            })),

            clearHistory: () => set({ chatHistory: [] }),

            setPrescriptionResult: (result) => set({ prescriptionResult: result }),
        }),
        {
            name: 'rxtract-settings',
        }
    )
);
