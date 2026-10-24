import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { AvailabilityItem } from '../services/api';
import { PriceBreakdown } from './PriceBreakdown';

export function RoomCard({ item, search }: { item: AvailabilityItem; search: { from: string; to: string; guests: number } }) {
  const { t } = useTranslation();
  const q = new URLSearchParams({
    room_type_id: String(item.room_type.id),
    check_in: search.from,
    check_out: search.to,
    guests: String(search.guests),
  });
  const headingId = `room-${item.room_type.id}`;
  return (
    <article className="card grid gap-5 p-5 md:grid-cols-[1fr_20rem]" aria-labelledby={headingId}>
      <div>
        <h3 id={headingId} className="text-2xl">{item.room_type.label}</h3>
        <p className="mt-2 max-w-prose leading-relaxed text-ink-soft">{item.room_type.description}</p>
        <p className="mt-3 text-sm">
          {t('results.capacity', { count: item.room_type.capacity })}
        </p>
        <p className="mt-1 text-sm font-semibold text-terracotta-700">
          {t('results.roomsLeft', { count: item.available_rooms })}
        </p>
      </div>
      <div className="flex flex-col justify-between gap-4 rounded-md bg-white p-4">
        <PriceBreakdown price={item.price} />
        <Link to={`/book?${q}`} className="btn-primary" aria-label={t('results.bookAria', { room: item.room_type.label })}>
          {t('results.book')}
        </Link>
      </div>
    </article>
  );
}
