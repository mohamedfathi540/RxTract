import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
    // State
    token: string | null;
    userEmail: string | null;
    isAuthenticated: boolean;

    // Actions
    login: (token: string, email: string) => void;
    logout: () => void;
}

export const useAuthStore = create<AuthState>()(
    persist(
        (set) => ({
            token: null,
            userEmail: null,
            isAuthenticated: false,

            login: (token, email) =>
                set({ token, userEmail: email, isAuthenticated: true }),

            logout: () =>
                set({ token: null, userEmail: null, isAuthenticated: false }),
        }),
        {
            name: 'tashfeer-auth',
        }
    )
);
