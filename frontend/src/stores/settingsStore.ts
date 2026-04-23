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
    /** Update the content of an existing message by id (used for streaming). */
    updateMessage: (id: string, content: string) => void;
    clearHistory: () => void;
    /**
     * Set the current prescription result.
     * Automatically clears chat history when the projectId changes so that
     * old messages about a different prescription don't bleed through.
     */
    setPrescriptionResult: (result: PrescriptionResult | null) => void;
}

export const useSettingsStore = create<SettingsState>()(
    persist(
        (set, get) => ({
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

            updateMessage: (id, content) => set((state) => ({
                chatHistory: state.chatHistory.map((msg) =>
                    msg.id === id ? { ...msg, content } : msg
                ),
            })),

            clearHistory: () => set({ chatHistory: [] }),

            setPrescriptionResult: (result) => set((state) => ({
                prescriptionResult: result,
                // Clear chat history when switching to a different prescription so
                // old messages from a previous analysis don't create confusion.
                chatHistory:
                    result?.projectId !== state.prescriptionResult?.projectId
                        ? []
                        : state.chatHistory,
            })),
        }),
        {
            name: 'rxtract-settings',
        }
    )
);
