import { describe, it, expect } from 'vitest';
import {
  JURISDICTIONS,
  CATEGORIES,
  federalFor,
  getJurisdiction,
  scopeLabel,
  scopeSummary,
} from './jurisdictions';

describe('jurisdictions', () => {
  it('has the three MVP jurisdictions', () => {
    expect(JURISDICTIONS.map((j) => j.id).sort()).toEqual(
      ['ca-bc', 'ca-federal', 'us-federal'],
    );
  });

  it('resolves the federal jurisdiction per country', () => {
    expect(federalFor('CA')?.id).toBe('ca-federal');
    expect(federalFor('US')?.id).toBe('us-federal');
  });

  it('getJurisdiction returns undefined for unknown ids', () => {
    expect(getJurisdiction('ca-on')).toBeUndefined();
  });
});

describe('scopeLabel (mirrors backend federal overlap)', () => {
  it('federal jurisdiction shows only itself', () => {
    expect(scopeLabel('us-federal')).toBe('United States federal');
    expect(scopeLabel('ca-federal')).toBe('Canada federal');
  });

  it('provincial jurisdiction includes the co-applicable federal layer', () => {
    expect(scopeLabel('ca-bc')).toBe('British Columbia + Canada federal');
  });

  it('never leaks US into a BC scope label', () => {
    expect(scopeLabel('ca-bc')).not.toContain('United States');
  });
});

describe('scopeSummary', () => {
  it('shows "All categories" when none are selected', () => {
    expect(scopeSummary('ca-bc', [])).toBe('British Columbia + Canada federal · All categories');
  });

  it('lists selected category labels', () => {
    expect(scopeSummary('us-federal', ['criminal', 'traffic'])).toBe(
      'United States federal · Criminal, Traffic',
    );
  });

  it('every category has a label', () => {
    expect(CATEGORIES.every((c) => c.label.length > 0)).toBe(true);
  });
});
