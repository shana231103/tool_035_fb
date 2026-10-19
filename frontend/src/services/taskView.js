// File: frontend/src/services/taskView.js
import {getBrowserErrorMessage} from './browserStatus.js';

const statuses = new Set(['DRAFT', 'PREPARING', 'RUNNING', 'WAITING_EMAIL_CODE',
  'VERIFYING_EMAIL', 'SUBMITTING', 'SUBMITTED', 'FAILED', 'CANCELLED', 'NEEDS_REVIEW']);
export const runningStatuses = new Set(['PREPARING', 'RUNNING', 'WAITING_EMAIL_CODE', 'VERIFYING_EMAIL', 'SUBMITTING']);
const outcomes = new Set(['ADMITTED', 'RUNNING', 'DRAINING', 'FINISHED', 'RECOVERY_REQUIRED']);
const legacyOutcomes = new Set(['FREE', 'ADMITTED', 'RUNNING', 'DRAINING', 'RECOVERY_REQUIRED']);
const positive = value => Number.isSafeInteger(value) && value >= 1;
const text = value => typeof value === 'string' && value.trim().length > 0;
const contractError = () => new Error('Dữ liệu tác vụ không hợp lệ. Vui lòng kiểm tra lại.');
export const unknownAvailability = (authEpoch = 0) => ({state: 'unknown', available: false, reason: null, authEpoch});

export function parseTask(raw) {
  const legacy = raw?.is_legacy === true || raw?.legacy_read_only === true;
  if (!raw || !text(raw.id) || !text(raw.name) || !statuses.has(raw.status) || !positive(raw.version) ||
      !Array.isArray(raw.target_urls) || raw.target_urls.length > 30 || raw.target_urls.some(url => !text(url)) ||
      (!legacy && (!raw.target_urls.length || !text(raw.original_url))) ||
      ['is_running', 'is_terminal', 'is_retriable'].some(key => typeof raw[key] !== 'boolean')) throw contractError();
  const fields = ['id', 'operator_id', 'owner_profile_id', 'name', 'original_url', 'explanation',
    'preferred_country', 'status', 'version', 'retry_count', 'max_retries', 'created_at',
    'updated_at', 'submitted_at', 'completed_at', 'receipt_text', 'case_number', 'attempt_id',
    'safe_error_code', 'is_active', 'is_terminal', 'is_retriable', 'is_running', 'is_legacy', 'legacy_read_only'];
  const view = Object.fromEntries(fields.filter(key => key in raw).map(key => [key, raw[key]]));
  return {...view, target_urls: [...raw.target_urls], targetCount: raw.target_urls.length,
    originalUrl: raw.original_url, legacy_read_only: legacy};
}

export function parseTaskPage(raw) {
  if (!Array.isArray(raw?.items) || !positive(raw.limit) || raw.limit > 100 ||
      !Number.isSafeInteger(raw.offset) || raw.offset < 0 || typeof raw.has_more !== 'boolean') throw contractError();
  return {...raw, items: raw.items.map(parseTask)};
}

export function parseAvailability(raw, authEpoch = 0) {
  if (typeof raw?.available !== 'boolean' || !['READY', 'BUSY', 'RECOVERY_REQUIRED', 'UNAVAILABLE'].includes(raw.reason) ||
      raw.available !== (raw.reason === 'READY')) throw contractError();
  return {state: 'ready', available: raw.available, reason: raw.reason, authEpoch};
}

export function parseStartReceipt(raw, intent) {
  if (!raw || raw.task_id !== intent.taskId || raw.command_id !== intent.commandId ||
      !positive(raw.version) || typeof raw.historical !== 'boolean') throw contractError();
  if (raw.authority_contract_version === 1) {
    if (raw.status !== 'LEGACY_READ_ONLY' || !raw.historical || !legacyOutcomes.has(raw.legacy_outcome_phase)) throw contractError();
  } else if (raw.authority_contract_version !== 2 || raw.version !== intent.expectedVersion + 1 || !outcomes.has(raw.status) ||
      raw.legacy_outcome_phase != null || !text(raw.attempt_id)) throw contractError();
  return raw;
}

export function parseControl(raw, commandId) {
  if (raw?.command_id !== commandId || !['ADMITTED', 'COMPLETE', 'RECOVERY_REQUIRED'].includes(raw.status)) throw contractError();
  return {command_id: commandId, status: raw.status, safe_code: raw.safe_code};
}

export function parseTaskEvent(raw) {
  if (raw?.type !== 'TASK_UPDATE' || raw.job_id || !text(raw.task_id) || !positive(raw.version) ||
      !raw.data || !statuses.has(raw.data.status) || (raw.attempt_id != null && !text(raw.attempt_id))) return null;
  return {taskId: raw.task_id, version: raw.version, attemptId: raw.attempt_id ?? null};
}

export function availabilityMessage(view) {
  if (view.state === 'loading') return 'Đang kiểm tra khả năng thực thi…';
  if (view.state === 'unknown') return 'Chưa kiểm tra khả năng thực thi.';
  if (view.state === 'error') return 'Không thể kiểm tra khả năng thực thi. Vui lòng kiểm tra lại.';
  return {READY: 'Sẵn sàng nhận tác vụ mới.', BUSY: 'Hệ thống đang thực thi hoặc dọn dẹp tác vụ.',
    RECOVERY_REQUIRED: 'Cần phục hồi trước khi chạy tác vụ.', UNAVAILABLE: 'Dịch vụ thực thi chưa khả dụng.'}[view.reason];
}

export function startBlockReason(task, availability, browser, pending) {
  if (!task) return 'Hãy chọn một tác vụ.';
  if (task.legacy_read_only) return 'Tác vụ lịch sử chỉ cho phép xem.';
  if (pending && pending.state !== 'RESOLVED') return 'Chưa xác định kết quả lệnh bắt đầu. Hãy kiểm tra kết quả.';
  if (task.status !== 'DRAFT' || !positive(task.version)) return 'Tác vụ chưa ở trạng thái bản nháp hợp lệ.';
  if (task.receipt_text || task.case_number || task.submitted_at) return 'Tác vụ đã có dấu vết gửi; cần kiểm tra thủ công.';
  if (availability.state !== 'ready' || !availability.available) return availabilityMessage(availability);
  if (!browser?.canStart) return browser?.loading ? 'Đang kiểm tra trình duyệt…' : getBrowserErrorMessage(browser?.status?.safe_reason);
  return null;
}

export function safeActionError(error) {
  const code = error?.response?.data?.safe_code || error?.response?.data?.detail?.code;
  const messages = {TASK_VERSION_CONFLICT: 'Tác vụ đã thay đổi. Hãy kiểm tra lại trạng thái.',
    EXECUTION_BUSY: 'Hệ thống đang bận.', COMMAND_REUSE_CONFLICT: 'Lệnh không khớp yêu cầu trước đó.',
    LEGACY_COMMAND_UNVERIFIED: 'Lệnh lịch sử không thể thực thi lại.', SESSION_INVALID: 'Phiên đăng nhập đã hết hạn.'};
  return messages[code] || 'Không thể xác nhận thao tác. Vui lòng kiểm tra lại trạng thái.';
}
