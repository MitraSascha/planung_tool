import {
  HttpErrorResponse,
  HttpEvent,
  HttpHandlerFn,
  HttpRequest,
  HttpResponse,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { AuthService } from './auth.service';
import { NotificationService } from './notification.service';
import { OfflineQueueService } from './offline-queue.service';

/**
 * Fängt write-Requests (POST/PUT/PATCH) gegen die eigene API ab.
 *
 * Bei Netzwerk-Error (status 0 oder bekannter Offline-Marker) wird der
 * Submit in die IndexedDB-Queue geschoben und der Aufrufer bekommt eine
 * synthetische HTTP-202-Response („Accepted, wird später gesendet").
 *
 * Bei allen anderen Fehlern (4xx/5xx) wird normal durchgereicht — das
 * sind Server-Fehler, die der User direkt sehen soll.
 */
const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function isOurApi(url: string): boolean {
  // Eigene API: relativer Pfad /api/...  oder absoluter mit selber Origin
  if (url.startsWith('/api/')) return true;
  try {
    const u = new URL(url, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    return (
      u.pathname.startsWith('/api/')
      && (typeof window === 'undefined' || u.origin === window.location.origin)
    );
  } catch {
    return false;
  }
}

function isFormDataBody(body: unknown): boolean {
  return typeof FormData !== 'undefined' && body instanceof FormData;
}

function isNetworkError(err: HttpErrorResponse): boolean {
  // status 0: Netzwerkfehler / CORS / offline
  // Manche Browser liefern auch ProgressEvent — wir prüfen den status
  return err.status === 0;
}

export function offlineQueueInterceptor(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
): Observable<HttpEvent<unknown>> {
  const queue = inject(OfflineQueueService);
  const auth = inject(AuthService);
  const notifications = inject(NotificationService);

  // Nur write-Requests gegen die eigene API queuen
  if (!WRITE_METHODS.has(req.method) || !isOurApi(req.url)) {
    return next(req);
  }
  // FormData (Datei-Uploads) NICHT queuen — IndexedDB-Serialisierung
  // ist fragil und Datei-Uploads sind selten offline-kritisch.
  if (isFormDataBody(req.body)) {
    return next(req);
  }

  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      if (!isNetworkError(err)) {
        throw err;
      }
      // Netzwerkfehler → in Queue
      const token = auth.token ? auth.token() : null;
      const contentType =
        req.headers.get('Content-Type') || 'application/json';
      const label = labelFromRequest(req);

      queue
        .add({
          url: req.urlWithParams,
          method: req.method,
          body: req.body,
          contentType,
          token,
          label,
        })
        .then(() => {
          notifications.showMessage(
            `📴 Offline: „${label}" wartet auf Sync — wird automatisch nachgesendet sobald du wieder online bist.`,
          );
        })
        .catch(() => {
          notifications.showError(
            'Konnte Eingabe nicht offline speichern. Bitte erneut versuchen.',
          );
        });

      // Synthetische 202-Antwort an den Aufrufer
      const synthetic = new HttpResponse<unknown>({
        status: 202,
        statusText: 'Accepted (queued for sync)',
        body: { queued: true, label },
        url: req.urlWithParams,
      });
      return of(synthetic as HttpEvent<unknown>);
    }),
  );
}

function labelFromRequest(req: HttpRequest<unknown>): string {
  const url = req.urlWithParams;
  if (url.includes('/daily-reports')) return 'Tagesbericht';
  if (url.includes('/weekly-reports')) return 'Wochenbericht';
  if (url.includes('/blockers')) return 'Blocker';
  if (url.includes('/material-issues')) return 'Materialmeldung';
  if (url.includes('/risk-issues')) return 'Risiko/Mangel';
  if (url.includes('/team-status')) return 'Teamstatus';
  if (url.includes('/material-items')) return 'Material';
  if (url.includes('/form-responses')) return 'Formular-Eingabe';
  // Fallback: kompakter URL-Suffix
  const tail = url.split('?')[0].split('/').slice(-2).join('/');
  return tail || 'Eingabe';
}
