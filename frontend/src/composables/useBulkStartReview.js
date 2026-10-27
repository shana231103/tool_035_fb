// File: frontend/src/composables/useBulkStartReview.js
import {computed, onScopeDispose, readonly, ref, watch} from 'vue';
import {startBlockReason} from '../utils/jobRetry.js';

const hash = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const text = value => typeof value === 'string' && value.trim().length > 0;
const reasons = new Set(['PROFILE_REVIEW_REQUIRED', 'IMPORT_METADATA_INVALID', 'MAIL_UNAVAILABLE', 'NO_PENDING_TASKS']);

/** Validate identity and clone only public review fields; server remains hash authority. */
export function projectReview(value, job) {
  const snapshot = value?.profile_snapshot;
  if (!job?.import_id || value?.job_id !== job.id || value.bulk_revision !== job.bulk_revision
      || !Number.isSafeInteger(value.bulk_revision) || value.bulk_revision < 1 || value.status !== job.status
      || snapshot?.profile_id !== job.owner_profile_id || snapshot.owner_role !== 'OWNER'
      || !['owner_name', 'sender_name', 'rights_jurisdiction'].every(key => text(snapshot[key]))
      || !['profile_sha256', 'pending_tasks_digest', 'mail_readiness_digest', 'review_sha256'].every(key => hash(value[key]))
      || typeof value.can_start !== 'boolean' || !Array.isArray(value.blocked_reasons)
      || !value.blocked_reasons.every(reason => reasons.has(reason))
      || !Number.isSafeInteger(value.waiting_counts?.MAIL_UNAVAILABLE) || value.waiting_counts.MAIL_UNAVAILABLE < 0
      || (value.can_start && value.blocked_reasons.length)) return null;
  return Object.freeze({job_id:value.job_id, bulk_revision:value.bulk_revision, status:value.status,
    profile_sha256:value.profile_sha256, pending_tasks_digest:value.pending_tasks_digest,
    mail_readiness_digest:value.mail_readiness_digest, review_sha256:value.review_sha256,
    can_start:value.can_start, blocked_reasons:Object.freeze([...value.blocked_reasons]),
    waiting_counts:Object.freeze({MAIL_UNAVAILABLE:value.waiting_counts.MAIL_UNAVAILABLE}),
    profile_snapshot:Object.freeze({profile_id:snapshot.profile_id, owner_name:snapshot.owner_name,
      sender_name:snapshot.sender_name, rights_jurisdiction:snapshot.rights_jurisdiction, owner_role:snapshot.owner_role})});
}

/**
 * Own one component's review lifecycle and explicit Start confirmation.
 * @param {{job: import('vue').Ref, mailboxConnections: import('vue').Ref,
 * observedProfile: import('vue').Ref, api: {review: Function, start: Function},
 * onStarted: Function, startBlocked?: import('vue').Ref<boolean>}} options
 */
export function useBulkStartReview({job, mailboxConnections, observedProfile, api, onStarted, startBlocked}) {
  const review = ref(null), acceptedDigest = ref(null), activeRequest = ref(null), error = ref('');
  let epoch = 0, disposed = false;
  const busy = computed(() => activeRequest.value !== null);
  const snapshot = computed(() => review.value?.profile_snapshot || null);
  const accepted = computed(() => !!review.value && acceptedDigest.value === review.value.review_sha256);
  const runnable = () => !!job.value?.import_id && ['PENDING', 'PAUSED'].includes(job.value.status)
    && !startBlockReason(job.value) && !startBlocked?.value;
  const canStart = computed(() => !disposed && runnable() && review.value?.can_start === true
    && accepted.value && !busy.value && projectReview(review.value, job.value) !== null);
  const clearReview = () => {review.value = null; acceptedDigest.value = null;};
  const invalidate = () => {epoch++; activeRequest.value = null; clearReview(); error.value = '';};
  const owns = token => !disposed && activeRequest.value === token && epoch === token.epoch && job.value?.id === token.jobId;
  const begin = operation => {
    if (disposed || busy.value) return null;
    const token = Object.freeze({epoch, jobId:job.value?.id, operation});
    activeRequest.value = token;
    return token;
  };
  watch([() => job.value?.id, () => job.value?.status, () => job.value?.bulk_revision,
    () => job.value?.owner_profile_id, mailboxConnections, observedProfile], invalidate, {deep:true, flush:'sync'});
  const dispose = () => {invalidate(); disposed = true;};
  onScopeDispose(dispose);

  async function requestReview() {
    if (!runnable()) return;
    const token = begin('review');
    if (!token) return;
    clearReview(); error.value = '';
    const requestedJob = {...job.value};
    try {
      const result = await api.review(token.jobId);
      if (!owns(token)) return;
      const projected = projectReview(result, requestedJob);
      if (!projected || !projectReview(projected, job.value)) {
        error.value = 'Hồ sơ kiểm tra không hợp lệ. Tải lại và kiểm tra trước khi Chạy.';
        return;
      }
      review.value = projected;
    } catch {
      if (owns(token)) error.value = 'Không kiểm tra được. Kết nối lại mail và tải lại hồ sơ trước khi thử lại.';
    } finally {
      if (owns(token)) activeRequest.value = null;
    }
  }

  function setAccepted(checked) {
    acceptedDigest.value = checked === true && !busy.value && runnable() && review.value?.can_start === true
      && projectReview(review.value, job.value) ? review.value.review_sha256 : null;
  }

  async function start() {
    if (!canStart.value) return;
    const digest = acceptedDigest.value, token = begin('start');
    clearReview(); error.value = '';
    let failed = false;
    try {
      await api.start(token.jobId, digest);
    } catch {
      failed = true;
      if (owns(token)) error.value = 'Không bắt đầu được hoặc kiểm tra đã cũ. Kiểm tra lại trước khi Chạy.';
    } finally {
      // A lost response can still mean server acceptance. Always resync; never resend.
      if (!disposed) {
        try {await onStarted();}
        catch {if (owns(token)) error.value = 'Chưa tải lại được trạng thái. Tải lại trước khi kiểm tra và Chạy.';}
      }
      if (owns(token)) {
        if (failed && !error.value) error.value = 'Kiểm tra lại trước khi Chạy.';
        activeRequest.value = null;
      }
    }
  }
  return {review:readonly(review), snapshot, accepted, busy, error:readonly(error), canStart,
    requestReview, setAccepted, start, invalidate};
}
