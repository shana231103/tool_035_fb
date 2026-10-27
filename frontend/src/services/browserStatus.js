// File: frontend/src/services/browserStatus.js
import apiClient from './api.js';

const states = new Set(['READY', 'DEGRADED', 'BLOCKED', 'STARTING', 'CLOSED']);
const cleanupStates = new Set(['CLEAR', 'PENDING', 'UNRESOLVED']);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const browserUnavailable = 'Dịch vụ trình duyệt chưa sẵn sàng. Vui lòng liên hệ hỗ trợ.';
const count = value => Number.isSafeInteger(value) && value >= 0 ? value : 0;

export function browserStatusView(data) {
  const view = {
    state: states.has(data?.state) ? data.state : 'BLOCKED',
    can_start: data?.can_start === true && ['READY', 'DEGRADED'].includes(data?.state),
    charged: count(data?.charged), limit: count(data?.limit),
    pending: count(data?.pending), unknown: count(data?.unknown),
    startup_classified: data?.startup_classified === true, task: null,
  };
  if (!view.startup_classified) view.can_start = false;
  const task = data?.task;
  if (uuid.test(task?.task_id || '') && cleanupStates.has(task?.cleanup_state)) {
    view.task = {
      task_id: task.task_id, cleanup_state: task.cleanup_state,
      can_retry: task.can_retry === true && task.resource_allows_retry === true,
      resource_allows_retry: task.resource_allows_retry === true,
      operation_refs: Array.isArray(task.operation_refs)
        ? task.operation_refs.filter(id => typeof id === 'string' && uuid.test(id)).slice(0, 10) : [],
    };
  }
  return view;
}

export function createBrowserStatusApi(client) {
  return {
    async status(taskId = null) {
      if (taskId !== null && !uuid.test(taskId)) throw new Error(browserUnavailable);
      try {
        const response = await client.get('/browser/status', {params: taskId ? {task_id: taskId} : {}});
        return browserStatusView(response.data);
      } catch { throw new Error(browserUnavailable); }
    },
    async retryCleanup(operationId) {
      if (!uuid.test(operationId || '')) throw new Error(browserUnavailable);
      try {
        const {data} = await client.post(`/browser/cleanup/${encodeURIComponent(operationId)}/retry`, {});
        const state = ['CLOSED', 'PENDING', 'UNRESOLVED'].includes(data?.state) ? data.state : 'UNRESOLVED';
        return {operation_id: operationId, state};
      } catch { throw new Error(browserUnavailable); }
    },
  };
}

export const browserApi = createBrowserStatusApi(apiClient);
