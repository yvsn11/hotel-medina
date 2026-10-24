import { useLocation, useNavigate } from 'react-router-dom';

/** Returns a function that sends the user back to where the auth guard sent them from. */
export function useAfterAuth() {
  const location = useLocation();
  const navigate = useNavigate();
  const from = (location.state as { from?: string } | null)?.from;
  return () => navigate(from && from.startsWith('/') ? from : '/', { replace: true });
}
