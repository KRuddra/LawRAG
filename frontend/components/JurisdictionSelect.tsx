'use client';

import React from 'react';
import * as Select from '@radix-ui/react-select';
import { Check, ChevronDown, MapPin } from 'lucide-react';
import { JURISDICTIONS, Jurisdiction } from '../lib/jurisdictions';
import { cn } from '../lib/cn';

interface JurisdictionSelectProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

const COUNTRY_ORDER: Array<{ key: Jurisdiction['country']; label: string }> = [
  { key: 'US', label: 'United States' },
  { key: 'CA', label: 'Canada' },
];

function itemLabel(j: Jurisdiction): string {
  return `${j.flag} ${j.isFederal ? `${j.countryLabel} Federal` : j.label}`;
}

export default function JurisdictionSelect({ value, onChange, disabled }: JurisdictionSelectProps) {
  return (
    <Select.Root value={value} onValueChange={onChange} disabled={disabled}>
      <Select.Trigger
        aria-label="Jurisdiction"
        className={cn(
          'inline-flex items-center gap-2 rounded-full border border-dark-borderMedium bg-dark-card px-3 py-1.5',
          'text-sm text-dark-textPrimary transition-colors',
          'hover:border-primary-accent focus:outline-none focus:ring-1 focus:ring-primary-accent',
          'disabled:opacity-50 disabled:cursor-not-allowed',
        )}
      >
        <MapPin size={14} className="text-primary-accent" />
        <Select.Value />
        <Select.Icon>
          <ChevronDown size={14} className="text-dark-textSecondary" />
        </Select.Icon>
      </Select.Trigger>

      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={6}
          className={cn(
            'z-50 min-w-[14rem] overflow-hidden rounded-lg border border-dark-borderMedium',
            'bg-dark-card shadow-xl',
          )}
        >
          <Select.Viewport className="p-1">
            {COUNTRY_ORDER.map(({ key, label }) => {
              const items = JURISDICTIONS.filter((j) => j.country === key);
              if (items.length === 0) return null;
              return (
                <Select.Group key={key}>
                  <Select.Label className="px-3 pb-1 pt-2 text-[11px] uppercase tracking-wide text-dark-textSecondary/60">
                    {label}
                  </Select.Label>
                  {items.map((j) => (
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
                      <Select.ItemText>{itemLabel(j)}</Select.ItemText>
                      <Select.ItemIndicator>
                        <Check size={14} />
                      </Select.ItemIndicator>
                    </Select.Item>
                  ))}
                </Select.Group>
              );
            })}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
