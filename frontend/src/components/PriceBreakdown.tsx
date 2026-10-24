import { useTranslation } from 'react-i18next';
import type { Price } from '../services/api';
import { useLocale } from '../lib/useLocale';

export function PriceBreakdown({ price }: { price: Price }) {
  const { t } = useTranslation();
  const { money } = useLocale();
  const c = price.currency;
  const hasDiscount = parseFloat(price.discount) > 0;
  return (
    <dl className="text-sm" data-testid="price-breakdown">
      <Row label={t('price.nights')} value={String(price.nights)} />
      <Row label={t('price.nightlyAvg')} value={money(price.nightly_avg, c)} />
      <Row label={t('price.subtotal')} value={money(price.subtotal, c)} />
      {hasDiscount && <Row label={t('price.discount')} value={`-${money(price.discount, c)}`} accent />}
      <Row label={t('price.tax')} value={money(price.tax, c)} />
      <div className="mt-2 flex items-baseline justify-between border-t border-sand-300 pt-2">
        <dt className="font-semibold text-zellige-800">{t('price.total')}</dt>
        <dd className="font-display text-xl font-semibold text-zellige-800">{money(price.total, c)}</dd>
      </div>
    </dl>
  );
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex justify-between py-0.5">
      <dt className="text-ink-soft">{label}</dt>
      <dd className={accent ? 'font-medium text-terracotta-700' : 'font-medium'}>{value}</dd>
    </div>
  );
}
