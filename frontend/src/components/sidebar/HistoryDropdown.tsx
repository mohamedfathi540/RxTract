import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { MoreVertical, Edit2, Pin, PinOff, Share2, Trash2 } from 'lucide-react';
import { useHistoryStore } from '../../stores/historyStore';
import { useState } from 'react';

interface HistoryDropdownProps {
  id: string;
  isPinned: boolean;
  onRenameClick: () => void;
}

export function HistoryDropdown({ id, isPinned, onRenameClick }: HistoryDropdownProps) {
  const { togglePin, deleteItem, shareItem } = useHistoryStore();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <DropdownMenu.Root open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenu.Trigger asChild>
        <button
          className="p-1 rounded-md opacity-100 md:opacity-0 md:group-hover:opacity-100 hover:bg-bg-hover text-text-muted hover:text-text-primary transition-all focus:opacity-100 outline-none"
          aria-label="More options"
        >
          <MoreVertical className="w-4 h-4" />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="min-w-[160px] bg-bg-secondary border border-border rounded-lg shadow-xl p-1 z-50 animate-in fade-in zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=closed]:zoom-out-95"
          sideOffset={5}
          align="start"
        >
          <DropdownMenu.Item
            className="flex items-center gap-2 px-2 py-1.5 text-sm text-text-secondary hover:text-text-primary hover:bg-bg-hover rounded-md cursor-pointer outline-none transition-colors"
            onSelect={() => onRenameClick()}
          >
            <Edit2 className="w-4 h-4" />
            Rename
          </DropdownMenu.Item>
          
          <DropdownMenu.Item
            className="flex items-center gap-2 px-2 py-1.5 text-sm text-text-secondary hover:text-text-primary hover:bg-bg-hover rounded-md cursor-pointer outline-none transition-colors"
            onSelect={() => togglePin(id)}
          >
            {isPinned ? <PinOff className="w-4 h-4" /> : <Pin className="w-4 h-4" />}
            {isPinned ? 'Unpin' : 'Pin'}
          </DropdownMenu.Item>
          
          <DropdownMenu.Item
            className="flex items-center gap-2 px-2 py-1.5 text-sm text-text-secondary hover:text-text-primary hover:bg-bg-hover rounded-md cursor-pointer outline-none transition-colors"
            onSelect={() => shareItem(id)}
          >
            <Share2 className="w-4 h-4" />
            Share
          </DropdownMenu.Item>

          <DropdownMenu.Separator className="h-px bg-border my-1 mx-2" />

          <DropdownMenu.Item
            className="flex items-center gap-2 px-2 py-1.5 text-sm text-error hover:bg-error/10 rounded-md cursor-pointer outline-none transition-colors"
            onSelect={() => deleteItem(id)}
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
