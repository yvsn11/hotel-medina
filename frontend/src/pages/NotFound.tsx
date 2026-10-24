import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

export default function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-xl px-4 py-16 text-center">
      <h1 className="text-3xl">{t('notFound.title')}</h1>
      <p className="mt-3">{t('notFound.body')}</p>
      <Link to="/" className="btn-primary mt-6">{t('hold.backToSearch')}</Link>
    </div>
  );
}
