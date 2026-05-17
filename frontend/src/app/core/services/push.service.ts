import { HttpClient } from '@angular/common/http';
import { Injectable, Signal, inject, signal } from '@angular/core';
import { SwPush } from '@angular/service-worker';
import { firstValueFrom, Observable } from 'rxjs';

export interface PushPublicKeyResponse {
  vapid_public_key: string | null;
  enabled: boolean;
}

export interface PushSubscriptionRead {
  id: number;
  endpoint: string;
  user_agent: string | null;
  active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface PushTestResponse {
  sent: number;
  failed: number;
  expired: number;
  enabled: boolean;
}

/**
 * Verwaltet Web-Push-Abonnements gegen das Backend.
 *
 * Pipeline beim Einschalten:
 *   1. ``GET /api/push/public-key`` — Schluessel + Aktiv-Status holen.
 *   2. ``SwPush.requestSubscription`` mit dem Public-Key.
 *   3. ``POST /api/push/subscriptions`` — endpoint + keys persistieren.
 */
@Injectable({ providedIn: 'root' })
export class PushService {
  private readonly http = inject(HttpClient);
  private readonly swPush = inject(SwPush);

  private readonly enabledSignal = signal<boolean>(false);
  private readonly subscriptionsSignal = signal<PushSubscriptionRead[]>([]);
  private readonly publicKeySignal = signal<PushPublicKeyResponse | null>(null);

  readonly isEnabledSignal: Signal<boolean> = this.enabledSignal.asReadonly();
  readonly subscriptions: Signal<PushSubscriptionRead[]> = this.subscriptionsSignal.asReadonly();
  readonly publicKey: Signal<PushPublicKeyResponse | null> = this.publicKeySignal.asReadonly();

  /** True wenn die Browser-APIs vorhanden sind. */
  isSupported(): boolean {
    if (typeof window === 'undefined') {
      return false;
    }
    return (
      'serviceWorker' in navigator &&
      typeof window.PushManager !== 'undefined' &&
      this.swPush.isEnabled
    );
  }

  /** Reactive read: derzeitiger Toggle-Status. */
  isEnabled(): Signal<boolean> {
    return this.enabledSignal.asReadonly();
  }

  /** Holt den Public-Key aus dem Backend und cached ihn. */
  fetchPublicKey(): Observable<PushPublicKeyResponse> {
    return this.http.get<PushPublicKeyResponse>('/api/push/public-key');
  }

  /** Listet die eigenen Subscriptions. */
  refreshSubscriptions(): Promise<PushSubscriptionRead[]> {
    return firstValueFrom(
      this.http.get<PushSubscriptionRead[]>('/api/push/subscriptions'),
    ).then((items) => {
      this.subscriptionsSignal.set(items);
      const anyActive = items.some((s) => s.active);
      this.enabledSignal.set(anyActive);
      return items;
    });
  }

  /** Aktiviert Push: holt Key, abonniert ueber ngsw, persistiert im Backend. */
  async enable(): Promise<{ ok: boolean; reason?: string }> {
    if (!this.isSupported()) {
      return { ok: false, reason: 'Browser unterstuetzt keine Web-Push-Benachrichtigungen.' };
    }
    let pk = this.publicKeySignal();
    if (!pk) {
      pk = await firstValueFrom(this.fetchPublicKey());
      this.publicKeySignal.set(pk);
    }
    if (!pk.enabled || !pk.vapid_public_key) {
      return { ok: false, reason: 'Push ist auf dem Server nicht konfiguriert.' };
    }

    let sub: PushSubscription;
    try {
      sub = await this.swPush.requestSubscription({
        serverPublicKey: pk.vapid_public_key,
      });
    } catch (err) {
      return {
        ok: false,
        reason: `Subscription abgelehnt oder fehlgeschlagen: ${(err as Error).message}`,
      };
    }

    const payload = this.subscriptionToPayload(sub);
    try {
      await firstValueFrom(
        this.http.post<PushSubscriptionRead>('/api/push/subscriptions', payload),
      );
    } catch (err) {
      return { ok: false, reason: `Speichern fehlgeschlagen: ${(err as Error).message}` };
    }

    this.enabledSignal.set(true);
    await this.refreshSubscriptions();
    return { ok: true };
  }

  /** Deaktiviert Push: unsubscribe + Backend benachrichtigen. */
  async disable(): Promise<void> {
    if (!this.isSupported()) {
      this.enabledSignal.set(false);
      return;
    }
    const current = await firstValueFrom(this.swPush.subscription);
    if (current) {
      const endpoint = current.endpoint;
      try {
        await current.unsubscribe();
      } catch {
        /* ignore */
      }
      try {
        await firstValueFrom(
          this.http.delete<void>(`/api/push/subscriptions/${encodeURIComponent(endpoint)}`),
        );
      } catch {
        /* ignore — Backend wird die Sub spaetestens bei 410 deaktivieren. */
      }
    }
    this.enabledSignal.set(false);
    await this.refreshSubscriptions().catch(() => undefined);
  }

  /** Sendet eine Test-Notification an die eigenen Subscriptions. */
  sendTest(): Observable<PushTestResponse> {
    return this.http.post<PushTestResponse>('/api/push/test', {});
  }

  /** Loescht eine konkrete Subscription (z. B. aus der Liste). */
  deleteSubscription(endpoint: string): Promise<void> {
    return firstValueFrom(
      this.http.delete<void>(`/api/push/subscriptions/${encodeURIComponent(endpoint)}`),
    ).then(() => undefined);
  }

  private subscriptionToPayload(sub: PushSubscription): {
    endpoint: string;
    keys: Record<string, string>;
    user_agent: string | null;
  } {
    const json = sub.toJSON();
    const keys = (json.keys ?? {}) as Record<string, string>;
    return {
      endpoint: json.endpoint ?? sub.endpoint,
      keys,
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
    };
  }
}
