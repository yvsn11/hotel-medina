import { useTranslation } from 'react-i18next';
import { intlLocale } from '../i18n';
import { formatDate, formatDateTime, formatMoney } from './format';

export function useLocale() {
  const { i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  return {
    locale,
    date: (s: string) => formatDate(s, locale),
    dateTime: (s: string) => formatDateTime(s, locale),
    money: (a: string | number, c = 'MAD') => formatMoney(a, c, locale),
  };
}
