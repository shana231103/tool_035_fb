// File: frontend/src/services/api.js
import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 30000,
});

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

export const mailboxApi = {
  async configuration() { return (await apiClient.get('/mailbox-connections/configuration')).data; },
  async configure(clientId) { return (await apiClient.put('/mailbox-connections/configuration', {client_id:clientId})).data; },
  async list() { return (await apiClient.get('/mailbox-connections')).data; },
  async login(data = {}) { return (await apiClient.post('/mailbox-connections/login', data)).data; },
  async loginStatus(id) { return (await apiClient.get(`/mailbox-connections/logins/${encodeURIComponent(id)}`)).data; },
  async cancelLogin(id) { await apiClient.delete(`/mailbox-connections/logins/${encodeURIComponent(id)}`); },
  async map(id, data) { return (await apiClient.put(`/mailbox-connections/${encodeURIComponent(id)}/mapping`, data)).data; },
  async disconnect(id) { await apiClient.delete(`/mailbox-connections/${encodeURIComponent(id)}`); },
};

export default apiClient;
