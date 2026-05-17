import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import { SwPush } from '@angular/service-worker';

/**
 * Reagiert auf eingehende Push-Notifications und Klicks auf
 * Notifications. Der eigentliche System-Toast wird vom Service-Worker
 * selbst angezeigt; wir muessen hier nur den Klick-Handler binden, damit
 * der Browser zur ``data.url`` aus dem Payload navigiert.
 */
@Injectable({ providedIn: 'root' })
export class NotificationListenerService {
  private readonly swPush = inject(SwPush);
  private readonly router = inject(Router);

  private started = false;

  start(): void {
    if (this.started) {
      return;
    }
    if (!this.swPush.isEnabled) {
      return;
    }
    this.started = true;

    this.swPush.notificationClicks.subscribe(({ notification }) => {
      const data = (notification?.data as { url?: string }) ?? {};
      if (data.url) {
        this.router.navigateByUrl(data.url).catch(() => undefined);
      }
    });

    // Auf manchen Plattformen liefert ngsw nur Payload — der Browser
    // zeigt die Notification nicht selbststaendig. Wir koennen hier
    // einen Fallback einbauen, falls der Service-Worker den Toast nicht
    // automatisch rendert. Auf modernen Browsern macht ngsw das selbst.
    this.swPush.messages.subscribe(() => {
      /* no-op — Browser-Toast kommt vom Service-Worker. */
    });
  }
}
