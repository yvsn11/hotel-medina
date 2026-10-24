import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import { PriceBreakdown } from '../components/PriceBreakdown';
import { HoldCountdown } from '../components/Countdown';
import { validateSearch } from '../lib/validation';
import { price } from './utils';

describe('PriceBreakdown', () => {
  it('renders every line of the price object in MAD', async () => {
    await i18n.changeLanguage('en');
    render(<PriceBreakdown price={price({ nights: 5, discount: '142.50', subtotal: '2850.00', tax: '150.00', total: '2857.50', nightly_avg: '570.00' })} />);
    const box = screen.getByTestId('price-breakdown');
    expect(box).toHaveTextContent('Nights');
    expect(box).toHaveTextContent('5');
    expect(box).toHaveTextContent(/570\.00/);
    expect(box).toHaveTextContent(/2,850\.00/);
    expect(box).toHaveTextContent(/-.*142\.50/);
    expect(box).toHaveTextContent(/150\.00/);
    expect(box).toHaveTextContent(/2,857\.50/);
    expect(box).toHaveTextContent(/MAD/);
  });

  it('hides the discount row when there is no discount', async () => {
    await i18n.changeLanguage('en');
    render(<PriceBreakdown price={price()} />);
    expect(screen.queryByText('Long-stay discount')).not.toBeInTheDocument();
    expect(screen.getByText('Tourist tax')).toBeInTheDocument();
  });

  it('formats with the active locale', async () => {
    await i18n.changeLanguage('fr');
    render(<PriceBreakdown price={price()} />);
    expect(screen.getByTestId('price-breakdown').textContent).toMatch(/2\s850,00/);
  });
});

describe('validateSearch', () => {
  const today = '2026-10-25';
  it('accepts a valid stay', () => {
    expect(validateSearch({ from: '2026-10-25', to: '2026-10-28', guests: 2 }, today)).toEqual({});
  });
  it('rejects past check-in, inverted dates, long stays and bad guests', () => {
    expect(validateSearch({ from: '2026-10-24', to: '2026-10-28', guests: 2 }, today).from).toBe('from_past');
    expect(validateSearch({ from: '2026-10-28', to: '2026-10-28', guests: 2 }, today).to).toBe('to_before_from');
    expect(validateSearch({ from: '2026-10-25', to: '2026-11-25', guests: 2 }, today).to).toBe('too_long');
    expect(validateSearch({ from: '2026-10-25', to: '2026-11-24', guests: 2 }, today)).toEqual({});
    expect(validateSearch({ from: '2026-10-25', to: '2026-10-26', guests: 7 }, today).guests).toBe('guests_range');
    expect(validateSearch({ from: '2026-10-25', to: '2026-10-26', guests: 0 }, today).guests).toBe('guests_range');
  });
});

describe('HoldCountdown', () => {
  afterEach(() => vi.useRealTimers());

  it('counts down and shows "hold expired" with a way back to search at zero', async () => {
    await i18n.changeLanguage('en');
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-25T10:00:00Z'));
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <HoldCountdown expiresAt="2026-10-25T10:00:03Z" />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('countdown')).toHaveTextContent('00:03');
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByTestId('countdown')).toHaveTextContent('00:02');
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.queryByTestId('countdown')).not.toBeInTheDocument();
    expect(screen.getAllByText('Hold expired').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: 'Back to search' })).toHaveAttribute('href', '/');
  });
});
