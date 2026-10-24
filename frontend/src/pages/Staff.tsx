import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { api, type RoomStatus, type StaffRoom } from '../services/api';
import { errorMessage } from '../lib/errors';
import { useLocale } from '../lib/useLocale';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorBox } from '../components/ErrorBox';

const PRICE_RE = /^\d{1,8}(\.\d{1,2})?$/;

function PriceEditor({ typeId, label, initial, onSaved }: { typeId: number; label: string; initial: string; onSaved: (price: string) => void }) {
  const { t } = useTranslation();
  const { money } = useLocale();
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaved(false);
    const v = value.trim().replace(',', '.');
    if (!PRICE_RE.test(v) || parseFloat(v) <= 0) {
      setError(t('staff.priceInvalid'));
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const price = parseFloat(v).toFixed(2);
      await api.updateRoomType(typeId, { base_price: price });
      setValue(price);
      onSaved(price);
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  const id = `price-${typeId}`;
  return (
    <form onSubmit={submit} noValidate className="mt-3 flex flex-wrap items-end gap-3">
      <div>
        <label htmlFor={id} className="label">{t('staff.basePrice', { label })}</label>
        <input id={id} inputMode="decimal" className="field w-40" value={value} onChange={(e) => setValue(e.target.value)} aria-invalid={!!error} aria-describedby={`${id}-msg`} />
      </div>
      <button type="submit" className="btn-secondary" disabled={busy}>{t('common.save')}</button>
      <p id={`${id}-msg`} role="status" aria-live="polite" className={`text-sm ${error ? 'text-red-800' : 'text-zellige-700'}`}>
        {error ?? (saved ? t('staff.saved', { price: money(value) }) : '')}
      </p>
    </form>
  );
}

export default function Staff() {
  const { t } = useTranslation();
  const [rooms, setRooms] = useState<StaffRoom[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listRooms()
      .then((r) => !cancelled && setRooms(r.items))
      .catch((e) => !cancelled && setError(errorMessage(e, t)));
    return () => {
      cancelled = true;
    };
  }, [t]);

  const types = useMemo(() => {
    const map = new Map<number, { type: StaffRoom['room_type']; rooms: StaffRoom[] }>();
    rooms?.forEach((r) => {
      const g = map.get(r.room_type.id) ?? { type: r.room_type, rooms: [] };
      g.rooms.push(r);
      map.set(r.room_type.id, g);
    });
    return [...map.values()];
  }, [rooms]);

  async function toggle(room: StaffRoom) {
    const next: RoomStatus = room.status === 'AVAILABLE' ? 'MAINTENANCE' : 'AVAILABLE';
    setBusyId(room.id);
    setError(null);
    try {
      const updated = await api.updateRoom(room.id, { status: next });
      setRooms((prev) => prev?.map((r) => (r.id === room.id ? { ...r, status: updated.status ?? next } : r)) ?? prev);
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusyId(null);
    }
  }

  function priceSaved(typeId: number, price: string) {
    setRooms((prev) => prev?.map((r) => (r.room_type.id === typeId ? { ...r, room_type: { ...r.room_type, base_price: price } } : r)) ?? prev);
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl">{t('staff.title')}</h1>
      <ErrorBox message={error} />
      {rooms === null && !error && <p className="mt-6" role="status">{t('common.loading')}</p>}
      <div className="mt-6 grid gap-6">
        {types.map(({ type, rooms: list }) => (
          <section key={type.id} className="card p-5" aria-labelledby={`type-${type.id}`}>
            <h2 id={`type-${type.id}`} className="text-2xl">{type.label}</h2>
            <PriceEditor typeId={type.id} label={type.label} initial={type.base_price} onSaved={(p) => priceSaved(type.id, p)} />
            <ul className="mt-4 divide-y divide-sand-300">
              {list.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <span className="font-semibold">{t('staff.room', { number: r.number })}</span>
                  <StatusBadge status={r.status} />
                  <button
                    type="button" className="btn-secondary" disabled={busyId === r.id}
                    onClick={() => void toggle(r)}
                    aria-label={t(r.status === 'AVAILABLE' ? 'staff.setMaintenanceAria' : 'staff.setAvailableAria', { number: r.number })}
                  >
                    {t(r.status === 'AVAILABLE' ? 'staff.setMaintenance' : 'staff.setAvailable')}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
