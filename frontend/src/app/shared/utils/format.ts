export function formatFileSize(sizeBytes?: number | null): string {
  if (sizeBytes === null || sizeBytes === undefined) {
    return 'Groesse unbekannt';
  }

  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }

  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }

  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDateTime(value?: string | null): string {
  if (!value) {
    return 'Zeitpunkt unbekannt';
  }

  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value));
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: 'Entwurf',
    generated: 'Dokumente erstellt',
    generation_queued: 'Wartet auf Erzeugung',
    filtering: 'Bereite Daten vor …',
    generating: 'Dokumente werden erzeugt …',
    running: 'Dokumente werden erzeugt …',
    publishing: 'Wird veröffentlicht …',
    completed: 'Fertig',
    succeeded: 'Fertig',
    failed: 'Fehlgeschlagen — bitte erneut starten',
    failed_partial: 'Teilweise fertig — Details ansehen',
    generation_failed: 'Erzeugung fehlgeschlagen',
    generation_failed_partial: 'Erzeugung teilweise fehlgeschlagen',
    publish_failed: 'Veröffentlichen fehlgeschlagen',
    published: 'Veröffentlicht',
  };

  return labels[status] ?? status;
}

export function projectTypeLabel(projectType: string): string {
  return projectType === 'small' ? 'Kleinprojekt' : 'Standardprojekt';
}

// Filename- bzw. Pfad-Marker für ausfüllbare Formulare/Checklisten;
// alles andere gilt als Informationsdokument.
const FORM_DOCUMENT_PATTERN =
  /(Tagescheckliste|Wochenplan|Checklist|Protokoll|Risiken|Maengel|Mängel|Status)/i;

export function inferDocumentType(path: string): 'form' | 'info' {
  return FORM_DOCUMENT_PATTERN.test(path) ? 'form' : 'info';
}

export function sortDocumentsFormFirst<T extends { path: string }>(files: readonly T[]): T[] {
  return files.slice().sort((a, b) => {
    const aType = inferDocumentType(a.path);
    const bType = inferDocumentType(b.path);
    if (aType !== bType) {
      return aType === 'form' ? -1 : 1;
    }
    return a.path.localeCompare(b.path);
  });
}

export const ALLOWED_UPLOAD_SUFFIXES = ['.csv', '.pdf', '.xlsx', '.xls'] as const;

export function isAllowedUploadFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return ALLOWED_UPLOAD_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

export function formatDate(value?: string | null): string {
  if (!value) {
    return '—';
  }
  return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short' }).format(new Date(value));
}

export function reportStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    green: 'Gruen',
    yellow: 'Gelb',
    red: 'Rot',
  };
  return labels[status] ?? status;
}

export function priorityLabel(priority: string): string {
  const labels: Record<string, string> = {
    low: 'Niedrig',
    normal: 'Normal',
    high: 'Hoch',
    urgent: 'Dringend',
  };
  return labels[priority] ?? priority;
}

export function severityLabel(severity: string): string {
  const labels: Record<string, string> = {
    low: 'Niedrig',
    medium: 'Mittel',
    high: 'Hoch',
    critical: 'Kritisch',
  };
  return labels[severity] ?? severity;
}

export function issueStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    open: 'Offen',
    in_progress: 'In Arbeit',
    done: 'Erledigt',
  };
  return labels[status] ?? status;
}

export function todayIso(): string {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

export function weekStartIso(date: Date = new Date()): string {
  const copy = new Date(date);
  const day = copy.getDay();
  const diff = (day === 0 ? -6 : 1) - day; // Monday
  copy.setDate(copy.getDate() + diff);
  const yyyy = copy.getFullYear();
  const mm = String(copy.getMonth() + 1).padStart(2, '0');
  const dd = String(copy.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

export function weekEndIso(date: Date = new Date()): string {
  const copy = new Date(date);
  const day = copy.getDay();
  const diff = (day === 0 ? 0 : 7 - day); // Sunday
  copy.setDate(copy.getDate() + diff);
  const yyyy = copy.getFullYear();
  const mm = String(copy.getMonth() + 1).padStart(2, '0');
  const dd = String(copy.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}
