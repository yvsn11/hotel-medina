import type { TFunction } from 'i18next';
import { ApiError } from '../services/api';

const KNOWN = ['no_availability', 'invalid_state', 'email_taken', 'unauthorized', 'forbidden', 'not_found', 'network_error', 'server_error'];

/** Human, translated message for any thrown error. validation_error keeps the server text (field details). */
export function errorMessage(err: unknown, t: TFunction): string {
  if (err instanceof ApiError) {
    if (KNOWN.includes(err.code)) return t(`errors.${err.code}`);
    if (err.code === 'validation_error' && err.message) return err.message;
    return t('errors.generic');
  }
  return t('errors.generic');
}
