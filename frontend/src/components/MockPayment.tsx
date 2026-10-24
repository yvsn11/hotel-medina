import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../services/api';
import { errorMessage } from '../lib/errors';
import { useLocale } from '../lib/useLocale';
import { ErrorBox } from './ErrorBox';

export function MockPayment({ bookingId, total, currency, onPaid }: { bookingId: number; total: string; currency: string; onPaid: () => void }) {
  const { t } = useTranslation();
  const { money } = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pay() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.startPayment(bookingId);
      await api.confirmMockPayment(bookingId);
      onPaid();
    } catch (e) {
      setError(errorMessage(e, t));
      setBusy(false);
    }
  }

  return (
    <section className="card p-5" aria-labelledby="pay-title">
      <h2 id="pay-title" className="text-xl">{t('pay.title')}</h2>
      <p className="mt-2 inline-block rounded border border-brass-600 bg-brass-400/20 px-2 py-1 text-sm font-semibold text-brass-600">
        {t('pay.demoBadge')}
      </p>
      <p className="mt-3 max-w-prose text-sm text-ink-soft">{t('pay.demoHelp')}</p>
      <ErrorBox message={error} />
      <button type="button" className="btn-primary mt-4" onClick={() => void pay()} disabled={busy}>
        {busy ? t('pay.processing') : t('pay.demoButton', { amount: money(total, currency) })}
      </button>
    </section>
  );
}
