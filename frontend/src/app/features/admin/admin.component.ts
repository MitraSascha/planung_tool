import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import { NotificationService } from '../../core/services/notification.service';
import { ProjectService } from '../../core/services/project.service';
import { ReportsService } from '../../core/services/reports.service';
import { UsersService } from '../../core/services/users.service';
import { formatHttpError } from '../../core/services/error-format';

@Component({
  selector: 'app-admin',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent {
  private readonly projectService = inject(ProjectService);
  private readonly usersService = inject(UsersService);
  private readonly reportsService = inject(ReportsService);
  private readonly notifications = inject(NotificationService);
  private readonly auth = inject(AuthService);

  protected readonly projects = this.projectService.projects;
  protected readonly users = this.usersService.users;
  protected readonly members = this.reportsService.members;

  protected userForm = {
    username: '',
    display_name: '',
    password: '',
    global_role: 'monteur',
  };

  protected memberForm = {
    slug: 'hez-640',
    user_id: 0,
    project_role: 'monteur',
  };

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.usersService.list().subscribe({
        next: (users) => {
          if (!this.memberForm.user_id && users.length > 0) {
            this.memberForm.user_id = users[0].id;
          }
        },
        error: () => undefined,
      });
      this.projectService.list().subscribe({
        next: (projects) => {
          if (projects.length > 0 && !projects.find((p) => p.slug === this.memberForm.slug)) {
            this.memberForm.slug = projects[0].slug;
          }
          for (const project of projects) {
            this.reportsService.loadMembers(project.slug).subscribe({ error: () => undefined });
          }
        },
        error: () => undefined,
      });
    }
  }

  protected memberList(slug: string) {
    return this.members()[slug] ?? [];
  }

  protected createUser(): void {
    this.notifications.clear();
    this.usersService.create(this.userForm).subscribe({
      next: () => {
        this.notifications.showMessage('Benutzer wurde angelegt.');
        this.userForm = { username: '', display_name: '', password: '', global_role: 'monteur' };
        this.usersService.list().subscribe({ error: () => undefined });
      },
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Benutzer konnte nicht angelegt werden.'),
        ),
    });
  }

  protected addProjectMember(): void {
    this.notifications.clear();
    this.reportsService
      .addMember(this.memberForm.slug, {
        user_id: Number(this.memberForm.user_id),
        project_role: this.memberForm.project_role,
      })
      .subscribe({
        next: () => {
          this.notifications.showMessage('Projektmitglied wurde gespeichert.');
          this.reportsService.loadMembers(this.memberForm.slug).subscribe({ error: () => undefined });
        },
        error: (response) =>
          this.notifications.showError(
            formatHttpError(response, 'Projektmitglied konnte nicht gespeichert werden.'),
          ),
      });
  }

  protected refreshUsers(): void {
    this.usersService.list().subscribe({ error: () => undefined });
  }

  protected refreshMembers(): void {
    for (const project of this.projects()) {
      this.reportsService.loadMembers(project.slug).subscribe({ error: () => undefined });
    }
  }
}
