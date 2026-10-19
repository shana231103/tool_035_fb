// File: frontend/src/services/tasksApi.js
import apiClient from './api.js';

export function createTasksApi(client) {
  const get = async (path, config) => (await client.get(path, config)).data;
  const post = async (path, body) => (await client.post(path, body)).data;
  return {
    createTask: form => post('/tasks', form),
    listTasks: ({limit = 50, offset = 0} = {}) => get('/tasks', {params: {limit, offset}}),
    getTask: id => get(`/tasks/${id}`),
    startTask: (id, {command_id, expected_version}) => post(`/tasks/${id}/start`, {command_id, expected_version}),
    getStartReceipt: (id, command) => get(`/tasks/${id}/starts/${command}`),
    stopTask: (id, {command_id, expected_version, attempt_id = null}) => post(`/tasks/${id}/stop`, {command_id, expected_version, attempt_id}),
    retryTask: (id, {expected_version}) => post(`/tasks/${id}/retry`, {expected_version}),
    getExecutionStatus: () => get('/execution/status'),
    getControlStatus: (id, config) => get(`/controls/${id}`, config),
  };
}

export const tasksApi = createTasksApi({get: (...args) => apiClient.get(...args), post: (...args) => apiClient.post(...args)});
export default tasksApi;
