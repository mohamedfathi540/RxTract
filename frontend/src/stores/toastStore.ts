import { create } from 'zustand';

export interface Toast {
    id: string;
    message: string;
    type: 'error' | 'warning' | 'info' | 'success';
}

interface ToastState {
    toasts: Toast[];
    addToast: (message: string, type?: Toast['type']) => void;
    removeToast: (id: string) => void;
}

let _counter = 0;

export const useToastStore = create<ToastState>()((set) => ({
    toasts: [],
    addToast: (message, type = 'error') => {
        const id = `toast-${++_counter}`;
        set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
        // Auto-dismiss after 6 seconds
        setTimeout(() => {
            set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
        }, 6000);
    },
    removeToast: (id) =>
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
