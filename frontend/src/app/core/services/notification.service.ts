import { Injectable, signal } from '@angular/core';

export interface NotificationAction {
  label: string;
  callback: () => void;
}

@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly messageSignal = signal('');
  private readonly errorSignal = signal('');
  private readonly errorActionSignal = signal<NotificationAction | null>(null);
  private readonly dryRunPromptSignal = signal('');

  readonly message = this.messageSignal.asReadonly();
  readonly error = this.errorSignal.asReadonly();
  readonly errorAction = this.errorActionSignal.asReadonly();
  readonly dryRunPrompt = this.dryRunPromptSignal.asReadonly();

  showMessage(message: string): void {
    this.messageSignal.set(message);
    this.errorSignal.set('');
    this.errorActionSignal.set(null);
  }

  showError(error: string, action?: NotificationAction): void {
    this.errorSignal.set(error);
    this.errorActionSignal.set(action ?? null);
    this.messageSignal.set('');
  }

  setDryRunPrompt(prompt: string): void {
    this.dryRunPromptSignal.set(prompt);
  }

  clear(): void {
    this.messageSignal.set('');
    this.errorSignal.set('');
    this.errorActionSignal.set(null);
    this.dryRunPromptSignal.set('');
  }
}
