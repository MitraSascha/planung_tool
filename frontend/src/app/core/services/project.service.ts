import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

import {
  GenerateStartResponse,
  GenerationRunRead,
  ProjectForm,
  ProjectOutputsRead,
  ProjectRead,
  ProjectUploadRead,
} from '../models';

@Injectable({ providedIn: 'root' })
export class ProjectService {
  private readonly http = inject(HttpClient);

  private readonly projectsSignal = signal<ProjectRead[]>([]);
  private readonly outputsSignal = signal<Record<string, ProjectOutputsRead>>({});
  private readonly generationRunsSignal = signal<Record<string, GenerationRunRead>>({});

  readonly projects = this.projectsSignal.asReadonly();
  readonly outputs = this.outputsSignal.asReadonly();
  readonly generationRuns = this.generationRunsSignal.asReadonly();

  list(): Observable<ProjectRead[]> {
    return this.http.get<ProjectRead[]>('/api/projects').pipe(
      tap((projects) => this.projectsSignal.set(projects)),
    );
  }

  get(slug: string): Observable<ProjectRead> {
    return this.http.get<ProjectRead>(`/api/projects/${slug}`);
  }

  create(payload: ProjectForm): Observable<unknown> {
    return this.http.post('/api/projects', payload);
  }

  update(slug: string, payload: ProjectForm): Observable<ProjectRead> {
    const { slug: _ignored, ...body } = payload;
    return this.http.put<ProjectRead>(`/api/projects/${slug}`, body);
  }

  uploadFile(slug: string, file: File): Observable<ProjectUploadRead> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<ProjectUploadRead>(`/api/projects/${slug}/uploads`, formData);
  }

  dryRun(slug: string): Observable<GenerateStartResponse> {
    return this.http.post<GenerateStartResponse>(
      `/api/projects/${slug}/generate`,
      { run_codex: false },
    );
  }

  startGeneration(slug: string): Observable<GenerateStartResponse> {
    return this.http.post<GenerateStartResponse>(
      `/api/projects/${slug}/generate`,
      { run_codex: true },
    );
  }

  getRun(slug: string, runId: number): Observable<GenerationRunRead> {
    return this.http.get<GenerationRunRead>(`/api/projects/${slug}/generate/${runId}`);
  }

  loadOutputs(slug: string): Observable<ProjectOutputsRead> {
    return this.http.get<ProjectOutputsRead>(`/api/projects/${slug}/outputs`).pipe(
      tap((response) =>
        this.outputsSignal.update((current) => ({ ...current, [slug]: response })),
      ),
    );
  }

  fetchOutputFile(viewUrl: string): Observable<Blob> {
    return this.http.get(viewUrl, { responseType: 'blob' });
  }

  setGenerationRun(slug: string, run: GenerationRunRead): void {
    this.generationRunsSignal.update((current) => ({ ...current, [slug]: run }));
  }

  clearProjects(): void {
    this.projectsSignal.set([]);
    this.outputsSignal.set({});
    this.generationRunsSignal.set({});
  }
}
