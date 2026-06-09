import { apiClient, unwrap } from './client';

export type UserInfo = {
  id: string;
  username: string;
  display_name: string;
  role: string;
  department: string;
};

export type LoginResult = {
  access_token: string;
  token_type: string;
  user: UserInfo;
};

export function login(username: string, password: string) {
  return unwrap<LoginResult>(apiClient.post('/auth/login', { username, password }));
}

export function fetchMe() {
  return unwrap<UserInfo>(apiClient.get('/auth/me'));
}

export function logout() {
  return unwrap<Record<string, unknown>>(apiClient.post('/auth/logout'));
}

