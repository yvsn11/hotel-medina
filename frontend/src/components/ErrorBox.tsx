import type { ReactNode } from 'react';

/** Always rendered so the live region exists before the message arrives. */
export function ErrorBox({ message, children }: { message?: string | null; children?: ReactNode }) {
  return (
    <div role="alert" aria-live="assertive">
      {message ? (
        <div className="mt-4 rounded-md border border-red-700 bg-red-50 p-3 text-sm text-red-900">
          <p>{message}</p>
          {children}
        </div>
      ) : null}
    </div>
  );
}
