import axios from 'axios';
import { apiConfig } from '../config/api';
import { useUserStore } from '../store/user';

/**
 * 统一 axios 实例：
 * 1. 自动加 Authorization: Bearer <accessToken>
 * 2. 收到 401 时自动刷新访问令牌，并重试原请求一次
 */
export const http = axios.create({
  baseURL: apiConfig.baseURL,
  timeout: 20000
});

http.interceptors.request.use((config) => {
  const userStore = useUserStore();
  if (userStore.token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${userStore.token}`;
  }
  return config;
});

// 同一时刻只允许一个刷新请求，避免并发 401 触发多次刷新
let refreshPromise = null;

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    if (!original || error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }

    const url = original.url || '';
    const skipUrls = [
      '/api/user/login',
      '/api/user/register',
      '/api/user/refresh',
      '/api/user/logout'
    ];
    if (skipUrls.some((path) => url.includes(path))) {
      return Promise.reject(error);
    }

    const userStore = useUserStore();
    if (!userStore.refreshToken) {
      return Promise.reject(error);
    }

    original._retry = true;

    if (!refreshPromise) {
      refreshPromise = userStore.refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }

    const refreshed = await refreshPromise;
    if (!refreshed) {
      return Promise.reject(error);
    }

    original.headers = original.headers || {};
    original.headers.Authorization = `Bearer ${userStore.token}`;
    return http(original);
  }
);

/**
 * 给 fetch / SSE 用的鉴权封装。
 * EventSource 不能自定义请求头，所以项目里用的是 fetch + ReadableStream，
 * 这里同样可以加 Authorization，并在 401 时刷新重试。
 */
export async function authFetch(url, options = {}) {
  const userStore = useUserStore();

  const buildOptions = () => {
    const headers = new Headers(options.headers || {});
    if (userStore.token) {
      headers.set('Authorization', `Bearer ${userStore.token}`);
    }
    return { ...options, headers };
  };

  let response = await fetch(url, buildOptions());

  if (response.status === 401 && userStore.refreshToken) {
    const refreshed = await userStore.refreshAccessToken();
    if (refreshed) {
      response = await fetch(url, buildOptions());
    }
  }

  return response;
}