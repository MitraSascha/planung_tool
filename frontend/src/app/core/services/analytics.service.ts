import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { PortfolioAnalytics, ProjectAnalytics } from '../models';

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private readonly http = inject(HttpClient);

  project(slug: string, weeksBack = 4): Observable<ProjectAnalytics> {
    return this.http.get<ProjectAnalytics>(
      `/api/analytics/projects/${slug}/analytics?weeks_back=${weeksBack}`,
    );
  }

  portfolio(): Observable<PortfolioAnalytics> {
    return this.http.get<PortfolioAnalytics>('/api/analytics/portfolio');
  }
}
