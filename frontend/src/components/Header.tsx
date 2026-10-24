import { useTranslation } from 'react-i18next';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export function Header() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded px-2 py-2 text-sm font-medium hover:text-brass-400 ${isActive ? 'text-brass-400' : 'text-sand-100'}`;

  return (
    <header className="bg-zellige-800 text-sand-100">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
        <Link to="/" className="font-display text-xl font-semibold tracking-wide text-sand-50">
          Hotel Medina
        </Link>
        <nav aria-label={t('nav.main')} className="flex flex-wrap items-center gap-1">
          <NavLink to="/" end className={link}>{t('nav.search')}</NavLink>
          {user && <NavLink to="/bookings" className={link}>{t('nav.bookings')}</NavLink>}
          {user?.role === 'staff' && <NavLink to="/staff" className={link}>{t('nav.staff')}</NavLink>}
          {user ? (
            <button
              type="button"
              className="rounded px-2 py-2 text-sm font-medium text-sand-100 hover:text-brass-400"
              onClick={() => {
                logout();
                navigate('/');
              }}
            >
              {t('nav.logout')}
            </button>
          ) : (
            <>
              <NavLink to="/login" className={link}>{t('nav.login')}</NavLink>
              <NavLink to="/register" className={link}>{t('nav.register')}</NavLink>
            </>
          )}
          <label className="ml-2 flex items-center gap-2 text-sm">
            <span className="sr-only">{t('nav.language')}</span>
            <select
              value={i18n.language}
              onChange={(e) => void i18n.changeLanguage(e.target.value)}
              className="min-h-[36px] rounded border border-zellige-400 bg-zellige-900 px-2 py-1 text-sand-50"
            >
              <option value="fr">Français</option>
              <option value="en">English</option>
            </select>
          </label>
        </nav>
      </div>
    </header>
  );
}
