import { useTranslation } from 'react-i18next';
import type { BookingStatus, RoomStatus } from '../services/api';

const STYLES: Record<string, string> = {
  PENDING: 'bg-brass-400/25 text-brass-600 border-brass-600',
  CONFIRMED: 'bg-zellige-50 text-zellige-700 border-zellige-600',
  CANCELLED: 'bg-sand-200 text-ink-soft border-sand-400',
  EXPIRED: 'bg-sand-200 text-ink-soft border-sand-400',
  AVAILABLE: 'bg-zellige-50 text-zellige-700 border-zellige-600',
  MAINTENANCE: 'bg-terracotta-50 text-terracotta-700 border-terracotta-600',
};

export function StatusBadge({ status }: { status: BookingStatus | RoomStatus }) {
  const { t } = useTranslation();
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold ${STYLES[status]}`}>
      {t(`status.${status}`)}
    </span>
  );
}
