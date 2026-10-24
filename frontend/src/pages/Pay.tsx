import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api, type Booking } from '../services/api';
import { errorMessage } from '../lib/errors';
import { useLocale } from '../lib/useLocale';
import { useCountdown } from '../lib/useCountdown';
import { HoldCountdown } from '../components/Countdown';
import { PriceBreakdown } from '../components/PriceBreakdown';
import { StatusBadge } from '../components/StatusBadge';
import { MockPayment } from '../components/MockPayment';
import { ErrorBox } from '../components/ErrorBox';

const StripePayment = lazy(() => import('../components/StripePayment'));

const POLL_MS = import.meta.env.MODE === 'test' ? 5 : 1500;
const POLL_TRIES = 10;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function Pay() {
  const { id } = useParams();
  const { t } = useTranslation();
  const { date } = useLocale();
  const [search] = useSearchParams();
  const stripeKey = (import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY as string | undefined) || '';

  const [booking, setBooking] = useState<Booking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [stillPending, setStillPending] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const remaining = useCountdown(booking?.status === 'PENDING' ? booking.expires_at : null);
  const expired = remaining === 0;

  const poll = useCallback(async () => {
    setConfirming(true);
    setStillPending(false);
    try {
      for (let i = 0; i < POLL_TRIES; i++) {
        const b = await api.getBooking(id!);
        if (!mounted.current) return;
        setBooking(b);
        if (b.status !== 'PENDING') return;
        await sleep(POLL_MS);
      }
      if (mounted.current) setStillPending(true);
    } catch (e) {
      if (mounted.current) setError(errorMessage(e, t));
    } finally {
      if (mounted.current) setConfirming(false);
    }
  }, [id, t]);

  useEffect(() => {
    let cancelled = false;
    api
      .getBooking(id!)
      .then((b) => {
        if (cancelled) return;
        setBooking(b);
        // Returning from a Stripe redirect: webhooks are asynchronous, so poll.
        if (b.status === 'PENDING' && search.get('redirect_status') === 'succeeded') void poll();
      })
      .catch((e) => !cancelled && setError(errorMessage(e, t)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) return <p className="mx-auto max-w-3xl px-4 py-10" role="status">{t('common.loading')}</p>;
  if (!booking) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <ErrorBox message={error ?? t('errors.not_found')} />
        <Link to="/bookings" className="btn-secondary mt-4">{t('nav.bookings')}</Link>
      </div>
    );
  }

  const summary = (
    <div className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-2xl">{booking.room.room_type.label}</h2>
        <StatusBadge status={booking.status} />
      </div>
      <p className="mt-1 text-sm text-ink-soft">{t('bookings.room', { number: booking.room.number })}</p>
      <p className="mt-2 text-sm">
        {date(booking.check_in)} {t('common.to')} {date(booking.check_out)} ({t('bookings.nights', { count: booking.nights })}, {t('bookings.guests', { count: booking.guests })})
      </p>
      <div className="mt-4 rounded-md bg-white p-4"><PriceBreakdown price={booking.price} /></div>
    </div>
  );

  const confirmedView = (
    <div className="card border-zellige-600 p-6" role="status">
      <h2 className="text-2xl text-zellige-700">{t('pay.confirmedTitle')}</h2>
      <p className="mt-2 max-w-prose">{t('pay.confirmedBody', { id: booking.id })}</p>
      <Link to="/bookings" className="btn-primary mt-4">{t('pay.viewBookings')}</Link>
    </div>
  );

  let action;
  if (booking.status === 'CONFIRMED') action = confirmedView;
  else if (booking.status === 'CANCELLED' || booking.status === 'EXPIRED') {
    action = (
      <div className="card p-6" role="status">
        <p>{t(booking.status === 'EXPIRED' ? 'pay.statusExpired' : 'pay.statusCancelled')}</p>
        <Link to="/" className="btn-primary mt-4">{t('hold.backToSearch')}</Link>
      </div>
    );
  } else if (confirming) {
    action = <p className="card p-6" role="status">{t('pay.confirming')}</p>;
  } else if (stillPending) {
    action = (
      <div className="card p-6" role="status">
        <p>{t('pay.stillPending')}</p>
        <button type="button" className="btn-secondary mt-4" onClick={() => void poll()}>{t('pay.checkAgain')}</button>
      </div>
    );
  } else if (!expired) {
    action = stripeKey ? (
      <Suspense fallback={<p role="status">{t('common.loading')}</p>}>
        <StripePayment publishableKey={stripeKey} bookingId={booking.id} total={booking.price.total} currency={booking.price.currency} onPaid={() => void poll()} />
      </Suspense>
    ) : (
      <MockPayment bookingId={booking.id} total={booking.price.total} currency={booking.price.currency} onPaid={() => void poll()} />
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl">{t('pay.pageTitle')}</h1>
      <div className="mt-6 grid gap-5">
        {booking.status === 'PENDING' && booking.expires_at && <HoldCountdown expiresAt={booking.expires_at} />}
        {summary}
        <ErrorBox message={error} />
        {action}
      </div>
    </div>
  );
}
