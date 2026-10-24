import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { formatClock, useCountdown } from '../lib/useCountdown';

export function HoldCountdown({ expiresAt }: { expiresAt: string }) {
  const { t } = useTranslation();
  const remaining = useCountdown(expiresAt);
  const expired = remaining === 0;
  // Announce once a minute (and on expiry) rather than every second.
  const announce = remaining === null ? '' : expired ? t('hold.expired') : t('hold.minutesLeft', { count: Math.ceil(remaining / 60) });

  return (
    <div className={`rounded-md border p-4 ${expired ? 'border-terracotta-600 bg-terracotta-50' : 'border-zellige-600 bg-zellige-50'}`}>
      {expired ? (
        <div>
          <p className="font-display text-xl text-terracotta-700">{t('hold.expired')}</p>
          <p className="mt-1 text-sm">{t('hold.expiredHelp')}</p>
          <Link to="/" className="btn-primary mt-3">{t('hold.backToSearch')}</Link>
        </div>
      ) : (
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-sm font-semibold">{t('hold.label')}</span>
          <span role="timer" aria-live="off" className="font-display text-3xl tabular-nums text-zellige-800" data-testid="countdown">
            {formatClock(remaining ?? 0)}
          </span>
        </div>
      )}
      <p className="sr-only" aria-live="polite" role="status">{announce}</p>
    </div>
  );
}
