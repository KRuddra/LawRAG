/**
 * Jurisdiction + category vocabulary for the scope selector (Stage 6).
 *
 * Mirrors the backend MVP scope (backend/jurisdictions.py, backend/categories.py):
 * US federal, Canada federal, British Columbia. A sub-national jurisdiction also
 * applies its country's federal layer (Decision 7), reflected in `scopeLabel`.
 */

export interface Jurisdiction {
  id: string;
  label: string;
  country: 'US' | 'CA';
  countryLabel: string;
  flag: string;
  isFederal: boolean;
}

export const JURISDICTIONS: Jurisdiction[] = [
  { id: 'us-federal', label: 'Federal', country: 'US', countryLabel: 'United States', flag: '🇺🇸', isFederal: true },
  { id: 'ca-federal', label: 'Federal', country: 'CA', countryLabel: 'Canada', flag: '🇨🇦', isFederal: true },
  { id: 'ca-bc', label: 'British Columbia', country: 'CA', countryLabel: 'Canada', flag: '🇨🇦', isFederal: false },
];

export const DEFAULT_JURISDICTION_ID = 'ca-federal';

export type CountryCode = 'US' | 'CA';

export interface Country {
  code: CountryCode;
  label: string;
  flag: string;
}

export const COUNTRIES: Country[] = [
  { code: 'US', label: 'United States', flag: '🇺🇸' },
  { code: 'CA', label: 'Canada', flag: '🇨🇦' },
];

export const DEFAULT_COUNTRY: CountryCode = 'CA';

/** Jurisdictions within a country, federal first. */
export function jurisdictionsForCountry(country: CountryCode): Jurisdiction[] {
  return JURISDICTIONS.filter((j) => j.country === country).sort(
    (a, b) => Number(b.isFederal) - Number(a.isFederal),
  );
}

export interface Category {
  value: string;
  label: string;
}

/** Controlled vocabulary mirroring backend LawCategory (excluding "other"). */
export const CATEGORIES: Category[] = [
  { value: 'criminal', label: 'Criminal' },
  { value: 'traffic', label: 'Traffic' },
  { value: 'family', label: 'Family' },
  { value: 'property', label: 'Property' },
  { value: 'employment', label: 'Employment' },
  { value: 'tax', label: 'Tax' },
  { value: 'immigration', label: 'Immigration' },
  { value: 'health', label: 'Health' },
  { value: 'environmental', label: 'Environmental' },
  { value: 'commercial', label: 'Commercial' },
  { value: 'constitutional', label: 'Constitutional' },
  { value: 'administrative', label: 'Administrative' },
];

export function getJurisdiction(id: string): Jurisdiction | undefined {
  return JURISDICTIONS.find((j) => j.id === id);
}

/** The federal jurisdiction for a country, if any. */
export function federalFor(country: 'US' | 'CA'): Jurisdiction | undefined {
  return JURISDICTIONS.find((j) => j.country === country && j.isFederal);
}

/**
 * Human-readable applied scope, e.g. "British Columbia + Canada federal" or
 * "United States federal". Mirrors backend resolve_applicable().
 */
export function scopeLabel(jurisdictionId: string): string {
  const j = getJurisdiction(jurisdictionId);
  if (!j) return 'Unknown jurisdiction';
  if (j.isFederal) return `${j.countryLabel} federal`;
  const fed = federalFor(j.country);
  return fed ? `${j.label} + ${j.countryLabel} federal` : j.label;
}

/** Full one-line summary including categories (or "All categories"). */
export function scopeSummary(jurisdictionId: string, categories: string[]): string {
  const cats =
    categories.length === 0
      ? 'All categories'
      : categories
          .map((c) => CATEGORIES.find((x) => x.value === c)?.label ?? c)
          .join(', ');
  return `${scopeLabel(jurisdictionId)} · ${cats}`;
}
