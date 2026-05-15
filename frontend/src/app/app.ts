import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface ProjectSection {
  number: number;
  name: string;
  goal?: string;
  planned_hours?: number | null;
  responsible?: string;
  staff?: string;
}

interface ProjectForm {
  slug: string;
  name: string;
  project_type: 'standard' | 'small';
  address?: string;
  responsible?: string;
  construction_manager?: string;
  foreman?: string;
  planned_start?: string;
  planned_end?: string;
  notes?: string;
  sections: ProjectSection[];
}

interface ProjectRead extends ProjectForm {
  status: string;
  preview_url: string;
  uploads: ProjectUploadRead[];
  upload_count: number;
  ready_for_generation: boolean;
  readiness_issues: string[];
  documentation_checklist: string[];
  planned_outputs: string[];
}

interface ProjectUploadRead {
  filename: string;
  path: string;
  content_type?: string | null;
  size_bytes?: number | null;
  created_at?: string | null;
}

interface ProjectOutputFile {
  path: string;
  filename: string;
  extension: string;
  size_bytes: number;
  view_url: string;
}

interface ProjectOutputsRead {
  slug: string;
  preview_url: string;
  published: boolean;
  files: ProjectOutputFile[];
}

interface UserRead {
  id: number;
  username: string;
  display_name: string;
  global_role: string;
  active: boolean;
  created_at: string;
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserRead;
}

interface DailyReportRead {
  id: number;
  project_slug: string;
  user_id: number;
  username: string;
  display_name: string;
  section_number?: number | null;
  report_date: string;
  status: string;
  team?: string | null;
  completed_work?: string | null;
  open_work?: string | null;
  material_missing?: string | null;
  blockers?: string | null;
  notes?: string | null;
  created_at: string;
}

