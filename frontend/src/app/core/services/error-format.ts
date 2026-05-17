interface HttpErrorLike {
  status?: number;
  error?: { detail?: unknown } | null;
}

const STATUS_MESSAGES: Record<number, string> = {
  401: 'Deine Sitzung ist abgelaufen. Bitte neu anmelden.',
  403: 'Diese Aktion ist für deine Rolle nicht freigegeben.',
  404: 'Nicht gefunden — vielleicht wurde es verschoben oder gelöscht.',
};

export function formatHttpError(response: HttpErrorLike, fallback: string): string {
  const status = response?.status ?? 0;

  if (status === 0) {
    return 'Keine Verbindung. Prüfe deine Internetverbindung.';
  }

  if (status >= 500) {
    return 'Server-Problem. Bitte in einer Minute nochmal versuchen.';
  }

  if (status in STATUS_MESSAGES) {
    return STATUS_MESSAGES[status];
  }

  const detail = response?.error?.detail;

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const formatted = detail
      .map((item: unknown) => {
        if (typeof item !== 'object' || item === null) {
          return undefined;
        }
        const record = item as Record<string, unknown>;
        const rawLoc = Array.isArray(record['loc']) ? record['loc'] : [];
        // FastAPI prefixes locations with 'body' / 'query' — für Endnutzer irrelevant.
        const location = rawLoc
          .filter((segment) => segment !== 'body' && segment !== 'query')
          .join('.');
        const message = typeof record['msg'] === 'string' ? record['msg'] : undefined;
        return [location, message].filter(Boolean).join(': ');
      })
      .filter(Boolean)
      .join('\n');

    if (formatted) {
      return status === 422 ? `Bitte Eingaben prüfen — ${formatted}` : formatted;
    }
  }

  return fallback;
}
