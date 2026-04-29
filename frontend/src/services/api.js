import axios from 'axios';

const API_BASE = 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: refreshToken });
          const newToken = res.data.access_token;
          localStorage.setItem('access_token', newToken);
          original.headers.Authorization = `Bearer ${newToken}`;
          return api(original);
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      } else {
        localStorage.clear();
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  login: (username, password) => api.post('/auth/login', { username, password }),
  me: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
  register: (data) => api.post('/auth/register', data),
};

export const dashboardAPI = {
  stats: () => api.get('/dashboard/stats'),
  statusChart: () => api.get('/dashboard/charts/status'),
  trendChart: (days = 30) => api.get(`/dashboard/charts/trend?days=${days}`),
  vendorChart: () => api.get('/dashboard/charts/vendors'),
  topClients: (limit = 10) => api.get(`/dashboard/top-clients?limit=${limit}`),
  tradingStats: () => api.get('/dashboard/trading-stats'),
};

export const queryAPI = {
  ask: (question, database = null, category = null) =>
    api.post('/query', { question, database, category }),
  databases: () => api.get('/query/databases'),
  categories: (database = null) =>
    api.get('/query/categories', { params: database ? { database } : {} }),
  history: (page = 1, limit = 20) =>
    api.get(`/query/history?page=${page}&limit=${limit}`),
  exportCSV: (sql, database) =>
    api.post('/query/export-csv', { sql, database }, { responseType: 'blob' }),
};

export const adminAPI = {
  users: () => api.get('/admin/users'),
  queryLogs: (page = 1, limit = 20) => api.get(`/admin/logs/queries?page=${page}&limit=${limit}`),
  errorLogs: (page = 1, limit = 20) => api.get(`/admin/logs/errors?page=${page}&limit=${limit}`),
};

export default api;