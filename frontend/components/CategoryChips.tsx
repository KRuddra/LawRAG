'use client';

import React from 'react';
import { CATEGORIES } from '../lib/jurisdictions';
import { cn } from '../lib/cn';

interface CategoryChipsProps {
  selected: string[];
  onToggle: (value: string) => void;
  disabled?: boolean;
}

export default function CategoryChips({ selected, onToggle, disabled }: CategoryChipsProps) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Categories of law">
      {CATEGORIES.map((c) => {
        const active = selected.includes(c.value);
        return (
          <button
            key={c.value}
            type="button"
            disabled={disabled}
            aria-pressed={active}
            onClick={() => onToggle(c.value)}
            className={cn(
              'rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
              'focus:outline-none focus:ring-1 focus:ring-primary-accent',
              active
                ? 'border-primary-accent bg-primary-accent/15 text-primary-accent'
                : 'border-dark-borderLight text-dark-textSecondary hover:border-dark-borderMedium hover:text-dark-textPrimary',
              disabled && 'opacity-50 cursor-not-allowed',
            )}
          >
            {c.label}
          </button>
        );
      })}
    </div>
  );
}
