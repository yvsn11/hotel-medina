import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api, type Booking } from '../services/api';
import { errorMessage } from '../lib/errors';
import { useLocale } from '../lib/useLocale';
import { todayISO } from '../lib/format';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorBox } from '../components/ErrorBox';

export default function Bookings() {
  const { t } = useTranslation();
  const { date, money } = useLocale();
  const [items, setItems] = useState<Booking[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listBookings()
      .then((r) => !cancelled && setItems(r.items))
      .catch((e) => !cancelled && setError(errorMessage(e, t)));
    return () => {
      cancelled = true;
    };
  }, [t]);

  async function cancel(id: number) {
    setBusyId(id);
    setError(null);
    try {
      const updated = await api.cancelBooking(id);
      setItems((prev) => prev?.map((b) => (b.id === id ? updated : b)) ?? prev);
      setConfirmId(null);
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusyId(null);
    }
  }

  const today = todayISO();

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl">{t('bookings.title')}</h1>
      <ErrorBox message={error} />
      {items === null && !error && <p className="mt-6" role="status">{t('common.loading')}</p>}
      {items?.length === 0 && (
        <div className="card mt-6 p-6">
          <p>{t('bookings.empty')}</p>
          <Link to="/" className="btn-primary mt-4">{t('hold.backToSearch')}</Link>
        </div>
      )}
      <ul className="mt-6 grid gap-4">
        {items?.map((b) => {
          const cancellable = (b.status === 'PENDING' || b.status === 'CONFIRMED') && b.check_in >= today;
          return (
            <li key={b.id} className="card p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-xl">{b.room.room_type.label} <span className="text-base text-ink-soft">#{b.id}</span></h2>
                <StatusBadge status={b.status} />
              </div>
              <p className="mt-2 text-sm">
                {date(b.check_in)} {t('common.to')} {date(b.check_out)} ({t('bookings.nights', { count: b.nights })}, {t('bookings.guests', { count: b.guests })})
              </p>
              <p className="mt-1 text-sm font-semibold">{money(b.price.total, b.price.currency)}</p>
              <div className="mt-4 flex flex-wrap gap-3">
                {b.status === 'PENDING' && (
                  <Link to={`/bookings/${b.id}/pay`} className="btn-primary">{t('bookings.pay')}</Link>
                )}
                {cancellable && confirmId !== b.id && (
                  <button type="button" className="btn-danger" onClick={() => setConfirmId(b.id)}>{t('bookings.cancel')}</button>
                )}
              </div>
              {confirmId === b.id && (
                <div role="alertdialog" aria-labelledby={`cancel-${b.id}`} className="mt-4 rounded-md border border-red-700 bg-red-50 p-4">
                  <p id={`cancel-${b.id}`} className="text-sm font-semibold">{t('bookings.cancelConfirm')}</p>
                  <div className="mt-3 flex gap-3">
                    <button type="button" className="btn-danger" onClick={() => void cancel(b.id)} disabled={busyId === b.id}>
                      {t('bookings.cancelYes')}
                    </button>
                    <button type="button" className="btn-secondary" onClick={() => setConfirmId(null)}>{t('bookings.cancelNo')}</button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
