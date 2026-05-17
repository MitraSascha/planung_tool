import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AuditEventFilter,
  AuditEventRead,
  CleanupResponse,
  ProjectRead,
  RetentionRuleRead,
  RetentionRuleUpsert,
} from '../../../core/models';
import { DsgvoService } from '../../../core/services/dsgvo.service';
import { NotificationService } from '../../../core/services/notification.service';
import { ProjectService } from '../../../core/services/project.service';
import { formatHttpError } from '../../../core/services/error-format';

const ENTITY_OPTIONS: string[] = [
  'Project',
  'ProjectSection',
  'ProjectMember',
  'User',
  'DailyReport',
  'WeeklyReport',
  'Blocker',
  'MaterialIssue',
  'GenerationRun',
  'HeatingDesign',
  'VoiceNote',
  'AuditEvent',
];

const ACTION_OPTIONS: string[] = ['create', 'update', 'delete', 'anonymize', 'login', 'export'];

const RETENTION_ENTITIES: string[] = [
  'DailyReport',
  'WeeklyReport',
  'Blocker',
  'MaterialIssue',
  'GenerationRun',
  'AuditEvent',
  'VoiceNote',
];

@Component({
  selector: 'app-dsgvo-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dsgvo-panel.component.html',
  styleUrl: './dsgvo-panel.component.scss',
})
export class DsgvoPanelComponent {
  private readonly dsgvo = inject(DsgvoService);
  private readonly projectService = inject(ProjectService);
  private readonly notifications = inject(NotificationService);

  protected readonly entityOptions = ENTITY_OPTIONS;
  protected readonly actionOptions = ACTION_OPTIONS;
  protected readonly retentionEntities = RETENTION_ENTITIES;

  protected readonly auditEvents = signal<AuditEventRead[]>([]);
  protected readonly auditLoading = signal<boolean>(false);
  protected readonly retentionRules = signal<RetentionRuleRead[]>([]);
  protected readonly cleanupResult = signal<CleanupResponse | null>(null);
  protected readonly projects = this.projectService.projects;
  protected readonly busy = signal<boolean>(false);

  protected auditFilter: AuditEventFilter = {
    entity_type: '',
    project_slug: '',
    action: '',
    from: '',
    to: '',
    limit: 200,
  };

  protected newRule: RetentionRuleUpsert = {
    entity_type: RETENTION_ENTITIES[0],
    ttl_days: 365,
    action: 'delete',
    enabled: true,
    description: '',
  };

  protected anonymizeSlug = '';
  protected deleteSlug = '';
  protected deleteConfirm = '';

  constructor() {
    this.refreshAudit();
    this.refreshRules();
    this.projectService.list().subscribe({ error: () => undefined });
  }

