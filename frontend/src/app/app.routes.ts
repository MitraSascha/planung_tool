import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./features/overview/overview.component').then((m) => m.OverviewComponent),
    pathMatch: 'full',
  },
  {
    path: 'projects',
    loadComponent: () =>
      import('./features/projects-list/projects-list.component').then(
        (m) => m.ProjectsListComponent,
      ),
  },
  {
    path: 'projects/new',
    loadComponent: () =>
      import('./features/project-form/project-form.component').then(
        (m) => m.ProjectFormComponent,
      ),
  },
  {
    path: 'landing',
    loadComponent: () =>
      import('./features/role-landing/role-landing.component').then(
        (m) => m.RoleLandingComponent,
      ),
  },
  {
    // Legacy-Pfad → konsolidierte Projektliste. ProjectsListComponent erkennt
    // den /overview/all-Prefix und stellt den View-Mode initial auf "table".
    path: 'overview/all',
    loadComponent: () =>
      import('./features/projects-list/projects-list.component').then(
        (m) => m.ProjectsListComponent,
      ),
  },
  {
    path: 'projects/:slug/role',
    loadComponent: () =>
      import('./features/role-landing/role-landing.component').then(
        (m) => m.RoleLandingComponent,
      ),
  },
  {
    path: 'projects/:slug/details',
    loadComponent: () =>
      import('./features/project-detail/project-detail.component').then(
        (m) => m.ProjectDetailComponent,
      ),
  },
  {
    path: 'projects/:slug/edit',
    loadComponent: () =>
      import('./features/project-form/project-form.component').then(
        (m) => m.ProjectFormComponent,
      ),
  },
  {
    path: 'projects/:slug/generate',
    loadComponent: () =>
      import('./features/generation-status/generation-status.component').then(
        (m) => m.GenerationStatusComponent,
      ),
  },
  {
    path: 'projects/:slug/heating-design/import',
    loadComponent: () =>
      import('./features/heating-design/heating-design-import.component').then(
        (m) => m.HeatingDesignImportComponent,
      ),
  },
  {
    path: 'projects/:slug/heating-design/edit',
    loadComponent: () =>
      import('./features/heating-design/heating-design-editor.component').then(
        (m) => m.HeatingDesignEditorComponent,
      ),
  },
  {
    path: 'projects/:slug/reports/daily/new',
    loadComponent: () =>
      import('./features/reports/daily-report-form/daily-report-form.component').then(
        (m) => m.DailyReportFormComponent,
      ),
  },
  {
    path: 'projects/:slug/reports/daily/:reportId/edit',
    loadComponent: () =>
      import('./features/reports/daily-report-form/daily-report-form.component').then(
        (m) => m.DailyReportFormComponent,
      ),
  },
  {
    path: 'projects/:slug/reports/weekly/new',
    loadComponent: () =>
      import('./features/reports/weekly-report-form/weekly-report-form.component').then(
        (m) => m.WeeklyReportFormComponent,
      ),
  },
  {
    path: 'projects/:slug/reports',
    loadChildren: () =>
      import('./features/reports/reports.routes').then((m) => m.REPORTS_ROUTES),
  },
  {
    path: 'projects/:slug/open-points/material/new',
    loadComponent: () =>
      import('./features/open-points/material-form/material-form.component').then(
        (m) => m.MaterialFormComponent,
      ),
  },
  {
    path: 'projects/:slug/open-points/blocker/new',
    loadComponent: () =>
      import('./features/open-points/blocker-form/blocker-form.component').then(
        (m) => m.BlockerFormComponent,
      ),
  },
  {
    path: 'projects/:slug/open-points',
    loadComponent: () =>
      import('./features/open-points/open-points.component').then((m) => m.OpenPointsComponent),
  },
  {
    path: 'projects/:slug/voice-notes',
    loadComponent: () =>
      import('./features/voice-notes/voice-notes.component').then((m) => m.VoiceNotesComponent),
  },
  {
    path: 'projects/:slug/offers',
    loadComponent: () =>
      import('./features/offers/offers.component').then((m) => m.OffersComponent),
  },
  {
    path: 'projects/:slug/nachkalkulation',
    loadComponent: () =>
      import('./features/nachkalkulation/nachkalkulation.component').then(
        (m) => m.NachkalkulationComponent,
      ),
  },
  {
    path: 'anomalies',
    loadComponent: () =>
      import('./features/anomalies/anomalies.component').then(
        (m) => m.AnomaliesComponent,
      ),
  },
  {
    path: 'material-issues',
    loadComponent: () =>
      import('./features/material-issues-all/material-issues-all.component').then(
        (m) => m.MaterialIssuesAllComponent,
      ),
  },
  {
    path: 'projects/:slug/anomalies',
    loadComponent: () =>
      import('./features/anomalies/anomalies.component').then(
        (m) => m.AnomaliesComponent,
      ),
  },
  {
    path: 'analyses',
    loadComponent: () =>
      import('./features/analyses/analyses.component').then((m) => m.AnalysesComponent),
  },
  {
    path: 'outputs',
    loadComponent: () =>
      import('./features/project-outputs/project-outputs.component').then(
        (m) => m.ProjectOutputsComponent,
      ),
  },
  {
    path: 'admin',
    loadComponent: () =>
      import('./features/admin/admin.component').then((m) => m.AdminComponent),
  },
  {
    path: 'admin/push',
    loadComponent: () =>
      import('./features/admin/push-settings/push-settings.component').then(
        (m) => m.PushSettingsComponent,
      ),
  },
  {
    path: 'admin/dsgvo',
    loadComponent: () =>
      import('./features/admin/dsgvo-panel/dsgvo-panel.component').then(
        (m) => m.DsgvoPanelComponent,
      ),
  },
  {
    path: 'settings/push',
    loadComponent: () =>
      import('./features/admin/push-settings/push-settings.component').then(
        (m) => m.PushSettingsComponent,
      ),
  },
  {
    path: 'projects/:slug',
    redirectTo: 'projects/:slug/role',
    pathMatch: 'full',
  },
  { path: '**', redirectTo: '' },
];
