import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { filter } from 'rxjs/operators';
import {
  NavigationEnd,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';

import { AuthService } from './core/services/auth.service';
import { NotificationListenerService } from './core/services/notification-listener.service';
import { NotificationService } from './core/services/notification.service';
import { OfflineQueueService } from './core/services/offline-queue.service';
import { OfflineSyncService } from './core/services/offline-sync.service';
import { ProjectService } from './core/services/project.service';
import { ReportsService } from './core/services/reports.service';
import { SyncStatusService } from './core/services/sync-status.service';
import { UsersService } from './core/services/users.service';
import { formatHttpError } from './core/services/error-format';

const OVERVIEW_ROLES = ['bauleitung', 'projektleitung', 'admin'];
const GENERATOR_ROLES = ['projektleitung', 'admin'];
const ADMIN_ROLES = ['admin'];

interface BottomTab {
  icon: string;
  label: string;
  route: string;
  exact?: boolean;
}

interface NavItem {
  label: string;
  route: string;
  icon: string;
  exact?: boolean;
  visible: boolean;
  disabledReason?: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const SIDEBAR_KEY = 'hez.sidebar.collapsed';

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly projects = inject(ProjectService);
  private readonly users = inject(UsersService);
  private readonly reports = inject(ReportsService);
  private readonly router = inject(Router);
  private readonly notifications = inject(NotificationService);
  private readonly notificationListener = inject(NotificationListenerService);
  private readonly sync = inject(SyncStatusService);
  protected readonly offlineQueue = inject(OfflineQueueService);
  protected readonly offlineSync = inject(OfflineSyncService);

  protected readonly lastSyncAt = this.sync.lastSyncAt;
  protected readonly pendingCount = this.sync.pendingCount;
  // PWA-Offline-Queue: separate Anzeige im Sync-Banner
  protected readonly offlinePendingCount = this.offlineQueue.pendingCount;
  protected readonly offlineSyncing = this.offlineSync.syncing;
  protected readonly offlineOnline = this.offlineSync.online;

  protected manualSync(): void {
    void this.offlineSync.flush();
  }
  private readonly nowTick = signal<number>(Date.now());

  protected readonly currentUser = this.auth.currentUser;
  protected readonly message = this.notifications.message;
  protected readonly error = this.notifications.error;
  protected readonly errorAction = this.notifications.errorAction;
  protected readonly dryRunPrompt = this.notifications.dryRunPrompt;

  protected loginForm = { username: '', password: '' };

  protected readonly online = signal<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );

  protected readonly canSeeOverview = computed<boolean>(() => {
    const user = this.currentUser();
    return Boolean(user && OVERVIEW_ROLES.includes(user.global_role));
  });

  protected readonly canUseGenerator = computed<boolean>(() => {
    const user = this.currentUser();
    return Boolean(user && GENERATOR_ROLES.includes(user.global_role));
  });

  protected readonly canUseAdmin = computed<boolean>(() => {
    const user = this.currentUser();
    return Boolean(user && ADMIN_ROLES.includes(user.global_role));
  });

  protected readonly sidebarCollapsed = signal<boolean>(this.loadCollapsedState());

  private loadCollapsedState(): boolean {
    if (typeof localStorage === 'undefined') return false;
    return localStorage.getItem(SIDEBAR_KEY) === '1';
  }

  protected toggleSidebar(): void {
    const next = !this.sidebarCollapsed();
    this.sidebarCollapsed.set(next);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(SIDEBAR_KEY, next ? '1' : '0');
    }
  }

  protected readonly navGroups = computed<readonly NavGroup[]>(() => {
    const user = this.currentUser();
    if (!user) return [];
    const overview = this.canSeeOverview();
    const gen = this.canUseGenerator();
    const adm = this.canUseAdmin();
    return [
      {
        label: 'Überblick',
        items: [
          { label: 'Dashboard', route: '/', icon: '🏠', exact: true, visible: true },
          { label: 'Alle Projekte', route: '/overview/all', icon: '📊', visible: overview, disabledReason: 'Nur für Bauleitung, Projektleitung und Admin' },
        ],
      },
      {
        label: 'Baustellen',
        items: [
          { label: 'Meine Baustellen', route: '/landing', icon: '🏗', visible: true },
          { label: 'Projekte', route: '/projects', icon: '📁', visible: overview, disabledReason: 'Nur für Bauleitung, Projektleitung und Admin' },
          { label: 'Dokumente erzeugen', route: '/outputs', icon: '📄', visible: gen, disabledReason: 'Nur für Projektleitung und Admin' },
          { label: 'Anomalien', route: '/anomalies', icon: '⚠️', visible: overview, disabledReason: 'Nur für Bauleitung, Projektleitung und Admin' },
        ],
      },
      {
        label: 'Auswertung',
        items: [
          { label: 'Analysen', route: '/analyses', icon: '📈', visible: overview, disabledReason: 'Nur für Bauleitung, Projektleitung und Admin' },
        ],
      },
      {
        label: 'Verwaltung',
        items: [
          { label: 'Administration', route: '/admin', icon: '⚙️', visible: adm, disabledReason: 'Nur für Admin' },
          { label: 'Push-Benachrichtigungen', route: '/admin/push', icon: '🔔', visible: adm, disabledReason: 'Nur für Admin' },
          { label: 'DSGVO-Panel', route: '/admin/dsgvo', icon: '🔒', visible: adm, disabledReason: 'Nur für Admin' },
        ],
      },
    ];
  });

  protected readonly bottomTabs = computed<readonly BottomTab[]>(() => {
    const user = this.currentUser();
    if (!user) {
      return [];
    }
    const role = user.global_role;
    if (role === 'admin') {
      return [
        { icon: '🏗', label: 'Projekte', route: '/projects' },
        { icon: '📊', label: 'Status', route: '/overview/all' },
        { icon: '📄', label: 'Dokumente', route: '/outputs' },
        { icon: '🛠', label: 'Admin', route: '/admin' },
      ];
    }
    if (role === 'projektleitung' || role === 'bauleitung') {
      return [
        { icon: '🏗', label: 'Baustellen', route: '/landing' },
        { icon: '📊', label: 'Status', route: '/overview/all' },
        { icon: '📁', label: 'Projekte', route: '/projects' },
        { icon: '⚙️', label: 'Mehr', route: '/', exact: true },
      ];
    }
    // monteur / obermonteur / viewer
    return [
      { icon: '🏠', label: 'Heute', route: '/landing' },
      { icon: '🔔', label: 'Hinweise', route: '/settings/push' },
      { icon: '⚙️', label: 'Mehr', route: '/', exact: true },
    ];
  });

  protected readonly lastSyncRelative = computed<string>(() => {
    const at = this.lastSyncAt();
    if (!at) {
      return 'noch nicht synchronisiert';
    }
    const diffMs = this.nowTick() - at.getTime();
    if (diffMs < 5_000) {
      return 'gerade eben';
    }
    const sec = Math.floor(diffMs / 1000);
    if (sec < 60) {
      return `vor ${sec} Sek.`;
    }
    const min = Math.floor(sec / 60);
    if (min < 60) {
      return `vor ${min} Min.`;
    }
    const hr = Math.floor(min / 60);
    if (hr < 24) {
      return `vor ${hr} Std.`;
    }
    const days = Math.floor(hr / 24);
    return `vor ${days} T.`;
  });

  // /landing auto-redirects single-project users to /projects/:slug/role,
  // which would otherwise light up the "Projekte" tab even though the user
  // is conceptually in "Meine Baustellen". Track the current URL and decide
  // tab highlighting manually for those two nav entries.
  private readonly currentUrl = signal<string>(this.router.url);

  protected readonly landingActive = computed<boolean>(() => {
    const url = this.currentUrl();
    return url === '/landing'
      || url.startsWith('/landing/')
      || /^\/projects\/[^/]+\/role(?:[/?#]|$)/.test(url);
  });

  protected readonly projectsActive = computed<boolean>(() => {
    const url = this.currentUrl();
    if (!url.startsWith('/projects')) {
      return false;
    }
    // Sub-routes that conceptually belong to other nav tabs.
    if (/^\/projects\/[^/]+\/role(?:[/?#]|$)/.test(url)) {
      return false;
    }
    return true;
  });

  constructor() {
    this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => this.currentUrl.set(event.urlAfterRedirects));

    if (this.auth.isAuthenticated()) {
      this.auth.loadCurrentUser().subscribe({
        next: () => this.projects.list().subscribe(),
        error: () => this.handleLogout(),
      });
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this.online.set(true));
      window.addEventListener('offline', () => this.online.set(false));
      setInterval(() => this.nowTick.set(Date.now()), 15_000);
    }

    this.notificationListener.start();
  }

  protected login(): void {
    this.notifications.clear();
    this.auth.login(this.loginForm).subscribe({
      next: (response) => {
        this.notifications.showMessage(`Angemeldet als ${response.user.display_name}.`);
        this.projects.list().subscribe();
        this.users.list().subscribe({ error: () => undefined });
        this.router.navigate([this.landingRouteFor(response.user.global_role)]);
      },
      error: (response) => {
        const text = response?.status === 401
          ? 'Benutzername oder Passwort falsch.'
          : formatHttpError(response, 'Anmeldung fehlgeschlagen.');
        this.notifications.showError(text);
      },
    });
  }

  private landingRouteFor(role: string): string {
    if (role === 'admin') {
      return '/admin';
    }
    if (role === 'projektleitung' || role === 'bauleitung') {
      return '/overview/all';
    }
    return '/landing';
  }

  protected logout(): void {
    this.handleLogout();
    this.router.navigate(['/']);
  }

  private handleLogout(): void {
    this.auth.logout();
    this.projects.clearProjects();
    this.users.clear();
    this.reports.clear();
    this.notifications.clear();
  }
}
