import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { GlobalRole, UserRead } from '../models';

export interface CreateUserPayload {
  username: string;
  display_name: string;
  password: string;
  global_role: GlobalRole | string;
}

@Injectable({ providedIn: 'root' })
export class UsersService {
  private readonly http = inject(HttpClient);

  private readonly usersSignal = signal<UserRead[]>([]);
  readonly users = this.usersSignal.asReadonly();

  list(): Observable<UserRead[]> {
    return this.http.get<UserRead[]>('/api/auth/users').pipe(
      tap((users) => this.usersSignal.set(users)),
    );
  }

  create(payload: CreateUserPayload): Observable<UserRead> {
    return this.http.post<UserRead>('/api/auth/users', payload);
  }

  clear(): void {
    this.usersSignal.set([]);
  }
}
