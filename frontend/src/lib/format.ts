/** Parse YYYY-MM-DD as a local date (avoids UTC off-by-one). */
export function parseISODate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function toISODate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function todayISO(now: Date = new Date()): string {
  return toISODate(now);
}

export function addDaysISO(s: string, days: number): string {
  const d = parseISODate(s);
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

export function nightsBetween(from: string, to: string): number {
  const a = parseISODate(from);
  const b = parseISODate(to);
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

export function formatDate(s: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(parseISODate(s));
}

export function formatDateTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
}

export function formatMoney(amount: string | number, currency: string, locale: string): string {
  const n = typeof amount === 'number' ? amount : parseFloat(amount);
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(Number.isNaN(n) ? 0 : n);
}

export function uuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function safeStorageGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
export function safeStorageSet(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}
export function safeStorageRemove(key: string) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* storage unavailable */
  }
}
