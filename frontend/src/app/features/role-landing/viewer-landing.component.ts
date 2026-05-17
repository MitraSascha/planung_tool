import { CommonModule } from '@angular/common';
import { Component, computed, inject, input, OnChanges, SimpleChanges } from '@angular/core';

import { ProjectOutputFile, ProjectRead } from '../../core/models';
import { ProjectService } from '../../core/services/project.service';
import { inferDocumentType, sortDocumentsFormFirst } from '../../shared/utils/format';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { AuthedUrlPipe } from '../../shared/pipes/authed-url.pipe';

@Component({
  selector: 'app-viewer-landing',
  imports: [CommonModule, AuthedUrlPipe, EmptyStateComponent],
  templateUrl: './viewer-landing.component.html',
  styleUrl: './landing-sections.scss',
})
export class ViewerLandingComponent implements OnChanges {
  private readonly projectService = inject(ProjectService);

  readonly project = input.required<ProjectRead>();

  protected readonly outputsByProject = this.projectService.outputs;
  protected readonly inferDocumentType = inferDocumentType;

  protected readonly outputs = computed<ProjectOutputFile[]>(() => {
    const files = this.outputsByProject()[this.project().slug]?.files ?? [];
    return sortDocumentsFormFirst(files);
  });

  ngOnChanges(changes: SimpleChanges): void {
    if ('project' in changes) {
      this.projectService
        .loadOutputs(this.project().slug)
        .subscribe({ error: () => undefined });
    }
  }
}
