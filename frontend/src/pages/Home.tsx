import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { api, type AvailabilityResponse } from '../services/api';
import { addDaysISO, todayISO } from '../lib/format';
import { MAX_GUESTS, validateSearch } from '../lib/validation';
import { errorMessage } from '../lib/errors';
import { RoomCard } from '../components/RoomCard';
import { ErrorBox } from '../components/ErrorBox';

export default function Home() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const today = todayISO();
  const [from, setFrom] = useState(params.get('from') ?? '');
  const [to, setTo] = useState(params.get('to') ?? '');
  const [guests, setGuests] = useState(Number(params.get('guests') ?? 2) || 2);
  const [touched, setTouched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AvailabilityResponse | null>(null);
  const requestId = useRef(0);

  const errors = validateSearch({ from, to, guests }, today);
  const show = (k: 'from' | 'to' | 'guests') => (touched && errors[k] ? t(`search.errors.${errors[k]}`) : null);

  async function run(f: string, tt: string, g: number) {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const res = await api.searchRooms(f, tt, g);
      if (id === requestId.current) setResult(res);
    } catch (e) {
      if (id === requestId.current) {
        setResult(null);
        setError(errorMessage(e, t));
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  // Restore a previous search from the URL (e.g. "change dates" links).
  const initial = useRef(true);
  useEffect(() => {
    if (!initial.current) return;
    initial.current = false;
    const f = params.get('from');
    const tt = params.get('to');
    if (f && tt && Object.keys(validateSearch({ from: f, to: tt, guests }, today)).length === 0) {
      void run(f, tt, guests);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.keys(errors).length > 0) return;
    setParams({ from, to, guests: String(guests) }, { replace: true });
    void run(from, to, guests);
  }

  return (
    <>
      <section className="zellige-bg px-4 pb-0 pt-12 text-sand-50 md:pt-16">
        <div className="mx-auto max-w-6xl">
          <h1 className="max-w-2xl text-4xl leading-tight text-sand-50 md:text-5xl">{t('hero.title')}</h1>
          <p className="mt-4 max-w-xl text-lg leading-relaxed text-sand-200">{t('hero.subtitle')}</p>

          <form
            onSubmit={onSubmit}
            noValidate
            aria-label={t('search.title')}
            className="mt-10 rounded-t-[2.5rem] border-x-4 border-t-4 border-brass-400 bg-sand-50 px-5 pb-6 pt-8 text-ink shadow-panel md:px-10"
          >
            <h2 className="text-2xl">{t('search.title')}</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-[1fr_1fr_10rem_auto] md:items-start">
              <div>
                <label htmlFor="from" className="label">{t('search.checkIn')}</label>
                <input
                  id="from" type="date" className={`field ${show('from') ? 'field-error' : ''}`}
                  value={from} min={today} required
                  aria-invalid={!!show('from')} aria-describedby="from-err"
                  onChange={(e) => {
                    setFrom(e.target.value);
                    if (e.target.value && (!to || to <= e.target.value)) setTo(addDaysISO(e.target.value, 1));
                  }}
                />
                <p id="from-err" className="mt-1 min-h-[1.25rem] text-sm text-red-800">{show('from')}</p>
              </div>
              <div>
                <label htmlFor="to" className="label">{t('search.checkOut')}</label>
                <input
                  id="to" type="date" className={`field ${show('to') ? 'field-error' : ''}`}
                  value={to} min={from ? addDaysISO(from, 1) : today} required
                  aria-invalid={!!show('to')} aria-describedby="to-err"
                  onChange={(e) => setTo(e.target.value)}
                />
                <p id="to-err" className="mt-1 min-h-[1.25rem] text-sm text-red-800">{show('to')}</p>
              </div>
              <div>
                <label htmlFor="guests" className="label">{t('search.guests')}</label>
                <input
                  id="guests" type="number" inputMode="numeric" min={1} max={MAX_GUESTS}
                  className={`field ${show('guests') ? 'field-error' : ''}`}
                  value={Number.isNaN(guests) ? '' : guests}
                  aria-invalid={!!show('guests')} aria-describedby="guests-err"
                  onChange={(e) => setGuests(e.target.value === '' ? NaN : Number(e.target.value))}
                />
                <p id="guests-err" className="mt-1 min-h-[1.25rem] text-sm text-red-800">{show('guests')}</p>
              </div>
              <div className="md:pt-6">
                <button type="submit" className="btn-primary w-full" disabled={loading}>
                  {loading ? t('search.searching') : t('search.submit')}
                </button>
              </div>
            </div>
          </form>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-10" aria-labelledby="results-title" aria-live="polite" aria-busy={loading}>
        <ErrorBox message={error} />
        {result && (
          <>
            <h2 id="results-title" className="text-2xl">
              {result.items.length > 0 ? t('results.title') : t('results.emptyTitle')}
            </h2>
            {result.items.length === 0 ? (
              <div className="card mt-4 p-6">
                <p className="max-w-prose leading-relaxed">{t('results.emptyBody')}</p>
              </div>
            ) : (
              <div className="mt-4 grid gap-5">
                {result.items.map((item) => (
                  <RoomCard key={item.room_type.id} item={item} search={{ from: result.from, to: result.to, guests: result.guests }} />
                ))}
              </div>
            )}
          </>
        )}
        {!result && !error && !loading && <p className="max-w-prose text-ink-soft">{t('results.intro')}</p>}
      </section>
    </>
  );
}
