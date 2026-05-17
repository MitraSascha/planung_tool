export type GlobalRole =
  | 'admin'
  | 'projektleitung'
  | 'bauleitung'
  | 'obermonteur'
  | 'monteur'
  | 'viewer';

export type ProjectRole = Exclude<GlobalRole, 'admin'>;

export interface UserRead {
  id: number;
  username: string;
  display_name: string;
  global_role: GlobalRole | string;
  active: boolean;
  created_at: string;
}

export interface ProjectMemberRead {
  id: number;
  user_id: number;
  username: string;
  display_name: string;
  project_role: ProjectRole | string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserRead;
}
