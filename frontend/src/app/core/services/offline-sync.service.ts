import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { NotificationService } from './notification.service';
import { OfflineQueueService, QueuedSubmit } from './offline-queue.service';

/**
 * Sync-Service — leert die Offline-Queue gegen das Backend.
 *
 * Wird automatisch beim 'online'-Event gefeuert und kann manuell vom User
 * über den Sync-Banner ("Jetzt senden") angetriggert werden.
 *
 * Conflict-Strategie für jetzt: jeder Submit wird einmal versucht. Bei
 * 4xx-Antworten (Validation, Auth) bleibt der Eintrag in der Queue mit
 * lastError, damit der User entscheiden kann (löschen / nochmal versuchen
 * nach neuem Login). Bei 5xx oder Netz-Error: bleibt in der Queue für
 * den nächsten Versuch.
 */
@Injectable({ providedIn: 'root' })
export class OfflineSyncService {
  private readonly http = inject(HttpClient);
  private readonly queue = inject(OfflineQueueService);
  private readonly notifications = inject(NotificationService);

  readonly online = signal<boolean>(this._isOnline());
  readonly syncing = signal<boolean>(false);

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => {
        this.online.set(true);
        // Auto-Sync wenn Queue nicht leer
        if (this.queue.hasPending()) {
          void this.flush();
        }
      });
      window.addEventListener('offline', () => this.online.set(false));
    }
  }

  private _isOnline(): boolean {
    if (typeof navigator === 'undefined') return true;
    return navigator.onLine !== false;
  }

  /** Versuche alle Queue-Einträge zu senden. Stoppt bei Netzwerk-Fehler. */
  async flush(): Promise<{ sent: number; failed: number }> {
    if (this.syncing()) {
      return { sent: 0, failed: 0 };
    }
    this.syncing.set(true);
    let sent = 0;
    let failed = 0;
    try {
      const items = await this.queue.list();
      items.sort((a, b) => a.createdAt - b.createdAt);
      for (const item of items) {
        const success = await this._trySend(item);
        if (success) {
          sent++;
          if (item.id != null) await this.queue.remove(item.id);
        } else {
          failed++;
          // Bei Netzwerk-Error: abbrechen, später probieren
          if (item.lastError && item.lastError.startsWith('network:')) {
            break;
          }
        }
      }
    } finally {
      this.syncing.set(false);
    }
    await this.queue.refresh();

    if (sent > 0) {
      this.notifications.showMessage(
        `${sent} Bericht${sent === 1 ? '' : 'e'} erfolgreich nachgesendet.`,
      );
    }
    return { sent, failed };
  }

  /** Einen Eintrag senden. Returnt true bei Erfolg, false sonst. */
  private async _trySend(item: QueuedSubmit): Promise<boolean> {
    const headers: Record<string, string> = {
      'Content-Type': item.contentType || 'application/json',
    };
    if (item.token) headers['Authorization'] = `Bearer ${item.token}`;

    try {
      await firstValueFrom(
        this.http.request(item.method, item.url, {
          body: item.body,
          headers: new HttpHeaders(headers),
        }),
      );
      return true;
    } catch (err: any) {
      const status = err?.status ?? 0;
      const updated: QueuedSubmit = {
        ...item,
        attempts: (item.attempts || 0) + 1,
        lastError:
          status === 0 ? `network: ${err?.message || 'offline'}` : `http_${status}`,
      };
      try {
        await this.queue.update(updated);
      } catch {
        /* ignore */
      }
      return false;
    }
  }
}
