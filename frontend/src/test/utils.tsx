import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import i18n from '../i18n';
import App from '../App';
import { AuthProvider } from '../context/AuthContext';
import { addDaysISO, todayISO } from '../lib/format';
import type { AvailabilityItem, Booking, Price, User } from '../services/api';

export interface Call {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}
export interface MockResponse {
  status?: number;
  body?: unknown;
}
type Handler = MockResponse | ((call: Call) => MockResponse);
interface Route {
  method: string;
  path: string;
  handler: Handler;
}

/** Replaces global fetch with a route table. Paths match on pathname (query ignored) unless they contain "?". */
export function mockApi(routes: Route[]) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost');
    const method = (init?.method ?? 'GET').toUpperCase();
    const headers = (init?.headers ?? {}) as Record<string, string>;
    const call: Call = {
      method,
      path: url.pathname + url.search,
      headers,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    const route = routes.find((r) => r.method === method && (r.path.includes('?') ? call.path === r.path : url.pathname === r.path));
    if (!route) return new Response(JSON.stringify({ error: 'not_found', message: 'no route' }), { status: 404 });
    const res = typeof route.handler === 'function' ? route.handler(call) : route.handler;
    return new Response(JSON.stringify(res.body ?? {}), { status: res.status ?? 200 });
  });
  vi.stubGlobal('fetch', fn);
  return { calls, fn, callsTo: (method: string, path: string) => calls.filter((c) => c.method === method && c.path.split('?')[0] === path) };
}

export const GUEST: User = { id: 1, email: 'guest@demo.test', full_name: 'Demo Guest', role: 'guest' };
export const STAFF: User = { id: 2, email: 'staff@demo.test', full_name: 'Demo Staff', role: 'staff' };

export function seedSession(user: User) {
  window.localStorage.setItem('medina.auth', JSON.stringify({ token: 'tok-' + user.role, user }));
}

export function renderApp(path = '/', lang: 'en' | 'fr' = 'en') {
  void i18n.changeLanguage(lang);
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

export const price = (over: Partial<Price> = {}): Price => ({
  nights: 3, nightly_avg: '950.00', subtotal: '2850.00', discount: '0.00', tax: '90.00', total: '2940.00', currency: 'MAD', ...over,
});

export const standardItem = (over: Partial<AvailabilityItem> = {}): AvailabilityItem => ({
  room_type: { id: 1, label: 'Standard', description: 'A cosy room on the courtyard.', capacity: 2 },
  available_rooms: 3,
  price: price(),
  ...over,
});

export const dates = () => {
  const from = addDaysISO(todayISO(), 10);
  return { from, to: addDaysISO(from, 3) };
};

export const booking = (over: Partial<Booking> = {}): Booking => {
  const d = dates();
  return {
    id: 12, status: 'PENDING', check_in: d.from, check_out: d.to, nights: 3, guests: 2,
    room: { id: 5, number: '101', room_type: { id: 1, label: 'Standard' } },
    expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
    price: price(), payment: null, created_at: new Date().toISOString(), ...over,
  };
};
