import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiError, type AvailabilityItem } from '../services/api';
import { uuid } from '../lib/format';
import { validateSearch } from '../lib/validation';
import { todayISO } from '../lib/format';
import { errorMessage } from '../lib/errors';
import { useLocale } from '../lib/useLocale';
import { PriceBreakdown } from '../components/PriceBreakdown';
import { ErrorBox } from '../components/ErrorBox';

export default function Book() {
  const { t } = useTranslation();
  const { date } = useLocale();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const roomTypeId = Number(params.get('room_type_id'));
  const checkIn = params.get('check_in') ?? '';
  const checkOut = params.get('check_out') ?? '';
  const guests = Number(params.get('guests'));
  const validSelection =
    Number.isInteger(roomTypeId) && roomTypeId > 0 &&
    Object.keys(validateSearch({ from: checkIn, to: checkOut, guests }, todayISO())).length === 0;

  const [item, setItem] = useState<AvailabilityItem | null>(null);
  const [loading, setLoading] = useState(validSelection);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noAvailability, setNoAvailability] = useState(false);

  // One key per selection (attempt); reused on retry and double click.
  const keyRef = useRef<{ sel: string; key: string } | null>(null);
  const inFlight = useRef(false);
  const selection = `${roomTypeId}|${checkIn}|${checkOut}|${guests}`;

  useEffect(() => {
    if (!validSelection) return;
    let cancelled = false;
    setLoading(true);
    api
      .searchRooms(checkIn, checkOut, guests)
      .then((res) => {
        if (cancelled) return;
        setItem(res.items.find((i) => i.room_type.id === roomTypeId) ?? null);
      })
      .catch((e) => !cancelled && setLoadError(errorMessage(e, t)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection]);

  const changeDatesLink = `/?${new URLSearchParams({ from: checkIn, to: checkOut, guests: String(guests) })}`;

  async function confirm() {
    if (inFlight.current) return;
    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    setNoAvailability(false);
    if (!keyRef.current || keyRef.current.sel !== selection) keyRef.current = { sel: selection, key: uuid() };
    try {
      const booking = await api.createBooking(
        { room_type_id: roomTypeId, check_in: checkIn, check_out: checkOut, guests },
        keyRef.current.key,
      );
      navigate(`/bookings/${booking.id}/pay`, { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'no_availability') setNoAvailability(true);
      else setError(errorMessage(e, t));
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl">{t('book.title')}</h1>

      {!validSelection ? (
        <div className="card mt-6 p-6">
          <p>{t('book.invalidSelection')}</p>
          <Link to="/" className="btn-primary mt-4">{t('hold.backToSearch')}</Link>
        </div>
      ) : loading ? (
        <p className="mt-6" role="status">{t('common.loading')}</p>
      ) : loadError ? (
        <ErrorBox message={loadError} />
      ) : !item ? (
        <div className="card mt-6 p-6" role="alert">
          <p>{t('book.unavailableNow')}</p>
          <Link to={changeDatesLink} className="btn-primary mt-4">{t('book.changeDates')}</Link>
        </div>
      ) : (
        <div className="card mt-6 p-6">
          <h2 className="text-2xl">{item.room_type.label}</h2>
          <p className="mt-1 text-ink-soft">{item.room_type.description}</p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div><dt className="text-ink-soft">{t('search.checkIn')}</dt><dd className="font-semibold">{date(checkIn)}</dd></div>
            <div><dt className="text-ink-soft">{t('search.checkOut')}</dt><dd className="font-semibold">{date(checkOut)}</dd></div>
            <div><dt className="text-ink-soft">{t('search.guests')}</dt><dd className="font-semibold">{guests}</dd></div>
          </dl>
          <div className="mt-5 rounded-md bg-white p-4"><PriceBreakdown price={item.price} /></div>
          <p className="mt-4 text-sm text-ink-soft">{t('book.holdNotice')}</p>

          <div role="alert" aria-live="assertive">
            {noAvailability && (
              <div className="mt-4 rounded-md border border-terracotta-600 bg-terracotta-50 p-3 text-sm">
                <p className="font-semibold">{t('errors.no_availability')}</p>
                <Link to={changeDatesLink} className="btn-secondary mt-3">{t('book.changeDates')}</Link>
              </div>
            )}
          </div>
          <ErrorBox message={error} />

          <div className="mt-6 flex flex-wrap gap-3">
            <button type="button" className="btn-primary" onClick={() => void confirm()} disabled={submitting}>
              {submitting ? t('book.confirming') : t('book.confirm')}
            </button>
            <Link to={changeDatesLink} className="btn-secondary">{t('book.changeDates')}</Link>
          </div>
        </div>
      )}
    </div>
  );
}
