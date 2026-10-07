'use client';

import React from 'react';
import { COUNTRIES, CountryCode } from '../lib/jurisdictions';
import { cn } from '../lib/cn';

interface CountryToggleProps {
  value: CountryCode;
  onChange: (value: CountryCode) => void;
  disabled?: boolean;
}

/** Segmented control to pick the country (US / Canada). */
export default function CountryToggle({ value, onChange, disabled }: CountryToggleProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Country"
      className="inline-flex rounded-full border border-dark-borderMedium bg-dark-bgSecondary p-0.5"
    >
      {COUNTRIES.map((c) => {
        const active = c.code === value;
        return (
          <button
            key={c.code}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(c.code)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium transition-colors',
              'focus:outline-none focus:ring-1 focus:ring-primary-accent',
              active
                ? 'bg-primary-accent text-white shadow-sm'
                : 'text-dark-textSecondary hover:text-dark-textPrimary',
              disabled && 'opacity-50 cursor-not-allowed',
            )}
          >
            <span aria-hidden>{c.flag}</span>
            <span className="hidden sm:inline">{c.label}</span>
          </button>
        );
      })}
    </div>
  );
}
