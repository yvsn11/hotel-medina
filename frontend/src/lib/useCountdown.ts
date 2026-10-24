import { useEffect, useState } from 'react';

/** Seconds remaining until `expiresAt` (ISO). null when no expiry. Ticks every second. */
export function useCountdown(expiresAt: string | null | undefined): number | null {
  const target = expiresAt ? new Date(expiresAt).getTime() : null;
  const calc = () => (target === null ? null : Math.max(0, Math.ceil((target - Date.now()) / 1000)));
  const [remaining, setRemaining] = useState<number | null>(calc);

  useEffect(() => {
    setRemaining(calc());
    if (target === null) return;
    const id = window.setInterval(() => {
      const r = Math.max(0, Math.ceil((target - Date.now()) / 1000));
      setRemaining(r);
      if (r === 0) window.clearInterval(id);
    }, 1000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  return remaining;
}

export function formatClock(total: number): string {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