interface ReportSummary {
  project_slug: string;
  daily_reports: number;
  weekly_reports: number;
  material_issues_open: number;
  blockers_open: number;
  status_green: number;
  status_yellow: number;
  status_red: number;
}

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  protected readonly title = signal('hez-tool-frontend');
  protected readonly allowedUploadTypes = '.csv,.pdf,.xlsx,.xls';
  protected readonly smallProjectOutputs = [
    '01_Projektuebersicht',
    '06_Detaillierter_Ablaufplan',
    '08_Monteur_Tagescheckliste',
    '10_Tagesbericht_App',
    '11_Meilensteinplan',
    '14_Gantt_Uebersicht',
  ];
  protected projects = signal<ProjectRead[]>([]);
  protected message = signal('');
  protected error = signal('');
  protected dryRunPrompt = signal('');
  protected selectedUploadNames = signal<Record<string, string[]>>({});
  protected uploadingSlug = signal<string | null>(null);
  protected generatingSlug = signal<string | null>(null);
  protected outputs = signal<Record<string, ProjectOutputsRead>>({});
  protected outputsLoadingSlug = signal<string | null>(null);
  protected activeView = signal<'overview' | 'projects' | 'analyses' | 'outputs' | 'admin'>('overview');
  protected token = signal(localStorage.getItem('hez_token') ?? '');
  protected currentUser = signal<UserRead | null>(null);
  protected users = signal<UserRead[]>([]);
  protected dailyReports = signal<Record<string, DailyReportRead[]>>({});
  protected summaries = signal<Record<string, ReportSummary>>({});

  protected loginForm = { username: 'admin', password: 'admin' };
  protected userForm = { username: '', display_name: '', password: '', global_role: 'monteur' };
  protected memberForm = { slug: 'hez-640', user_id: 0, project_role: 'monteur' };
  protected dailyReportForm = {
    slug: 'hez-640',
    section_number: 1,
    report_date: new Date().toISOString().slice(0, 10),
    status: 'green',
    team: '',
    completed_work: '',
    open_work: '',
    material_missing: '',
    blockers: '',
    notes: '',
  };
  protected weeklyReportForm = {
    slug: 'hez-640',
    week_start: new Date().toISOString().slice(0, 10),
    week_end: new Date().toISOString().slice(0, 10),
    status: 'green',
    summary: '',
    next_week_plan: '',
    manpower_notes: '',
    material_notes: '',
    risks: '',
  };

  private selectedUploadFiles = new Map<string, File[]>();

  protected form: ProjectForm = {
    slug: 'hez-640',
    name: 'Heizungsmodernisierung',
    project_type: 'standard',
    address: '',
    responsible: '',
    construction_manager: '',
    foreman: '',
    planned_start: '',
    planned_end: '',
    notes: '',
    sections: [
      {
        number: 1,
        name: 'Kellerleitung',
        goal: '',
        planned_hours: 200,
        responsible: '',
        staff: '',
      },
    ],
  };

  constructor(private readonly http: HttpClient) {
    this.loadProjects();
    if (this.token()) {
      this.loadMe();
    }
  }

  protected setView(view: 'overview' | 'projects' | 'analyses' | 'outputs' | 'admin'): void {
    this.activeView.set(view);
    if (view === 'admin') {
      this.loadUsers();
    }
    if (view === 'analyses') {
      this.loadReportData();
    }
  }

  protected login(): void {
    this.clearMessages();
    this.http.post<LoginResponse>('/api/auth/login', this.loginForm).subscribe({
      next: (response) => {
        localStorage.setItem('hez_token', response.access_token);
        this.token.set(response.access_token);
        this.currentUser.set(response.user);
        this.message.set(`Angemeldet als ${response.user.display_name}.`);
        this.loadUsers();
        this.loadReportData();
      },
      error: (response) => this.error.set(this.formatHttpError(response, 'Login fehlgeschlagen.')),
    });
  }

  protected logout(): void {
    localStorage.removeItem('hez_token');
    this.token.set('');
    this.currentUser.set(null);
    this.users.set([]);
    this.dailyReports.set({});
    this.summaries.set({});
  }

  protected addSection(): void {
    this.form.sections.push({
      number: this.form.sections.length + 1,
      name: '',
      goal: '',
      planned_hours: null,
      responsible: '',
      staff: '',
    });
  }

  protected removeSection(index: number): void {
    if (this.form.sections.length === 1) {
      return;
    }

    this.form.sections.splice(index, 1);
    this.form.sections.forEach((section, sectionIndex) => {
      section.number = sectionIndex + 1;
    });
  }

  protected applySmallProjectTemplate(kind: 'bathroom' | 'gas_floor' | 'custom'): void {
    this.form.project_type = 'small';

    if (kind === 'bathroom') {
      this.form.name = 'Badsanierung';
      this.form.notes = 'Kleinprojekt: Badezimmer sanieren, Abbruch, Rohinstallation, Feininstallation, Abnahme.';
      this.form.sections = [
        { number: 1, name: 'Vorbereitung und Schutz', goal: 'Baustelle einrichten, Laufwege schuetzen, Bestand dokumentieren.', planned_hours: 8, responsible: '', staff: '' },
        { number: 2, name: 'Demontage und Rohinstallation', goal: 'Altbestand demontieren, Wasser/Abwasser/Heizung vorbereiten.', planned_hours: 24, responsible: '', staff: '' },
        { number: 3, name: 'Endmontage und Abnahme', goal: 'Objekte montieren, Dichtheit pruefen, Tagesbericht und Fotodoku abschliessen.', planned_hours: 16, responsible: '', staff: '' },
      ];
      return;
    }

    if (kind === 'gas_floor') {
      this.form.name = 'Gasetagenheizung';
      this.form.notes = 'Kleinprojekt: einzelne Gasetagenheizung erneuern oder neu bauen.';
      this.form.sections = [
        { number: 1, name: 'Bestand und Absicherung', goal: 'Bestand pruefen, Absperrungen, Schutzmassnahmen und Materialkontrolle.', planned_hours: 6, responsible: '', staff: '' },
        { number: 2, name: 'Montage Heizgeraet und Anschluesse', goal: 'Geraet setzen, Rohrleitungen anschliessen, Abgas/Verbrennungsluft beruecksichtigen.', planned_hours: 18, responsible: '', staff: '' },
        { number: 3, name: 'Pruefung, Inbetriebnahme und Einweisung', goal: 'Dichtheit, Funktion, Dokumentation und Einweisung abschliessen.', planned_hours: 8, responsible: '', staff: '' },
      ];
      return;
    }

    this.form.sections = [
      { number: 1, name: 'Arbeitspaket 1', goal: 'Leistungsumfang und Tagesziel beschreiben.', planned_hours: null, responsible: '', staff: '' },
    ];
  }

  protected createProject(): void {
    this.clearMessages();
    this.http.post('/api/projects', this.form).subscribe({
      next: () => {
        this.message.set('Projekt wurde angelegt und der Workspace wurde erstellt.');
        this.loadProjects();
      },
      error: (response) => {
        this.error.set(this.formatHttpError(response, 'Projekt konnte nicht angelegt werden.'));
      },
    });
  }

  protected runDryGenerate(slug: string): void {
    this.clearMessages();
    this.http.post<{ stderr: string }>(`/api/projects/${slug}/generate`, { run_codex: false }).subscribe({
      next: (response) => {
        this.message.set('Generator-Dry-Run wurde vorbereitet.');
        this.dryRunPrompt.set(response.stderr);
      },
      error: (response) => {
        this.error.set(this.formatHttpError(response, 'Dry-Run konnte nicht erstellt werden.'));
      },
    });
  }

  protected runGenerate(project: ProjectRead): void {
    if (!project.ready_for_generation) {
      this.error.set('Vor dem Generatorlauf bitte die offenen Punkte in der Projektkarte klären.');
      return;
    }

    this.clearMessages();
    this.generatingSlug.set(project.slug);
    this.http.post<{ returncode: number | null; stdout: string; stderr: string }>(
      `/api/projects/${project.slug}/generate`,
      { run_codex: true },
    ).subscribe({
      next: (response) => {
        this.generatingSlug.set(null);
        this.message.set(response.returncode === 0 ? 'Generatorlauf abgeschlossen.' : 'Generatorlauf wurde beendet.');
        this.dryRunPrompt.set([response.stdout, response.stderr].filter(Boolean).join('\n\n'));
        this.loadProjects();
        this.loadOutputs(project.slug);
      },
      error: (response) => {
        this.generatingSlug.set(null);
        this.error.set(this.formatHttpError(response, 'Generatorlauf konnte nicht gestartet werden.'));
        this.loadProjects();
      },
    });
  }

  protected onUploadSelection(slug: string, event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    const unsupportedFile = files.find((file) => !this.isAllowedUploadFile(file));
    if (unsupportedFile) {
      this.error.set(`${unsupportedFile.name} ist kein erlaubter Dateityp. Erlaubt sind CSV, PDF, XLSX und XLS.`);
      input.value = '';
      this.selectedUploadFiles.delete(slug);
      this.selectedUploadNames.update((current) => ({
        ...current,
        [slug]: [],
      }));
      return;
    }

    this.selectedUploadFiles.set(slug, files);
    this.selectedUploadNames.update((current) => ({
      ...current,
      [slug]: files.map((file) => file.name),
    }));
  }

  protected uploadFiles(slug: string): void {
    const files = this.selectedUploadFiles.get(slug) ?? [];
    if (files.length === 0) {
      this.error.set('Bitte zuerst eine oder mehrere Dateien auswählen.');
      return;
    }

    this.clearMessages();
    this.uploadingSlug.set(slug);
    this.uploadNextFile(slug, files, 0, []);
  }

  protected formatFileSize(sizeBytes?: number | null): string {
    if (sizeBytes === null || sizeBytes === undefined) {
      return 'Groesse unbekannt';
    }

    if (sizeBytes < 1024) {
      return `${sizeBytes} B`;
    }

    if (sizeBytes < 1024 * 1024) {
      return `${(sizeBytes / 1024).toFixed(1)} KB`;
    }

    return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
  }

  protected formatUploadDate(createdAt?: string | null): string {
    if (!createdAt) {
      return 'Datum unbekannt';
    }

    return new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date(createdAt));
  }

  protected publishedProjectsCount(): number {
    return this.projects().filter((project) => project.status === 'published').length;
  }

  protected readyProjectsCount(): number {
    return this.projects().filter((project) => project.ready_for_generation).length;
  }

  protected totalOutputFiles(): number {
    return Object.values(this.outputs()).reduce((total, output) => total + output.files.length, 0);
  }

  protected projectOutputCount(slug: string): number {
    return this.outputs()[slug]?.files.length ?? 0;
  }

  protected statusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Entwurf',
      generated: 'Generiert',
      generation_failed: 'Generatorfehler',
      publish_failed: 'Publikationsfehler',
      published: 'Veroeffentlicht',
    };

    return labels[status] ?? status;
  }

  protected projectTypeLabel(projectType: string): string {
    return projectType === 'small' ? 'Kleinprojekt' : 'Standardprojekt';
  }

  protected createUser(): void {
    this.clearMessages();
    this.http.post<UserRead>('/api/auth/users', this.userForm, { headers: this.authHeaders() }).subscribe({
      next: () => {
        this.message.set('Benutzer wurde angelegt.');
        this.userForm = { username: '', display_name: '', password: '', global_role: 'monteur' };
        this.loadUsers();
      },
      error: (response) => this.error.set(this.formatHttpError(response, 'Benutzer konnte nicht angelegt werden.')),
    });
  }

  protected addProjectMember(): void {
    this.clearMessages();
    this.http.post(`/api/reports/projects/${this.memberForm.slug}/members`, {
      user_id: Number(this.memberForm.user_id),
      project_role: this.memberForm.project_role,
    }, { headers: this.authHeaders() }).subscribe({
      next: () => this.message.set('Projektmitglied wurde gespeichert.'),
      error: (response) => this.error.set(this.formatHttpError(response, 'Projektmitglied konnte nicht gespeichert werden.')),
    });
  }

  protected submitDailyReport(): void {
    this.clearMessages();
    const { slug, ...payload } = this.dailyReportForm;
    this.http.post(`/api/reports/projects/${slug}/daily-reports`, payload, { headers: this.authHeaders() }).subscribe({
      next: () => {
        this.message.set('Tagesbericht gespeichert.');
        this.loadReports(slug);
        this.loadSummary(slug);
      },
      error: (response) => this.error.set(this.formatHttpError(response, 'Tagesbericht konnte nicht gespeichert werden.')),
    });
  }

  protected submitWeeklyReport(): void {
    this.clearMessages();
    const { slug, ...payload } = this.weeklyReportForm;
    this.http.post(`/api/reports/projects/${slug}/weekly-reports`, payload, { headers: this.authHeaders() }).subscribe({
      next: () => {
        this.message.set('Wochenbericht gespeichert.');
        this.loadSummary(slug);
      },
      error: (response) => this.error.set(this.formatHttpError(response, 'Wochenbericht konnte nicht gespeichert werden.')),
    });
  }

  protected loadOutputs(slug: string): void {
    this.outputsLoadingSlug.set(slug);
    this.http.get<ProjectOutputsRead>(`/api/projects/${slug}/outputs`).subscribe({
      next: (response) => {
        this.outputs.update((current) => ({
          ...current,
          [slug]: response,
        }));
        this.outputsLoadingSlug.set(null);
      },
      error: (response) => {
        this.outputsLoadingSlug.set(null);
        this.error.set(this.formatHttpError(response, 'Ausgaben konnten nicht geladen werden.'));
      },
    });
  }

  protected outputGroups(files: ProjectOutputFile[]): { folder: string; files: ProjectOutputFile[] }[] {
    const groups = new Map<string, ProjectOutputFile[]>();

    for (const file of files) {
      const folder = file.path.includes('/') ? file.path.slice(0, file.path.lastIndexOf('/')) : 'Root';
      groups.set(folder, [...(groups.get(folder) ?? []), file]);
    }

    return Array.from(groups.entries()).map(([folder, groupedFiles]) => ({
      folder,
      files: groupedFiles,
    }));
  }

  private loadProjects(): void {
    this.http.get<ProjectRead[]>('/api/projects').subscribe({
      next: (projects) => {
        this.projects.set(projects);
        projects
          .filter((project) => project.status === 'published')
          .forEach((project) => this.loadOutputs(project.slug));
        this.loadReportData();
      },
      error: () => this.projects.set([]),
    });
  }

  private loadMe(): void {
    this.http.get<UserRead>('/api/auth/me', { headers: this.authHeaders() }).subscribe({
      next: (user) => {
        this.currentUser.set(user);
        this.loadUsers();
        this.loadReportData();
      },
      error: () => this.logout(),
    });
  }

  private loadUsers(): void {
    if (!this.token()) {
      return;
    }
    this.http.get<UserRead[]>('/api/auth/users', { headers: this.authHeaders() }).subscribe({
      next: (users) => {
        this.users.set(users);
        if (!this.memberForm.user_id && users.length > 0) {
          this.memberForm.user_id = users[0].id;
        }
      },
      error: () => undefined,
    });
  }

  private loadReportData(): void {
    if (!this.token()) {
      return;
    }
    this.projects().forEach((project) => {
      this.loadReports(project.slug);
      this.loadSummary(project.slug);
    });
  }

  private loadReports(slug: string): void {
    this.http.get<DailyReportRead[]>(`/api/reports/projects/${slug}/daily-reports`, { headers: this.authHeaders() }).subscribe({
      next: (reports) => this.dailyReports.update((current) => ({ ...current, [slug]: reports })),
      error: () => undefined,
    });
  }

  private loadSummary(slug: string): void {
    this.http.get<ReportSummary>(`/api/reports/projects/${slug}/summary`, { headers: this.authHeaders() }).subscribe({
      next: (summary) => this.summaries.update((current) => ({ ...current, [slug]: summary })),
      error: () => undefined,
    });
  }

  private authHeaders(): Record<string, string> {
    return this.token() ? { Authorization: `Bearer ${this.token()}` } : {};
  }

  private clearMessages(): void {
    this.message.set('');
    this.error.set('');
    this.dryRunPrompt.set('');
  }

  private uploadNextFile(
    slug: string,
    files: File[],
    index: number,
    uploaded: ProjectUploadRead[],
  ): void {
    if (index >= files.length) {
      this.uploadingSlug.set(null);
      this.message.set(`${uploaded.length} Datei(en) wurden hochgeladen.`);
      this.selectedUploadFiles.delete(slug);
      this.selectedUploadNames.update((current) => ({
        ...current,
        [slug]: [],
      }));
      this.loadProjects();
      return;
    }

    const formData = new FormData();
    formData.append('file', files[index]);

    this.http.post<ProjectUploadRead>(`/api/projects/${slug}/uploads`, formData).subscribe({
      next: (response) => {
        this.uploadNextFile(slug, files, index + 1, [...uploaded, response]);
      },
      error: (response) => {
        this.uploadingSlug.set(null);
        this.error.set(this.formatHttpError(response, `${files[index].name} konnte nicht hochgeladen werden.`));
      },
    });
  }

  private isAllowedUploadFile(file: File): boolean {
    return ['.csv', '.pdf', '.xlsx', '.xls'].some((suffix) => file.name.toLowerCase().endsWith(suffix));
  }

  private formatHttpError(response: { error?: { detail?: unknown } }, fallback: string): string {
    const detail = response?.error?.detail;

    if (typeof detail === 'string') {
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const location = Array.isArray(item?.loc) ? item.loc.join('.') : undefined;
          const message = typeof item?.msg === 'string' ? item.msg : undefined;
          return [location, message].filter(Boolean).join(': ');
        })
        .filter(Boolean)
        .join('\n') || fallback;
    }

    return fallback;
  }
}
