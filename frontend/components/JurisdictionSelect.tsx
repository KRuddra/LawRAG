'use client';

import React from 'react';
import * as Select from '@radix-ui/react-select';
import { Check, ChevronDown, Landmark } from 'lucide-react';
import { CountryCode, jurisdictionsForCountry } from '../lib/jurisdictions';
import { cn } from '../lib/cn';

interface JurisdictionSelectProps {
  country: CountryCode;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/** Jurisdiction picker, scoped to the selected country. */
export default function JurisdictionSelect({ country, value, onChange, disabled }: JurisdictionSelectProps) {
  const options = jurisdictionsForCountry(country);

  return (
    <Select.Root value={value} onValueChange={onChange} disabled={disabled}>
      <Select.Trigger
        aria-label="Jurisdiction"
        className={cn(
          'inline-flex items-center gap-2 rounded-full border border-dark-borderMedium bg-dark-bgSecondary px-3 py-1',
          'text-sm text-dark-textPrimary transition-colors',
          'hover:border-primary-accent focus:outline-none focus:ring-1 focus:ring-primary-accent',
          'disabled:opacity-50 disabled:cursor-not-allowed',
        )}
      >
        <Landmark size={14} className="text-primary-accent" />
        <Select.Value />
        <Select.Icon>
          <ChevronDown size={14} className="text-dark-textSecondary" />
        </Select.Icon>
      </Select.Trigger>

      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={6}
          className="z-50 min-w-[12rem] overflow-hidden rounded-lg border border-dark-borderMedium bg-dark-card shadow-xl"
        >
          <Select.Viewport className="p-1">
            {options.map((j) => (
              <Select.Item
                key={j.id}
                value={j.id}
                className={cn(
                  'relative flex cursor-pointer select-none items-center justify-between gap-3 rounded px-3 py-1.5 text-sm outline-none',
                  'text-dark-textSecondary',
                  'data-[highlighted]:bg-primary-accent/10 data-[highlighted]:text-dark-textPrimary',
                  'data-[state=checked]:text-primary-accent',
                )}
              >
                <Select.ItemText>{j.isFederal ? `${j.countryLabel} Federal` : j.label}</Select.ItemText>
                <Select.ItemIndicator>
                  <Check size={14} />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
