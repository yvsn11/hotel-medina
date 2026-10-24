import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { booking, dates, GUEST, mockApi, renderApp, seedSession, STAFF, standardItem } from './utils';

afterEach(() => {
  vi.unstubAllGlobals();
});

function bookUrl() {
  const d = dates();
  return `/book?room_type_id=1&check_in=${d.from}&check_out=${d.to}&guests=2`;
}
const availability = () => ({ from: dates().from, to: dates().to, guests: 2, items: [standardItem()] });

describe('search form', () => {
  it('shows validation errors and does not call the API when dates are missing', async () => {
    const api = mockApi([]);
    renderApp('/');
    await userEvent.click(screen.getByRole('button', { name: 'Search rooms' }));
    expect(screen.getByText('Choose a check-in date.')).toBeInTheDocument();
    expect(screen.getByText('Choose a check-out date.')).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it('rejects check-out not after check-in and stays over 30 nights', async () => {
    const api = mockApi([]);
    renderApp('/');
    const d = dates();
    fireEvent.change(screen.getByLabelText('Check-in'), { target: { value: d.from } });
    fireEvent.change(screen.getByLabelText('Check-out'), { target: { value: d.from } });
    await userEvent.click(screen.getByRole('button', { name: 'Search rooms' }));
    expect(screen.getByText('Check-out must be after check-in.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Check-out'), { target: { value: '2099-01-01' } });
    await userEvent.click(screen.getByRole('button', { name: 'Search rooms' }));
    expect(screen.getByText('A stay can last 30 nights at most.')).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it('searches and renders a card per room type with price and Book link', async () => {
    const api = mockApi([{ method: 'GET', path: '/api/rooms/available', handler: { body: availability() } }]);
    renderApp('/');
    const d = dates();
    fireEvent.change(screen.getByLabelText('Check-in'), { target: { value: d.from } });
    fireEvent.change(screen.getByLabelText('Check-out'), { target: { value: d.to } });
    await userEvent.click(screen.getByRole('button', { name: 'Search rooms' }));

    const card = await screen.findByRole('article');
    expect(within(card).getByText('Standard')).toBeInTheDocument();
    expect(within(card).getByText('3 rooms left')).toBeInTheDocument();
    expect(within(card).getByText('Sleeps up to 2 guests')).toBeInTheDocument();
    expect(within(card).getByTestId('price-breakdown')).toHaveTextContent(/2,940\.00/);
    const link = within(card).getByRole('link', { name: 'Book Standard' });
    expect(link).toHaveAttribute('href', expect.stringContaining('/book?room_type_id=1'));
    expect(api.calls[0].path).toBe(`/api/rooms/available?from=${d.from}&to=${d.to}&guests=2`);
  });

  it('shows a friendly empty state when nothing is available', async () => {
    mockApi([{ method: 'GET', path: '/api/rooms/available', handler: { body: { ...availability(), items: [] } } }]);
    renderApp('/');
    const d = dates();
    fireEvent.change(screen.getByLabelText('Check-in'), { target: { value: d.from } });
    fireEvent.change(screen.getByLabelText('Check-out'), { target: { value: d.to } });
    await userEvent.click(screen.getByRole('button', { name: 'Search rooms' }));
    expect(await screen.findByText('No room available')).toBeInTheDocument();
    expect(screen.getByText(/Try moving your stay/)).toBeInTheDocument();
  });
});

describe('booking flow', () => {
  it('sends an Idempotency-Key and reuses the same key on a second attempt', async () => {
    seedSession(GUEST);
    let n = 0;
    const api = mockApi([
      { method: 'GET', path: '/api/rooms/available', handler: { body: availability() } },
      {
        method: 'POST', path: '/api/bookings',
        handler: () => (++n === 1 ? { status: 500, body: { error: 'server_error', message: 'boom' } } : { status: 201, body: booking() }),
      },
      { method: 'GET', path: '/api/bookings/12', handler: { body: booking() } },
    ]);
    renderApp(bookUrl());
    const confirm = await screen.findByRole('button', { name: 'Confirm and continue to payment' });
    await userEvent.click(confirm);
    await screen.findByText(/server had a problem/);
    await userEvent.click(screen.getByRole('button', { name: 'Confirm and continue to payment' }));
    await screen.findByRole('heading', { name: 'Payment' });

    const posts = api.callsTo('POST', '/api/bookings');
    expect(posts).toHaveLength(2);
    const k1 = posts[0].headers['Idempotency-Key'];
    expect(k1).toMatch(/^[0-9a-f-]{36}$/);
    expect(posts[1].headers['Idempotency-Key']).toBe(k1);
    expect(posts[0].headers.Authorization).toBe('Bearer tok-guest');
    expect(posts[0].body).toEqual({ room_type_id: 1, check_in: dates().from, check_out: dates().to, guests: 2 });
  });

  it('a double click sends a single request', async () => {
    seedSession(GUEST);
    const api = mockApi([
      { method: 'GET', path: '/api/rooms/available', handler: { body: availability() } },
      { method: 'POST', path: '/api/bookings', handler: { status: 201, body: booking() } },
      { method: 'GET', path: '/api/bookings/12', handler: { body: booking() } },
    ]);
    renderApp(bookUrl());
    const confirm = await screen.findByRole('button', { name: 'Confirm and continue to payment' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await screen.findByRole('heading', { name: 'Payment' });
    expect(api.callsTo('POST', '/api/bookings')).toHaveLength(1);
  });

  it('shows a clear message and a change-dates path on 409 no_availability', async () => {
    seedSession(GUEST);
    mockApi([
      { method: 'GET', path: '/api/rooms/available', handler: { body: availability() } },
      { method: 'POST', path: '/api/bookings', handler: { status: 409, body: { error: 'no_availability', message: 'x', details: {} } } },
    ]);
    renderApp(bookUrl());
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm and continue to payment' }));
    const alert = await screen.findByText(/last room of this type was just taken/);
    expect(alert).toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: 'Change dates' });
    expect(links[0]).toHaveAttribute('href', expect.stringContaining(`from=${dates().from}`));
  });
});

describe('payment page (mock mode)', () => {
  it('runs pay -> mock confirm, then polls until the booking is CONFIRMED', async () => {
    seedSession(GUEST);
    let gets = 0;
    let confirmed = false;
    const api = mockApi([
      {
        method: 'GET', path: '/api/bookings/12',
        handler: () => {
          gets++;
          // first load PENDING, then still PENDING once (async webhook), then CONFIRMED
          return { body: booking({ status: confirmed && gets >= 4 ? 'CONFIRMED' : 'PENDING' }) };
        },
      },
      { method: 'POST', path: '/api/bookings/12/pay', handler: { body: { provider: 'mock', amount: '2940.00', currency: 'MAD' } } },
      { method: 'POST', path: '/api/payments/mock/confirm', handler: () => { confirmed = true; return { body: { status: 'ok' } }; } },
    ]);
    renderApp('/bookings/12/pay');
    expect(await screen.findByText('Demo payment')).toBeInTheDocument();
    expect(screen.getByTestId('countdown')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Pay .*\(demo\)/ }));
    expect(await screen.findByText('Booking confirmed')).toBeInTheDocument();
    expect(api.callsTo('POST', '/api/bookings/12/pay')).toHaveLength(1);
    const confirm = api.callsTo('POST', '/api/payments/mock/confirm');
    expect(confirm).toHaveLength(1);
    expect(confirm[0].body).toEqual({ booking_id: 12 });
    expect(gets).toBeGreaterThanOrEqual(4);
  });

  it('shows hold expired and no pay button when expires_at is in the past', async () => {
    seedSession(GUEST);
    mockApi([{ method: 'GET', path: '/api/bookings/12', handler: { body: booking({ expires_at: new Date(Date.now() - 1000).toISOString() }) } }]);
    renderApp('/bookings/12/pay');
    expect((await screen.findAllByText('Hold expired')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Pay/ })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to search' })).toBeInTheDocument();
  });
});

describe('my bookings', () => {
  it('lists bookings with badges, links PENDING to pay, and cancels after confirmation', async () => {
    seedSession(GUEST);
    const api = mockApi([
      { method: 'GET', path: '/api/bookings', handler: { body: { items: [booking(), booking({ id: 13, status: 'CONFIRMED' })] } } },
      { method: 'DELETE', path: '/api/bookings/13', handler: { body: booking({ id: 13, status: 'CANCELLED' }) } },
    ]);
    renderApp('/bookings');
    expect(await screen.findByText('Awaiting payment')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Pay now' })).toHaveAttribute('href', '/bookings/12/pay');
    const cancelButtons = screen.getAllByRole('button', { name: 'Cancel booking' });
    await userEvent.click(cancelButtons[1]);
    expect(api.callsTo('DELETE', '/api/bookings/13')).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: 'Yes, cancel it' }));
    expect(await screen.findByText('Cancelled')).toBeInTheDocument();
    expect(api.callsTo('DELETE', '/api/bookings/13')).toHaveLength(1);
  });

  it('logs out cleanly on a 401 and sends the user to /login', async () => {
    seedSession(GUEST);
    mockApi([{ method: 'GET', path: '/api/bookings', handler: { status: 401, body: { error: 'unauthorized', message: 'expired' } } }]);
    renderApp('/bookings');
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
    expect(screen.getByText(/Your session has ended/)).toBeInTheDocument();
    expect(window.localStorage.getItem('medina.auth')).toBeNull();
  });
});

