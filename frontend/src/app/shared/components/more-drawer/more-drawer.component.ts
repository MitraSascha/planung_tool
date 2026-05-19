import { CommonModule } from '@angular/common';
import {
  Component,
  HostListener,
  computed,
  effect,
  input,
  output,
} from '@angular/core';
import { RouterLink } from '@angular/router';

/** Sidebar-Item (Subset von App.NavItem). Eigene Deklaration im Component,
 *  damit das Drawer nicht hart an App.ts gebunden ist. */
export interface MoreDrawerItem {
  label: string;
  route: string;
  icon: string;
  exact?: boolean;
  visible: boolean;
  disabledReason?: string;
}

export interface MoreDrawerGroup {
  label: string;
  items: MoreDrawerItem[];
}

@Component({
  selector: 'app-more-drawer',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './more-drawer.component.html',
  styleUrl: './more-drawer.component.scss',
})
export class MoreDrawerComponent {
  /** Steuert Sichtbarkeit; übergeordnete Komponente reagiert mit (close). */
  readonly open = input<boolean>(false);
  /** Selbe Source-of-Truth wie Sidebar (App.navGroups()). */
  readonly groups = input<readonly MoreDrawerGroup[]>([]);
  /** Callback für aktive Route — i.d.R. App.isNavActive (gebunden). */
  readonly isActive = input<(item: { route: string; exact?: boolean }) => boolean>(
    () => false,
  );

  readonly close = output<void>();
  readonly navigate = output<string>();

  /** Sichtbare Gruppen — Items ohne `visible` werden komplett herausgefiltert,
   *  Gruppen ohne sichtbare Items entfallen ebenfalls. */
  protected readonly visibleGroups = computed<readonly MoreDrawerGroup[]>(() => {
    return this.groups()
      .map((g) => ({ ...g, items: g.items.filter((i) => i.visible) }))
      .filter((g) => g.items.length > 0);
  });

  constructor() {
    // Body-Scroll-Lock solange das Drawer offen ist.
    effect(() => {
      if (typeof document === 'undefined') return;
      const body = document.body;
      if (this.open()) {
        body.style.overflow = 'hidden';
      } else {
        body.style.overflow = '';
      }
    });
  }

  @HostListener('document:keydown.escape')
  protected onEsc(): void {
    if (this.open()) {
      this.close.emit();
    }
  }

  protected onBackdrop(): void {
    this.close.emit();
  }

  protected onItemClick(route: string): void {
    this.navigate.emit(route);
    this.close.emit();
  }

  /** Bequemer Wrapper, damit das Template nicht jedes Mal die Callback-Funktion
   *  über die Signal-Klammer aufruft. */
  protected itemActive(item: MoreDrawerItem): boolean {
    const fn = this.isActive();
    try {
      return fn({ route: item.route, exact: item.exact });
    } catch {
      return false;
    }
  }
}
