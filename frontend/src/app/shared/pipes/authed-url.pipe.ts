import { Pipe, PipeTransform, inject } from '@angular/core';

import { AuthService } from '../../core/services/auth.service';

/**
 * Appends `?token=<jwt>` (or `&token=...`) to a same-origin API URL so that
 * direct browser navigations (e.g. `<a href>` opened in a new tab) carry
 * authentication. The standard request interceptor only injects the
 * `Authorization` header for XHR/fetch issued by the SPA — it cannot reach
 * navigations the browser performs on its own.
 *
 * Use exclusively on URLs that point at endpoints accepting
 * `?token=...`-style auth (file/PDF download endpoints). Don't sprinkle it
 * on arbitrary API URLs: JWTs in URLs land in browser history and access
 * logs, which is acceptable for short-lived download links but not for the
 * full API surface.
 */
@Pipe({
  name: 'authedUrl',
  standalone: true,
})
export class AuthedUrlPipe implements PipeTransform {
  private readonly auth = inject(AuthService);

  transform(url: string | null | undefined): string {
    if (!url) {
      return '';
    }
    const token = this.auth.token();
    if (!token) {
      return url;
    }
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}token=${encodeURIComponent(token)}`;
  }
}
