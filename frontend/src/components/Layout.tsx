import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Header } from './Header';
import { useAuth } from '../context/AuthContext';

export function Layout() {
  const { t } = useTranslation();
  const { sessionExpired, clearSessionExpired } = useAuth();
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-white focus:p-2">
        {t('nav.skip')}
      </a>
      <Header />
      <div role="status" aria-live="polite">
        {sessionExpired && (
          <div className="bg-brass-400/30 px-4 py-2 text-center text-sm">
            {t('auth.sessionExpired')}{' '}
            <button type="button" className="underline" onClick={clearSessionExpired}>{t('common.dismiss')}</button>
          </div>
        )}
      </div>
      <main id="main" className="flex-1">
        <Outlet />
      </main>
      <footer className="zellige-bg px-4 py-8 text-center text-sm text-sand-200">
        <p className="font-display text-lg text-sand-50">Hotel Medina</p>
        <p>{t('footer.address')}</p>
        <p className="mt-1 text-xs text-sand-300">{t('footer.demo')}</p>
      </footer>
    </div>
  );
}
