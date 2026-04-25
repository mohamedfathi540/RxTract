import { create } from 'zustand';
import { fetchHistory, renameItem, togglePin, deleteItem as deleteItemApi, shareItem } from '../api/prescription';
import type { HistoryItem } from '../api/types';
import { useToastStore } from './toastStore';
import { useSettingsStore } from './settingsStore';

interface HistoryState {
    items: HistoryItem[];
    isLoading: boolean;
    error: string | null;

    // Actions
    fetchHistory: () => Promise<void>;
    renameItem: (id: string, newTitle: string) => Promise<void>;
    togglePin: (id: string) => Promise<void>;
    deleteItem: (id: string) => Promise<void>;
    shareItem: (id: string) => Promise<void>;

    // Selection
    isSelectionMode: boolean;
    selectedIds: Set<string>;
    setSelectionMode: (mode: boolean) => void;
    toggleSelection: (id: string) => void;
    clearSelection: () => void;
    selectAllInGroup: (ids: string[], select: boolean) => void;
    deleteSelected: () => Promise<void>;
}

export const useHistoryStore = create<HistoryState>((set, get) => ({
    items: [],
    isLoading: false,
    error: null,
    isSelectionMode: false,
    selectedIds: new Set(),

    fetchHistory: async () => {
        set({ isLoading: true, error: null });
        try {
            const history = await fetchHistory();
            set({ items: history, isLoading: false });
        } catch (error) {
            set({ error: 'Failed to fetch history', isLoading: false });
            useToastStore.getState().addToast('Failed to fetch history', 'error');
        }
    },

    renameItem: async (id: string, newTitle: string) => {
        const previousItems = get().items;
        // Optimistic update
        set((state) => ({
            items: state.items.map((item) =>
                item.id === id ? { ...item, title: newTitle } : item
            ),
        }));

        try {
            await renameItem(id, newTitle);
        } catch (error) {
            // Revert on failure
            set({ items: previousItems });
            useToastStore.getState().addToast('Failed to rename item', 'error');
        }
    },

    togglePin: async (id: string) => {
        const previousItems = get().items;
        // Optimistic update
        set((state) => ({
            items: state.items.map((item) =>
                item.id === id ? { ...item, is_pinned: !item.is_pinned } : item
            ),
        }));

        try {
            const isPinned = await togglePin(id);
            // Sync with actual backend state
            set((state) => ({
                items: state.items.map((item) =>
                    item.id === id ? { ...item, is_pinned: isPinned } : item
                ),
            }));
        } catch (error) {
            // Revert on failure
            set({ items: previousItems });
            useToastStore.getState().addToast('Failed to pin item', 'error');
        }
    },

    deleteItem: async (id: string) => {
        const previousItems = get().items;
        // Optimistic update
        set((state) => ({
            items: state.items.filter((item) => item.id !== id),
        }));

        try {
            await deleteItemApi(id);
            useToastStore.getState().addToast('Item deleted', 'success');
            
            // If the deleted item is currently open, clear it and navigate home (full refresh)
            if (String(useSettingsStore.getState().prescriptionResult?.projectId) === String(id)) {
                useSettingsStore.getState().setPrescriptionResult(null);
                window.location.href = '/';
            }
        } catch (error) {
            // Revert on failure
            set({ items: previousItems });
            useToastStore.getState().addToast('Failed to delete item', 'error');
        }
    },

    shareItem: async (id: string) => {
        try {
            const token = await shareItem(id);
            // Create a public share URL (assuming domain is current window origin + /shared/)
            const shareUrl = `${window.location.origin}/shared/${token}`;
            
            // Try to copy to clipboard
            await navigator.clipboard.writeText(shareUrl);
            useToastStore.getState().addToast('Share link copied to clipboard', 'success');
        } catch (error) {
            useToastStore.getState().addToast('Failed to share item', 'error');
        }
    },

    setSelectionMode: (mode) => set({ isSelectionMode: mode, selectedIds: new Set() }),

    toggleSelection: (id) => set((state) => {
        const newSelected = new Set(state.selectedIds);
        if (newSelected.has(id)) {
            newSelected.delete(id);
        } else {
            newSelected.add(id);
        }
        return { selectedIds: newSelected };
    }),

    clearSelection: () => set({ selectedIds: new Set() }),

    selectAllInGroup: (ids, select) => set((state) => {
        const newSelected = new Set(state.selectedIds);
        if (select) {
            ids.forEach(id => newSelected.add(id));
        } else {
            ids.forEach(id => newSelected.delete(id));
        }
        return { selectedIds: newSelected };
    }),

    deleteSelected: async () => {
        const { selectedIds, items } = get();
        if (selectedIds.size === 0) return;

        const previousItems = items;
        // Optimistic update
        set({
            items: items.filter((item) => !selectedIds.has(item.id)),
            selectedIds: new Set(),
            isSelectionMode: false
        });

        try {
            // Delete in parallel
            await Promise.all(Array.from(selectedIds).map(id => deleteItemApi(id)));
            useToastStore.getState().addToast(`${selectedIds.size} items deleted`, 'success');

            // Check if currently open item was deleted
            const currentProjectId = String(useSettingsStore.getState().prescriptionResult?.projectId);
            if (selectedIds.has(currentProjectId)) {
                useSettingsStore.getState().setPrescriptionResult(null);
                window.location.href = '/';
            }
        } catch (error) {
            // Revert on failure, we might have partially deleted but reloading history is safer
            set({ items: previousItems });
            useToastStore.getState().addToast('Failed to delete some items', 'error');
            get().fetchHistory(); // Refresh to get actual state
        }
    },
}));
