import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { LoginRequest, LoginResponse, UserRead } from '../models';

const TOKEN_KEY = 'hez_token';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  private readonly tokenSignal = signal<string>(localStorage.getItem(TOKEN_KEY) ?? '');
  private readonly userSignal = signal<UserRead | null>(null);

  readonly token = this.tokenSignal.asReadonly();
  readonly currentUser = this.userSignal.asReadonly();
  readonly isAuthenticated = computed(() => Boolean(this.tokenSignal()));

  login(credentials: LoginRequest): Observable<LoginResponse> {
    return this.http.post<LoginResponse>('/api/auth/login', credentials).pipe(
      tap((response) => {
        localStorage.setItem(TOKEN_KEY, response.access_token);
        this.tokenSignal.set(response.access_token);
        this.userSignal.set(response.user);
      }),
    );
  }

  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    this.tokenSignal.set('');
    this.userSignal.set(null);
  }

  loadCurrentUser(): Observable<UserRead> {
    return this.http.get<UserRead>('/api/auth/me').pipe(
      tap((user) => this.userSignal.set(user)),
    );
  }

  setUser(user: UserRead | null): void {
    this.userSignal.set(user);
  }

  authHeader(): Record<string, string> {
    const token = this.tokenSignal();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
