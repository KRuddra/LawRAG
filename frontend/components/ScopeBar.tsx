'use client';

import React from 'react';
import { Scale } from 'lucide-react';
import CountryToggle from './CountryToggle';
import JurisdictionSelect from './JurisdictionSelect';
import CategoryMenu from './CategoryMenu';
import { CountryCode, scopeSummary } from '../lib/jurisdictions';

interface ScopeBarProps {
  country: CountryCode;
  jurisdiction: string;
  categories: string[];
  onCountryChange: (value: CountryCode) => void;
  onJurisdictionChange: (value: string) => void;
  onToggleCategory: (value: string) => void;
  onClearCategories: () => void;
  disabled?: boolean;
}

/**
 * Compact scope bar: Country -> Jurisdiction -> Categories, plus a live
 * summary that shows the co-applicable federal layer (Decision 7).
 */
export default function ScopeBar({
  country,
  jurisdiction,
  categories,
  onCountryChange,
  onJurisdictionChange,
  onToggleCategory,
  onClearCategories,
  disabled,
}: ScopeBarProps) {
  return (
    <div className="scope-bar">
      <div className="scope-controls">
        <CountryToggle value={country} onChange={onCountryChange} disabled={disabled} />
        <JurisdictionSelect
          country={country}
          value={jurisdiction}
          onChange={onJurisdictionChange}
          disabled={disabled}
        />
        <CategoryMenu
          selected={categories}
          onToggle={onToggleCategory}
          onClear={onClearCategories}
          disabled={disabled}
        />
      </div>
      <p className="scope-summary">
        <Scale size={12} className="text-primary-accent" />
        <span>{scopeSummary(jurisdiction, categories)}</span>
      </p>
    </div>
  );
}
