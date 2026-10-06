'use client';

import React from 'react';
import { IconSend } from './Icons';
import QuickActions from './QuickActions';

interface InputDockProps {
  input: string;
  onInputChange: (value: string) => void;
  onSend: (message?: string) => void;
  disabled?: boolean;
}

export default function InputDock({ input, onInputChange, onSend, disabled = false }: InputDockProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="input-dock">
      {/* Quick Actions */}
      <QuickActions
        onQuerySelect={(query) => {
          // Auto-send quick action queries (one tap sends common query)
          onSend(query);
        }}
        disabled={disabled}
      />

      {/* Main Input */}
      <div className="input-wrapper">
        <input
          className="text-input"
          placeholder="Enter legal inquiry or case number..."
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          autoFocus
        />
        <button
          className="send-btn"
          onClick={() => onSend()}
          disabled={disabled || !input.trim()}
          aria-label="Send message"
          type="button"
        >
          <IconSend />
        </button>
      </div>
    </div>
  );
}

