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
}

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  protected readonly title = signal('hez-tool-frontend');
  protected projects = signal<ProjectRead[]>([]);
  protected message = signal('');
  protected error = signal('');
  protected dryRunPrompt = signal('');

  protected form: ProjectForm = {
    slug: 'hez-640',
    name: 'Heizungsmodernisierung',
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

  private loadProjects(): void {
    this.http.get<ProjectRead[]>('/api/projects').subscribe({
      next: (projects) => this.projects.set(projects),
      error: () => this.projects.set([]),
    });
  }

  private clearMessages(): void {
    this.message.set('');
    this.error.set('');
    this.dryRunPrompt.set('');
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
