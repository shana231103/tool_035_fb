// File: frontend/src/services/bulkJobsApi.js
import apiClient from './api.js';
export const createBulkJobsApi = client => ({
  async preview(body) { return (await client.post('/jobs/bulk/preview', body)).data; },
  async create(body) { return (await client.post('/jobs/bulk', body)).data; },
  async lookup(id) { return (await client.get(`/jobs/bulk/${encodeURIComponent(id)}`)).data; },
  async review(id) { return (await client.post(`/jobs/${encodeURIComponent(id)}/bulk-review`)).data; },
  async start(id, digest) { return (await client.post(`/jobs/${encodeURIComponent(id)}/start`, {bulk_review_sha256:digest})).data; },
});
export const bulkJobsApi = createBulkJobsApi(apiClient);
