import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { GlobalRole, ProjectRead } from '../../core/models';
import { AuthService } from '../../core/services/auth.service';
import { ProjectService } from '../../core/services/project.service';
import { statusLabel } from '../../shared/utils/format';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { MonteurLandingComponent } from './monteur-landing.component';
import { ObermonteurLandingComponent } from './obermonteur-landing.component';
import { BauleitungLandingComponent } from './bauleitung-landing.component';
import { ProjektleitungLandingComponent } from './projektleitung-landing.component';
import { ViewerLandingComponent } from './viewer-landing.component';

/**
 * RoleLandingComponent dispatches the right per-role landing for a single project,
 * OR shows a multi-project picker if the user has no slug yet and several projects.
 *
 * Routes:
 *   /landing                 -> multi-project picker (or auto-redirect when only one)
 *   /projects/:slug/role     -> resolve effective role and render the matching sub-component
 */
@Component({
  selector: 'app-role-landing',
  imports: [
    CommonModule,
    RouterLink,
    EmptyStateComponent,
    MonteurLandingComponent,
    ObermonteurLandingComponent,
    BauleitungLandingComponent,
    ProjektleitungLandingComponent,
    ViewerLandingComponent,
  ],
  templateUrl: './role-landing.component.html',
  styleUrl: './role-landing.component.scss',
})
export class RoleLandingComponent {
  private readonly auth = inject(AuthService);
  private readonly projectService = inject(ProjectService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly currentUser = this.auth.currentUser;
  protected readonly projects = this.projectService.projects;
  protected readonly statusLabel = statusLabel;

  protected readonly slug = signal<string | null>(null);
  protected readonly loading = signal<boolean>(true);

  /** The effective role for the (single) project that we currently render. */
  protected readonly effectiveRole = computed<GlobalRole | string>(() => {
    const user = this.currentUser();
    if (!user) {
      return 'viewer';
    }
    // Without a member-role lookup endpoint exposed to all roles, we fall back to
    // the user's global role as the effective role for the project view.
    return user.global_role;
  });

  protected readonly currentProject = computed<ProjectRead | null>(() => {
    const slug = this.slug();
    if (!slug) {
      return null;
    }
    return this.projects().find((p) => p.slug === slug) ?? null;
  });

  constructor() {
    this.route.paramMap.subscribe((params) => {
      const slug = params.get('slug');
      this.slug.set(slug);
    });

    if (this.auth.isAuthenticated()) {
      this.projectService.list().subscribe({
        next: (projects) => {
          this.loading.set(false);
          // Auto-redirect at /landing if the user is member of exactly one project.
          if (!this.slug() && projects.length === 1) {
            this.router.navigate(['/projects', projects[0].slug, 'role'], {
              replaceUrl: true,
            });
          }
        },
        error: () => this.loading.set(false),
      });
    } else {
      this.loading.set(false);
    }
  }

  protected openProject(slug: string): void {
    this.router.navigate(['/projects', slug, 'role']);
  }
}