  protected refreshAudit(): void {
    this.auditLoading.set(true);
    const payload: AuditEventFilter = {
      entity_type: this.auditFilter.entity_type || undefined,
      project_slug: this.auditFilter.project_slug || undefined,
      action: this.auditFilter.action || undefined,
      from: this.auditFilter.from || undefined,
      to: this.auditFilter.to || undefined,
      limit: this.auditFilter.limit ?? 200,
    };
    this.dsgvo.listAuditEvents(payload).subscribe({
      next: (events) => {
        this.auditEvents.set(events);
        this.auditLoading.set(false);
      },
      error: (response) => {
        this.auditLoading.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Audit-Log konnte nicht geladen werden.'),
        );
      },
    });
  }

  protected refreshRules(): void {
    this.dsgvo.listRetentionRules().subscribe({
      next: (rules) => this.retentionRules.set(rules),
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Aufbewahrungsregeln konnten nicht geladen werden.'),
        ),
    });
  }

  protected saveRule(rule: RetentionRuleUpsert): void {
    this.busy.set(true);
    this.dsgvo.upsertRetentionRule(rule).subscribe({
      next: () => {
        this.busy.set(false);
        this.notifications.showMessage('Aufbewahrungsregel wurde gespeichert.');
        this.refreshRules();
      },
      error: (response) => {
        this.busy.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Aufbewahrungsregel konnte nicht gespeichert werden.'),
        );
      },
    });
  }

  protected addRule(): void {
    if (!this.newRule.entity_type || this.newRule.ttl_days < 0) {
      this.notifications.showError('Bitte gueltigen Eintrag eingeben.');
      return;
    }
    this.saveRule({
      ...this.newRule,
      description: this.newRule.description || null,
    });
    this.newRule = {
      entity_type: RETENTION_ENTITIES[0],
      ttl_days: 365,
      action: 'delete',
      enabled: true,
      description: '',
    };
  }

  protected toggleRule(rule: RetentionRuleRead): void {
    this.saveRule({
      entity_type: rule.entity_type,
      ttl_days: rule.ttl_days,
      action: rule.action as 'delete' | 'anonymize',
      enabled: !rule.enabled,
      description: rule.description,
    });
  }

  protected updateRule(rule: RetentionRuleRead): void {
    this.saveRule({
      entity_type: rule.entity_type,
      ttl_days: rule.ttl_days,
      action: rule.action as 'delete' | 'anonymize',
      enabled: rule.enabled,
      description: rule.description,
    });
  }

  protected deleteRule(rule: RetentionRuleRead): void {
    if (!confirm(`Regel fuer ${rule.entity_type} loeschen?`)) {
      return;
    }
    this.dsgvo.deleteRetentionRule(rule.entity_type).subscribe({
      next: () => {
        this.notifications.showMessage('Regel wurde geloescht.');
        this.refreshRules();
      },
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Regel konnte nicht geloescht werden.'),
        ),
    });
  }

  protected runDryRun(): void {
    this.busy.set(true);
    this.dsgvo.runCleanup(true).subscribe({
      next: (result) => {
        this.busy.set(false);
        this.cleanupResult.set(result);
        this.notifications.showMessage('Dry-Run durchgefuehrt.');
      },
      error: (response) => {
        this.busy.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Dry-Run fehlgeschlagen.'),
        );
      },
    });
  }

  protected runCleanup(): void {
    if (!confirm('Cleanup ausfuehren? Diese Aktion ist nicht rueckgaengig zu machen.')) {
      return;
    }
    this.busy.set(true);
    this.dsgvo.runCleanup(false).subscribe({
      next: (result) => {
        this.busy.set(false);
        this.cleanupResult.set(result);
        this.notifications.showMessage('Cleanup wurde durchgefuehrt.');
        this.refreshAudit();
      },
      error: (response) => {
        this.busy.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Cleanup fehlgeschlagen.'),
        );
      },
    });
  }

  protected anonymize(): void {
    const slug = this.anonymizeSlug;
    if (!slug) {
      this.notifications.showError('Bitte Projekt auswaehlen.');
      return;
    }
    if (!confirm(`Projekt ${slug} anonymisieren? Diese Aktion ist nicht rueckgaengig zu machen.`)) {
      return;
    }
    this.busy.set(true);
    this.dsgvo.anonymizeProject(slug).subscribe({
      next: (response) => {
        this.busy.set(false);
        this.notifications.showMessage(
          `Projekt ${slug} anonymisiert: ${response.updated_rows} Zeile(n) angepasst.`,
        );
        this.refreshAudit();
      },
      error: (response) => {
        this.busy.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Anonymisierung fehlgeschlagen.'),
        );
      },
    });
  }

  protected deleteProject(): void {
    const slug = this.deleteSlug;
    const expected = `DELETE-${slug}`;
    if (!slug) {
      this.notifications.showError('Bitte Projekt auswaehlen.');
      return;
    }
    if (this.deleteConfirm !== expected) {
      this.notifications.showError(`Bestaetigung muss exakt "${expected}" lauten.`);
      return;
    }
    if (!confirm(`Projekt ${slug} unwiderruflich loeschen?`)) {
      return;
    }
    this.busy.set(true);
    this.dsgvo.deleteProject(slug, this.deleteConfirm).subscribe({
      next: (response) => {
        this.busy.set(false);
        this.notifications.showMessage(
          `Projekt ${slug} geloescht (${response.removed_files} Dateien, ${response.removed_dirs} Verzeichnisse entfernt).`,
        );
        this.deleteSlug = '';
        this.deleteConfirm = '';
        this.projectService.list().subscribe({ error: () => undefined });
        this.refreshAudit();
      },
      error: (response) => {
        this.busy.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Loeschvorgang fehlgeschlagen.'),
        );
      },
    });
  }

  protected onDeleteSlugChange(slug: string): void {
    this.deleteSlug = slug;
    this.deleteConfirm = '';
  }

  protected cleanupRules(): { entity_type: string; stats: { affected: number; executed?: number; action: string; skipped?: boolean; reason?: string } }[] {
    const result = this.cleanupResult();
    if (!result) {
      return [];
    }
    return Object.entries(result.rules).map(([entity_type, stats]) => ({
      entity_type,
      stats: stats as { affected: number; executed?: number; action: string; skipped?: boolean; reason?: string },
    }));
  }

  protected projectSlugs(): string[] {
    return this.projects().map((p: ProjectRead) => p.slug);
  }
}
