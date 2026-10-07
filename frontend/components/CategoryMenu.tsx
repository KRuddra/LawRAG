'use client';

import React from 'react';
import * as Popover from '@radix-ui/react-popover';
import { Check, SlidersHorizontal } from 'lucide-react';
import { CATEGORIES } from '../lib/jurisdictions';
import { cn } from '../lib/cn';

interface CategoryMenuProps {
  selected: string[];
  onToggle: (value: string) => void;
  onClear: () => void;
  disabled?: boolean;
}

/** Compact categories picker: one trigger with a count, opens a checklist. */
export default function CategoryMenu({ selected, onToggle, onClear, disabled }: CategoryMenuProps) {
  const count = selected.length;
  return (
    <Popover.Root>
      <Popover.Trigger
        disabled={disabled}
        className={cn(
          'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition-colors',
          'focus:outline-none focus:ring-1 focus:ring-primary-accent disabled:opacity-50 disabled:cursor-not-allowed',
          count > 0
            ? 'border-primary-accent bg-primary-accent/10 text-primary-accent'
            : 'border-dark-borderMedium bg-dark-bgSecondary text-dark-textPrimary hover:border-primary-accent',
        )}
      >
        <SlidersHorizontal size={14} />
        <span>Categories</span>
        {count > 0 && (
          <span className="rounded-full bg-primary-accent px-1.5 text-xs font-semibold text-white">{count}</span>
        )}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={6}
          align="start"
          className="z-50 w-64 rounded-lg border border-dark-borderMedium bg-dark-card p-2 shadow-xl"
        >
          <div className="mb-1 flex items-center justify-between px-2 pt-1">
            <span className="text-[11px] uppercase tracking-wide text-dark-textSecondary/60">Categories of law</span>
            {count > 0 && (
              <button
                type="button"
                onClick={onClear}
                className="text-xs text-dark-textSecondary hover:text-dark-textPrimary"
              >
                Clear
              </button>
            )}
          </div>
          <div className="max-h-64 overflow-y-auto">
            {CATEGORIES.map((c) => {
              const active = selected.includes(c.value);
              return (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => onToggle(c.value)}
                  className={cn(
                    'flex w-full items-center justify-between rounded px-2 py-1.5 text-sm outline-none transition-colors',
                    active ? 'text-primary-accent' : 'text-dark-textSecondary',
                    'hover:bg-primary-accent/10 hover:text-dark-textPrimary',
                  )}
                >
                  <span>{c.label}</span>
                  {active && <Check size={14} />}
                </button>
              );
            })}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
