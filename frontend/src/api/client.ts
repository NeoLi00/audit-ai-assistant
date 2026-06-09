import axios from 'axios';

export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('audit_ai_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.response?.data?.message || '请求失败';
    return Promise.reject(new Error(message));
  },
);

export async function unwrap<T>(promise: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const response = await promise;
  return response.data.data;
}

