import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import fr from './fr.json';
import en from './en.json';
import { safeStorageGet, safeStorageSet } from '../lib/format';

export const LANG_KEY = 'medina.lang';
export type Lang = 'fr' | 'en';

function initialLang(): Lang {
  const saved = safeStorageGet(LANG_KEY);
  if (saved === 'fr' || saved === 'en') return saved;
  if (typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('en')) return 'en';
  return 'fr';
}

void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr }, en: { translation: en } },
  lng: initialLang(),
  fallbackLng: 'fr',
  supportedLngs: ['fr', 'en'],
  interpolation: { escapeValue: false },
});

if (typeof document !== 'undefined') document.documentElement.lang = i18n.language;
i18n.on('languageChanged', (lng) => {
  safeStorageSet(LANG_KEY, lng);
  if (typeof document !== 'undefined') document.documentElement.lang = lng;
});

export function intlLocale(lng: string): string {
  return lng === 'en' ? 'en-GB' : 'fr-FR';
}

export default i18n;
