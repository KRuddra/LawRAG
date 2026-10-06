'use client';

import React from 'react';
import { Scale } from 'lucide-react';
import JurisdictionSelect from './JurisdictionSelect';
import CategoryChips from './CategoryChips';
import { scopeSummary } from '../lib/jurisdictions';

interface ScopeBarProps {
  jurisdiction: string;
  categories: string[];
  onJurisdictionChange: (value: string) => void;
  onToggleCategory: (value: string) => void;
  onClearCategories: () => void;
  disabled?: boolean;
}

/**
 * Slim scope bar above the input: pick jurisdiction + categories and see the
 * resolved scope (Decision 7 shows the co-applicable federal layer).
 */
export default function ScopeBar({
  jurisdiction,
  categories,
  onJurisdictionChange,
  onToggleCategory,
  onClearCategories,
  disabled,
}: ScopeBarProps) {
  return (
    <div className="mb-2 rounded-card border border-dark-borderLight bg-dark-card/40 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <JurisdictionSelect value={jurisdiction} onChange={onJurisdictionChange} disabled={disabled} />
        <div className="hidden h-5 w-px bg-dark-borderLight sm:block" />
        <CategoryChips selected={categories} onToggle={onToggleCategory} disabled={disabled} />
        {categories.length > 0 && (
          <button
            type="button"
            onClick={onClearCategories}
            disabled={disabled}
            className="text-xs text-dark-textSecondary underline-offset-2 hover:text-dark-textPrimary hover:underline disabled:opacity-50"
          >
            Clear
          </button>
        )}
      </div>
      <p className="mt-2 flex items-center gap-1.5 font-mono text-xs text-dark-textSecondary/80">
        <Scale size={12} className="text-primary-accent" />
        Scope: {scopeSummary(jurisdiction, categories)}
      </p>
    </div>
  );
}
