import * as React from 'react';
import { useState, useRef, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { MessageSquare, CheckSquare, Square } from 'lucide-react';
import { HistoryDropdown } from './HistoryDropdown';
import { useHistoryStore } from '../../stores/historyStore';
import type { HistoryItem as HistoryItemType } from '../../api/types';

interface HistoryItemProps {
  item: HistoryItemType;
  onItemClick?: () => void;
}

export function HistoryItem({ item, onItemClick }: HistoryItemProps) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [editTitle, setEditTitle] = useState(item.title);
  const inputRef = useRef<HTMLInputElement>(null);
  const { renameItem, isSelectionMode, selectedIds, toggleSelection } = useHistoryStore();
  const isSelected = selectedIds.has(item.id);

  useEffect(() => {
    if (isRenaming && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isRenaming]);

  const handleRenameSubmit = () => {
    if (editTitle.trim() !== '' && editTitle !== item.title) {
      renameItem(item.id, editTitle.trim());
    } else {
      setEditTitle(item.title); // reset if empty
    }
    setIsRenaming(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleRenameSubmit();
    } else if (e.key === 'Escape') {
      setEditTitle(item.title);
      setIsRenaming(false);
    }
  };

  return (
    <div className={`group relative flex items-center w-full px-2 py-1.5 mb-0.5 rounded-lg text-sm transition-all ${
      isSelectionMode 
        ? isSelected ? 'bg-primary-500/10 text-text-primary' : 'text-text-secondary hover:bg-bg-hover'
        : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
    }`}>
      {isSelectionMode ? (
        <button onClick={() => toggleSelection(item.id)} className="shrink-0 mr-3 text-text-muted hover:text-primary-500">
          {isSelected ? <CheckSquare className="w-4 h-4 text-primary-500" /> : <Square className="w-4 h-4" />}
        </button>
      ) : (
        <MessageSquare className="w-4 h-4 shrink-0 mr-3 opacity-70" />
      )}
      
      {isRenaming ? (
        <input
          ref={inputRef}
          type="text"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={handleRenameSubmit}
          onKeyDown={handleKeyDown}
          className="flex-1 bg-transparent outline-none border-b border-primary-500 text-text-primary px-0 py-0 min-w-0"
        />
      ) : isSelectionMode ? (
        <button
          onClick={() => toggleSelection(item.id)}
          className={`flex-1 truncate outline-none min-w-0 text-left ${isSelected ? 'text-primary-400 font-medium' : ''}`}
        >
          {item.title}
        </button>
      ) : (
        <NavLink
          to={`/prescription/${item.id}`}
          onClick={onItemClick}
          className={({ isActive }) =>
            `flex-1 truncate outline-none min-w-0 ${isActive ? 'text-primary-400 font-medium' : ''}`
          }
        >
          {item.title}
        </NavLink>
      )}

      {!isRenaming && !isSelectionMode && (
        <div className="shrink-0 ml-1 flex items-center">
          <HistoryDropdown
            id={item.id}
            isPinned={item.is_pinned}
            onRenameClick={() => setIsRenaming(true)}
          />
        </div>
      )}
    </div>
  );
}
