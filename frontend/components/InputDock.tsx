'use client';

import React from 'react';
import { IconSend } from './Icons';
import QuickActions from './QuickActions';
import ScopeBar from './ScopeBar';
import { CountryCode } from '../lib/jurisdictions';

interface InputDockProps {
  input: string;
  onInputChange: (value: string) => void;
  onSend: (message?: string) => void;
  disabled?: boolean;
  // Scope selection
  country: CountryCode;
  jurisdiction: string;
  categories: string[];
  onCountryChange: (value: CountryCode) => void;
  onJurisdictionChange: (value: string) => void;
  onToggleCategory: (value: string) => void;
  onClearCategories: () => void;
}

export default function InputDock({
  input,
  onInputChange,
  onSend,
  disabled = false,
  country,
  jurisdiction,
  categories,
  onCountryChange,
  onJurisdictionChange,
  onToggleCategory,
  onClearCategories,
}: InputDockProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="input-dock">
      <ScopeBar
        country={country}
        jurisdiction={jurisdiction}
        categories={categories}
        onCountryChange={onCountryChange}
        onJurisdictionChange={onJurisdictionChange}
        onToggleCategory={onToggleCategory}
        onClearCategories={onClearCategories}
        disabled={disabled}
      />

      <QuickActions onQuerySelect={(query) => onSend(query)} disabled={disabled} />

      <div className="input-wrapper">
        <input
          className="text-input"
          placeholder="Ask about a statute, regulation, or case…"
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
