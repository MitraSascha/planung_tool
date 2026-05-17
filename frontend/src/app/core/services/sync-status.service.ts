import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class SyncStatusService {
  private readonly lastSyncAtSignal = signal<Date | null>(null);
  private readonly pendingCountSignal = signal<number>(0);

  readonly lastSyncAt = this.lastSyncAtSignal.asReadonly();
  readonly pendingCount = this.pendingCountSignal.asReadonly();

  setSynced(): void {
    this.lastSyncAtSignal.set(new Date());
  }

  incrementPending(): void {
    this.pendingCountSignal.update((count) => count + 1);
  }

  decrementPending(): void {
    this.pendingCountSignal.update((count) => Math.max(0, count - 1));
  }

  resetPending(): void {
    this.pendingCountSignal.set(0);
  }
}
