// File: frontend/src/services/api.js
import axios from "axios";
import { mailboxReason } from './mailboxConnect.js';
import { useAuthStore } from "../stores/authStore.js";
import { authLifecycle } from "./authLifecycle.js";

const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 30000,
});

apiClient.interceptors.request.use((config) => {
  try {
    const authStore = useAuthStore();
    const method = config.method?.toLowerCase();
    if (["post", "put", "patch", "delete"].includes(method)) {
      if (authStore.csrfToken) {
        config.headers["X-CSRF-Token"] = authStore.csrfToken;
      }
      if (authStore.sessionContext) {
        config.headers["X-Operator-Session"] = authStore.sessionContext;
      }
    }
  } catch (e) {
    // Pinia not yet initialized or test environment
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      authLifecycle.handleAuthLoss(error);
    }
    return Promise.reject(error);
  }
);

export { tasksApi } from "./tasksApi.js";

export const jobsApi = {
  async listJobsPage(limit = 50, offset = 0) {
    return (await apiClient.get('/jobs/page', {params: {limit, offset}})).data;
  },
  async listJobs(limit = 50, offset = 0) {
    const res = await apiClient.get("/jobs", { params: { limit, offset } });
    return res.data;
  },

  async getJob(id) {
    const res = await apiClient.get(`/jobs/${id}`);
    return res.data;
  },

  async createJob(formData) {
    const res = await apiClient.post("/jobs", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return res.data;
  },

  async startJob(id) {
    const res = await apiClient.post(`/jobs/${id}/start`);
    return res.data;
  },

  async stopJob(id) {
    const res = await apiClient.post(`/jobs/${id}/stop`);
    return res.data;
  },

  async retryFailedTasks(id) {
    return (await apiClient.post(`/jobs/${id}/retry-failed`)).data;
  },
};

export const profilesApi = {
  async listProfiles() {
    const res = await apiClient.get("/profiles");
    return res.data;
  },

  async createProfile(data) {
    const res = await apiClient.post("/profiles", data);
    return res.data;
  },

  async updateProfile(id, data) {
    return (await apiClient.put(`/profiles/${id}`, data)).data;
  },

  async deleteProfile(id) {
    await apiClient.delete(`/profiles/${id}`);
  },
};

export const proxiesApi = {
  async listProxies() {
    const res = await apiClient.get("/proxies");
    return res.data;
  },

  async addProxy(data) {
    const res = await apiClient.post("/proxies", data);
    return res.data;
  },

  async testProxy(id) {
    const res = await apiClient.post(`/proxies/${id}/test`);
    return res.data;
  },

  async deleteProxy(id) {
    await apiClient.delete(`/proxies/${id}`);
  },
};

export const verificationApi = {
  async resend(id, data) { return (await apiClient.post(`/tasks/${id}/verification/resend`, data)).data; },
};

export const createMailboxApi = (client) => ({
  async capabilities() { return (await client.get('/mailbox-connections/capabilities')).data; },
  async reserve() { return (await client.post('/mailbox-connections/reservations', {}, {timeout:10000})).data; },
  async connect(id, credentials, signal) {
    const data = {connection_id:id, credentials};
    credentials = '';
    let response;
    try {
      response = await client.post('/mailbox-connections/connect', data, {signal, timeout:45000});
      return response.data;
    } catch (error) {
      const reason = mailboxReason(error);
      if (error.config) error.config.data = '';
      throw new Error(reason);
    } finally {
      data.credentials = '';
      if (response?.config) response.config.data = '';
    }
  },
  async list() { return (await client.get('/mailbox-connections')).data; },
  async map(id, data) { return (await client.put(`/mailbox-connections/${encodeURIComponent(id)}/mapping`, data)).data; },
  async disconnect(id) { await client.delete(`/mailbox-connections/${encodeURIComponent(id)}`); },
});
export const mailboxApi = createMailboxApi(apiClient);

export default apiClient;