describe('auth guards', () => {
  it('redirects /book to /login when logged out and returns to the selection after login', async () => {
    const api = mockApi([
      { method: 'GET', path: '/api/rooms/available', handler: { body: availability() } },
      { method: 'POST', path: '/api/auth/login', handler: { body: { token: 'abc', user: GUEST } } },
    ]);
    renderApp(bookUrl());
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
    expect(screen.getByText(/Your selection is kept/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Email'), 'guest@demo.test');
    await userEvent.type(screen.getByLabelText('Password'), 'demo1234');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('heading', { name: 'Review your booking' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Standard' })).toBeInTheDocument();
    expect(api.callsTo('POST', '/api/auth/login')[0].body).toEqual({ email: 'guest@demo.test', password: 'demo1234' });
    expect(JSON.parse(window.localStorage.getItem('medina.auth')!).token).toBe('abc');
  });

  it('shows server errors on the login form', async () => {
    mockApi([{ method: 'POST', path: '/api/auth/login', handler: { status: 401, body: { error: 'unauthorized', message: 'bad' } } }]);
    renderApp('/login');
    await userEvent.type(screen.getByLabelText('Email'), 'a@b.co');
    await userEvent.type(screen.getByLabelText('Password'), 'wrongpass');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByText(/Wrong email or password/)).toBeInTheDocument();
  });

  it('validates the register form client-side', async () => {
    const api = mockApi([]);
    renderApp('/register');
    await userEvent.type(screen.getByLabelText('Password'), 'short');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(screen.getByText('Use at least 8 characters.')).toBeInTheDocument();
    expect(screen.getAllByText('This field is required.')).toHaveLength(2);
    expect(api.calls).toHaveLength(0);
  });

  it('redirects /staff to /login when logged out', async () => {
    mockApi([]);
    renderApp('/staff');
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
  });

  it('redirects a guest away from /staff to the home page', async () => {
    seedSession(GUEST);
    const api = mockApi([]);
    renderApp('/staff');
    expect(await screen.findByRole('heading', { name: 'Find your room' })).toBeInTheDocument();
    expect(api.callsTo('GET', '/api/rooms')).toHaveLength(0);
  });

  it('lets staff list rooms, toggle status and edit a base price', async () => {
    seedSession(STAFF);
    const room = { id: 1, number: '101', status: 'AVAILABLE', room_type: { id: 1, label: 'Standard', base_price: '700.00', capacity: 2 } };
    const api = mockApi([
      { method: 'GET', path: '/api/rooms', handler: { body: { items: [room] } } },
      { method: 'PUT', path: '/api/rooms/1', handler: (c) => ({ body: { ...room, ...(c.body as object) } }) },
      { method: 'PUT', path: '/api/room-types/1', handler: { body: {} } },
    ]);
    renderApp('/staff');
    await userEvent.click(await screen.findByRole('button', { name: 'Set room 101 to maintenance' }));
    expect(await screen.findByRole('button', { name: 'Set room 101 to available' })).toBeInTheDocument();
    expect(api.callsTo('PUT', '/api/rooms/1')[0].body).toEqual({ status: 'MAINTENANCE' });

    const input = screen.getByLabelText(/Standard base price/);
    await userEvent.clear(input);
    await userEvent.type(input, 'abc');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByText(/positive amount/)).toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, '750');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.callsTo('PUT', '/api/room-types/1')).toHaveLength(1));
    expect(api.callsTo('PUT', '/api/room-types/1')[0].body).toEqual({ base_price: '750.00' });
  });
});

describe('language switching', () => {
  it('switches between French and English and persists the choice', async () => {
    mockApi([]);
    renderApp('/', 'fr');
    expect(screen.getByRole('heading', { name: 'Trouvez votre chambre' })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Langue'), 'en');
    expect(await screen.findByRole('heading', { name: 'Find your room' })).toBeInTheDocument();
    expect(window.localStorage.getItem('medina.lang')).toBe('en');
    expect(document.documentElement.lang).toBe('en');
  });
});
