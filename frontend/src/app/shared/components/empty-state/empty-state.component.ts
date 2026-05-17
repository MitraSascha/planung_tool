import { CommonModule } from '@angular/common';
import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  imports: [CommonModule],
  templateUrl: './empty-state.component.html',
  styleUrl: './empty-state.component.scss',
})
export class EmptyStateComponent {
  readonly icon = input<string>('📭');
  readonly title = input<string>('Noch nichts hier');
  readonly description = input<string>('');
  readonly actionLabel = input<string>('');

  readonly action = output<void>();

  protected onAction(): void {
    this.action.emit();
  }
}
