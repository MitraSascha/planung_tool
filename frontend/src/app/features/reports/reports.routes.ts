import { Routes } from '@angular/router';

export const REPORTS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./reports.component').then((m) => m.ReportsComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'daily' },
      {
        path: 'daily',
        loadComponent: () =>
          import('./daily-reports/daily-reports.component').then((m) => m.DailyReportsComponent),
      },
      {
        path: 'weekly',
        loadComponent: () =>
          import('./weekly-reports/weekly-reports.component').then((m) => m.WeeklyReportsComponent),
      },
    ],
  },
];
