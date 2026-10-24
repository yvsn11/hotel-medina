export type Role = 'guest' | 'staff';
export type BookingStatus = 'PENDING' | 'CONFIRMED' | 'CANCELLED' | 'EXPIRED';
export type RoomStatus = 'AVAILABLE' | 'MAINTENANCE';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
}
export interface AuthResponse {
  token: string;
  user: User;
}
export interface Price {
  nights: number;
  nightly_avg: string;
  subtotal: string;
  discount: string;
  tax: string;
  total: string;
  currency: string;
}
export interface RoomTypeInfo {
  id: number;
  label: string;
  description: string;
  capacity: number;
}
export interface AvailabilityItem {
  room_type: RoomTypeInfo;
  available_rooms: number;
  price: Price;
}
export interface AvailabilityResponse {
  from: string;
  to: string;
  guests: number;
  items: AvailabilityItem[];
}
export interface Booking {
  id: number;
  status: BookingStatus;
  check_in: string;
  check_out: string;
  nights: number;
  guests: number;
  room: { id: number; number: string; room_type: { id: number; label: string } };
  expires_at: string | null;
  price: Price;
  payment: { status: string; provider: string; amount: string } | null;
  created_at: string;
}
export interface PayResponse {
  provider: 'stripe' | 'mock';
  client_secret?: string;
  amount: string;
  currency: string;
}
export interface StaffRoom {
  id: number;
  number: string;
  status: RoomStatus;
  room_type: { id: number; label: string; base_price: string; capacity: number };
}
export interface BookingRequest {
  room_type_id: number;
  check_in: string;
  check_out: string;
  guests: number;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');

let token: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setToken(t: string | null) {
  token = t;
}
export function getToken() {
  return token;
}
export function setUnauthorizedHandler(fn: (() => void) | null) {
  unauthorizedHandler = fn;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  /** auth endpoints: a 401 means bad credentials, not an expired session */
  skipUnauthorizedHandler?: boolean;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', ...opts.headers };
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: opts.method ?? 'GET',
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Network error');
  }

  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    const e = (data ?? {}) as { error?: string; message?: string; details?: Record<string, unknown> };
    if (res.status === 401 && token && !opts.skipUnauthorizedHandler) unauthorizedHandler?.();
    throw new ApiError(
      res.status,
      e.error ?? (res.status >= 500 ? 'server_error' : 'unknown_error'),
      e.message ?? `HTTP ${res.status}`,
      e.details ?? {},
    );
  }
  return data as T;
}

export const api = {
  register: (body: { email: string; password: string; full_name: string }) =>
    request<AuthResponse>('/api/auth/register', { method: 'POST', body, skipUnauthorizedHandler: true }),
  login: (body: { email: string; password: string }) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body, skipUnauthorizedHandler: true }),
  searchRooms: (from: string, to: string, guests: number) =>
    request<AvailabilityResponse>(
      `/api/rooms/available?${new URLSearchParams({ from, to, guests: String(guests) })}`,
    ),
  createBooking: (body: BookingRequest, idempotencyKey: string) =>
    request<Booking>('/api/bookings', { method: 'POST', body, headers: { 'Idempotency-Key': idempotencyKey } }),
  listBookings: () => request<{ items: Booking[] }>('/api/bookings'),
  getBooking: (id: number | string) => request<Booking>(`/api/bookings/${id}`),
  cancelBooking: (id: number | string) => request<Booking>(`/api/bookings/${id}`, { method: 'DELETE' }),
  startPayment: (id: number | string) => request<PayResponse>(`/api/bookings/${id}/pay`, { method: 'POST' }),
  confirmMockPayment: (bookingId: number) =>
    request<unknown>('/api/payments/mock/confirm', { method: 'POST', body: { booking_id: bookingId } }),
  listRooms: () => request<{ items: StaffRoom[] }>('/api/rooms'),
  updateRoom: (id: number, body: { number?: string; status?: RoomStatus }) =>
    request<StaffRoom>(`/api/rooms/${id}`, { method: 'PUT', body }),
  updateRoomType: (id: number, body: { base_price?: string; label?: string; description?: string; capacity?: number }) =>
    request<unknown>(`/api/room-types/${id}`, { method: 'PUT', body }),
};
