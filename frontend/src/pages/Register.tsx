import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { errorMessage } from '../lib/errors';
import { ErrorBox } from '../components/ErrorBox';
import { useAfterAuth } from '../lib/useAfterAuth';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Register() {
  const { t } = useTranslation();
  const { register } = useAuth();
  const location = useLocation();
  const after = useAfterAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errs = {
    name: !name.trim() ? 'required' : null,
    email: !email ? 'required' : !EMAIL_RE.test(email) ? 'email' : null,
    password: !password ? 'required' : password.length < 8 ? 'short' : null,
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (errs.name || errs.email || errs.password) return;
    setBusy(true);
    try {
      await register(email.trim(), password, name.trim());
      after();
    } catch (err) {
      setError(errorMessage(err, t));
      setBusy(false);
    }
  }

  const fieldErr = (k: 'name' | 'email' | 'password') => (touched && errs[k] ? t(`auth.errors.${errs[k]}`) : '');

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-3xl">{t('auth.registerTitle')}</h1>
      <form onSubmit={submit} noValidate className="card mt-6 p-6">
        <label htmlFor="name" className="label">{t('auth.fullName')}</label>
        <input id="name" autoComplete="name" className={`field ${fieldErr('name') ? 'field-error' : ''}`} value={name}
          onChange={(e) => setName(e.target.value)} aria-invalid={!!fieldErr('name')} aria-describedby="name-err" />
        <p id="name-err" className="min-h-[1.25rem] text-sm text-red-800">{fieldErr('name')}</p>

        <label htmlFor="email" className="label mt-2">{t('auth.email')}</label>
        <input id="email" type="email" autoComplete="email" className={`field ${fieldErr('email') ? 'field-error' : ''}`} value={email}
          onChange={(e) => setEmail(e.target.value)} aria-invalid={!!fieldErr('email')} aria-describedby="email-err" />
        <p id="email-err" className="min-h-[1.25rem] text-sm text-red-800">{fieldErr('email')}</p>

        <label htmlFor="password" className="label mt-2">{t('auth.password')}</label>
        <input id="password" type="password" autoComplete="new-password" className={`field ${fieldErr('password') ? 'field-error' : ''}`}
          value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={!!fieldErr('password')} aria-describedby="pw-err pw-hint" />
        <p id="pw-hint" className="text-xs text-ink-soft">{t('auth.passwordHint')}</p>
        <p id="pw-err" className="min-h-[1.25rem] text-sm text-red-800">{fieldErr('password')}</p>

        <ErrorBox message={error} />
        <button type="submit" className="btn-primary mt-4 w-full" disabled={busy}>{busy ? t('common.loading') : t('auth.registerSubmit')}</button>
        <p className="mt-4 text-sm">
          {t('auth.haveAccount')}{' '}
          <Link to="/login" state={location.state} className="font-semibold text-zellige-700 underline">{t('auth.loginLink')}</Link>
        </p>
      </form>
    </div>
  );
}
