const inFlight = ['RUNNING', 'WAITING_EMAIL_SLOT', 'WAITING_EMAIL_CODE', 'VERIFYING_EMAIL', 'SUBMITTING', 'NEEDS_REVIEW'];
const hasEvidence = task => ['submitted_at', 'receipt_text', 'meta_case_number', 'screenshot_path']
  .some(key => task[key] != null);

export function retryFailedCount(job) {
  if (!job || ['RUNNING', 'CANCELLED'].includes(job.status) || !Array.isArray(job.tasks)) return 0;
  if (job.tasks.some(task => inFlight.includes(task.status) || task.status === 'FAILED' && hasEvidence(task))) return 0;
  return job.tasks.filter(task => task.status === 'FAILED' && !hasEvidence(task)
    && Number.isInteger(task.retry_count) && Number.isInteger(task.max_retries)
    && task.retry_count < task.max_retries).length;
}

export function startBlockReason(job) {
  if (!job || job.status === 'RUNNING') return '';
  if (job.tasks?.some(task => ['SUBMITTING', 'NEEDS_REVIEW'].includes(task.status))) {
    return 'Reconcile uncertain submissions before starting this job.';
  }
  if (job.tasks?.some(task => ['PENDING', 'QUEUED'].includes(task.status))) return '';
  return retryFailedCount(job) ? 'No pending tasks. Use Retry failed tasks, then Start Execution when ready.'
    : 'No pending tasks. Failed tasks with submission evidence or an exhausted retry limit cannot be retried.';
}
