import { CommonModule, DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';

import { NotificationService } from '../../../core/services/notification.service';
import {
  PushPublicKeyResponse,
  PushService,
  PushSubscriptionRead,
} from '../../../core/services/push.service';

@Component({
  selector: 'app-push-settings',
  standalone: true,
  imports: [CommonModule, DatePipe],
  templateUrl: './push-settings.component.html',
  styleUrl: './push-settings.component.scss',
})
export class PushSettingsComponent {
  private readonly push = inject(PushService);
  private readonly notifications = inject(NotificationService);

  protected readonly busy = signal<boolean>(false);
  protected readonly serverInfo = signal<PushPublicKeyResponse | null>(null);
  protected readonly subscriptions = this.push.subscriptions;
  protected readonly enabled = this.push.isEnabledSignal;
  protected readonly supported = signal<boolean>(this.push.isSupported());
  protected readonly statusText = signal<string>('');

  constructor() {
    this.push
      .fetchPublicKey()
      .subscribe({
        next: (info) => this.serverInfo.set(info),
        error: () => this.serverInfo.set({ vapid_public_key: null, enabled: false }),
      });
    this.push.refreshSubscriptions().catch(() => undefined);
  }

  protected async toggle(): Promise<void> {
    this.busy.set(true);
    this.statusText.set('');
    try {
      if (this.enabled()) {
        await this.push.disable();
        this.notifications.showMessage('Push-Benachrichtigungen deaktiviert.');
        this.statusText.set('Push deaktiviert.');
      } else {
        const result = await this.push.enable();
        if (result.ok) {
          this.notifications.showMessage('Push-Benachrichtigungen aktiviert.');
          this.statusText.set('Push aktiv.');
        } else {
          this.notifications.showError(result.reason ?? 'Aktivierung fehlgeschlagen.');
          this.statusText.set(result.reason ?? 'Aktivierung fehlgeschlagen.');
        }
      }
    } finally {
      this.busy.set(false);
    }
  }

  protected sendTest(): void {
    this.busy.set(true);
    this.push.sendTest().subscribe({
      next: (resp) => {
        this.busy.set(false);
        if (!resp.enabled) {
          this.notifications.showError('Push ist serverseitig nicht aktiv.');
          return;
        }
        if (resp.sent === 0) {
          this.notifications.showError(
            `Kein Empfaenger erreicht (failed=${resp.failed}, expired=${resp.expired}).`,
          );
          return;
        }
        this.notifications.showMessage(
          `Test versendet an ${resp.sent} Geraet(e).`,
        );
      },
      error: () => {
        this.busy.set(false);
        this.notifications.showError('Test-Versand fehlgeschlagen.');
      },
    });
  }

  protected async removeSubscription(sub: PushSubscriptionRead): Promise<void> {
    this.busy.set(true);
    try {
      await this.push.deleteSubscription(sub.endpoint);
      await this.push.refreshSubscriptions();
      this.notifications.showMessage('Subscription entfernt.');
    } catch {
      this.notifications.showError('Konnte Subscription nicht entfernen.');
    } finally {
      this.busy.set(false);
    }
  }

  protected shortEndpoint(endpoint: string): string {
    try {
      const url = new URL(endpoint);
      return url.host;
    } catch {
      return endpoint.slice(0, 40);
    }
  }
}
