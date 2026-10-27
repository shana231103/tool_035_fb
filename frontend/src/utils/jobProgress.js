// File: frontend/src/utils/jobProgress.js
const activeKeys = ['pending', 'queued', 'running', 'waiting_email_slot',
  'waiting_email_code', 'verifying_email', 'submitting'];

export function pendingOrActive(stats = {}) {
  return activeKeys.reduce((sum, key) => sum + Math.max(0, Number(stats[key]) || 0), 0);
}

export function taskStats(tasks = []) {
  const stats = {total: tasks.length, submitted: 0, failed: 0, cancelled: 0,
    needs_review: 0, ...Object.fromEntries(activeKeys.map(key => [key, 0]))};
  for (const task of tasks) {
    const key = String(task.status || '').toLowerCase();
    if (key !== 'total' && Object.hasOwn(stats, key)) stats[key]++;
  }
  return stats;
}

export function safeTaskProgress(data = {}) {
  const fields = ['status', 'attempt_id', 'retry_count', 'error_message', 'receipt_text',
    'meta_case_number', 'screenshot_path', 'started_at', 'completed_at', 'submitted_at',
    'error_stage', 'verification_state', 'retryable'];
  const projected = Object.fromEntries(fields.filter(key => key in data).map(key => [key, data[key]]));
  if ('verification' in data) {
    const value = data.verification;
    const allowed = ['challenge_id', 'masked_email', 'requested_at', 'expires_at', 'attempts',
      'resends', 'last_error', 'resend_supported', 'mode', 'phase', 'attempt_id'];
    projected.verification = value && typeof value === 'object'
      ? Object.fromEntries(allowed.filter(key => key in value).map(key => [key, value[key]])) : null;
  }
  return projected;
}

export function preserveReceipts(snapshot, previous) {
  if (!snapshot || !previous || snapshot.id !== previous.id) return snapshot;
  const tasks = snapshot.tasks?.map(task => {
    const old = previous.tasks?.find(item => item.id === task.id);
    return old?.status === 'SUBMITTED' && old.receipt_text && task.status !== 'SUBMITTED'
      ? {...task, ...safeTaskProgress(old)} : task;
  });
  return tasks ? {...snapshot, tasks, stats: taskStats(tasks)} : snapshot;
}
