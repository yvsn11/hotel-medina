import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { loadStripe } from '@stripe/stripe-js';
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js';
import { api } from '../services/api';
import { errorMessage } from '../lib/errors';
import { useLocale } from '../lib/useLocale';
import { ErrorBox } from './ErrorBox';

function CheckoutForm({ total, currency, bookingId, onPaid }: { total: string; currency: string; bookingId: number; onPaid: () => void }) {
  const { t } = useTranslation();
  const { money } = useLocale();
  const stripe = useStripe();
  const elements = useElements();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!stripe || !elements || busy) return;
    setBusy(true);
    setError(null);
    const { error: err } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: `${window.location.origin}/bookings/${bookingId}/pay` },
      redirect: 'if_required',
    });
    if (err) {
      setError(err.message ?? t('errors.generic'));
      setBusy(false);
    } else {
      onPaid();
    }
  }

  return (
    <form onSubmit={submit}>
      <PaymentElement />
      <ErrorBox message={error} />
      <button type="submit" className="btn-primary mt-4" disabled={!stripe || busy}>
        {busy ? t('pay.processing') : t('pay.button', { amount: money(total, currency) })}
      </button>
    </form>
  );
}

export default function StripePayment({ publishableKey, bookingId, total, currency, onPaid }: { publishableKey: string; bookingId: number; total: string; currency: string; onPaid: () => void }) {
  const { t } = useTranslation();
  const stripePromise = useMemo(() => loadStripe(publishableKey), [publishableKey]);
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api
      .startPayment(bookingId)
      .then((r) => (r.client_secret ? setSecret(r.client_secret) : setError(t('errors.generic'))))
      .catch((e) => setError(errorMessage(e, t)));
  }, [bookingId, t]);

  return (
    <section className="card p-5" aria-labelledby="pay-title">
      <h2 id="pay-title" className="text-xl">{t('pay.title')}</h2>
      <p className="mt-2 text-sm text-ink-soft">{t('pay.testHint')}</p>
      <ErrorBox message={error} />
      {secret ? (
        <div className="mt-4">
          <Elements stripe={stripePromise} options={{ clientSecret: secret }}>
            <CheckoutForm total={total} currency={currency} bookingId={bookingId} onPaid={onPaid} />
          </Elements>
        </div>
      ) : (
        !error && <p className="mt-4" role="status">{t('common.loading')}</p>
      )}
    </section>
  );
}
