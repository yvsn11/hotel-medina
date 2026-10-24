import { nightsBetween } from './format';

export type SearchErrorCode = 'from_required' | 'to_required' | 'from_past' | 'to_before_from' | 'too_long' | 'guests_range';

export const MAX_NIGHTS = 30;
export const MAX_GUESTS = 6;

/** Mirrors the backend rules in docs/api.md. Returns a map field -> error code. */
export function validateSearch(
  v: { from: string; to: string; guests: number },
  today: string,
): Partial<Record<'from' | 'to' | 'guests', SearchErrorCode>> {
  const errors: Partial<Record<'from' | 'to' | 'guests', SearchErrorCode>> = {};
  if (!v.from) errors.from = 'from_required';
  else if (v.from < today) errors.from = 'from_past';
  if (!v.to) errors.to = 'to_required';
  else if (v.from && v.to <= v.from) errors.to = 'to_before_from';
  else if (v.from && nightsBetween(v.from, v.to) > MAX_NIGHTS) errors.to = 'too_long';
  if (!Number.isInteger(v.guests) || v.guests < 1 || v.guests > MAX_GUESTS) errors.guests = 'guests_range';
  return errors;
}
