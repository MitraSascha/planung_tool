import { HttpErrorResponse, HttpEventType, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { EMPTY, throwError } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';

import { AuthService } from './auth.service';
import { NotificationService } from './notification.service';
import { SyncStatusService } from './sync-status.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const notifications = inject(NotificationService);
  const sync = inject(SyncStatusService);

  const token = auth.token();
  const request = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(request).pipe(
    tap((event) => {
      if (event.type === HttpEventType.Response && event.ok) {
        sync.setSynced();
      }
    }),
    catchError((error: unknown) => {
      // 401 vom eingeloggten Zustand aus = Token abgelaufen → ausloggen +
      // Toast mit „Neu anmelden"-Aktion. Bei Login selbst (kein Token vorher)
      // soll die normale Fehlerbehandlung des Aufrufers greifen.
      if (error instanceof HttpErrorResponse && error.status === 401 && token) {
        auth.logout();
        notifications.showError('Deine Sitzung ist abgelaufen. Bitte neu anmelden.', {
          label: 'Neu anmelden',
          callback: () => {
            router.navigate(['/']);
          },
        });
        router.navigate(['/']);
        return EMPTY;
      }
      return throwError(() => error);
    }),
  );
};
