import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { useAfterAuth } from '../lib/useAfterAuth';
import { useAuth } from '../context/AuthContext';
import { errorMessage } from '../lib/errors';
import { ErrorBox } from '../components/ErrorBox';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const location = useLocation();
  const after = useAfterAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errs = {
    email: !email ? 'required' : !EMAIL_RE.test(email) ? 'email' : null,
    password: !password ? 'required' : null,
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (errs.email || errs.password) return;
    setBusy(true);
    try {
      await login(email.trim(), password);
      after();
    } catch (err) {
      setError(errorMessage(err, t));
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-3xl">{t('auth.loginTitle')}</h1>
      {(location.state as { from?: string } | null)?.from && <p className="mt-2 text-sm text-ink-soft">{t('auth.loginRequired')}</p>}
      <form onSubmit={submit} noValidate className="card mt-6 p-6">
        <label htmlFor="email" className="label">{t('auth.email')}</label>
        <input id="email" type="email" autoComplete="email" className={`field ${touched && errs.email ? 'field-error' : ''}`}
          value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={touched && !!errs.email} aria-describedby="email-err" />
        <p id="email-err" className="min-h-[1.25rem] text-sm text-red-800">{touched && errs.email ? t(`auth.errors.${errs.email}`) : ''}</p>

        <label htmlFor="password" className="label mt-2">{t('auth.password')}</label>
        <input id="password" type="password" autoComplete="current-password" className={`field ${touched && errs.password ? 'field-error' : ''}`}
          value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={touched && !!errs.password} aria-describedby="pw-err" />
        <p id="pw-err" className="min-h-[1.25rem] text-sm text-red-800">{touched && errs.password ? t(`auth.errors.${errs.password}`) : ''}</p>

        <ErrorBox message={error} />
        <button type="submit" className="btn-primary mt-4 w-full" disabled={busy}>{busy ? t('common.loading') : t('auth.loginSubmit')}</button>
        <p className="mt-4 text-sm">
          {t('auth.noAccount')}{' '}
          <Link to="/register" state={location.state} className="font-semibold text-zellige-700 underline">{t('auth.registerLink')}</Link>
        </p>
      </form>
    </div>
  );
}
