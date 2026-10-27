// File: frontend/src/stores/bulkImportStore.js
import { defineStore } from 'pinia';
const publicRow = row => ({source_line:row.source_line, masked_email:row.masked_email || '***', status:row.status, reason:row.reason || null});
export const createBulkImportStoreOptions = () => ({
  state: () => ({revision:0, phase:'EMPTY', importId:null, jobId:null, rows:[], errors:[], preview:null,
    review:null, busy:false, error:'', exclusionsAccepted:false, duplicatesAccepted:false, outcomeUnknown:false}),
  actions: {
    invalidate() { this.revision++; this.preview = null; this.review = null; this.exclusionsAccepted = false; this.duplicatesAccepted = false; },
    setRows(rows) { this.rows = rows.map(publicRow); this.invalidate(); },
    setErrors(errors) { this.errors = errors.map(row => ({source_line:row.source_line, reason:row.reason})); this.invalidate(); },
    acceptPreview(result, revision) {
      if (revision !== this.revision) return false;
      this.preview = {profile_sha256:result.profile_sha256, preview_sha256:result.preview_sha256,
        duplicate_ack_sha256:result.duplicate_ack_sha256 || null, can_create:result.can_create === true,
        masked_assignments:(result.masked_assignments || []).map(row => ({sequence:row.sequence, source_line:row.source_line, masked_email:row.masked_email})),
        content_matches:(result.content_matches || []).map(row => ({job_id:row.job_id, status:row.status, submitted_count:row.submitted_count, has_uncertain:row.has_uncertain}))};
      this.errors = (result.errors || []).map(row => ({source_line:row.source_line, reason:row.reason}));
      this.phase = 'PREVIEW'; return true;
    },
    beginImport(id) { this.importId = id; this.outcomeUnknown = false; },
    created(result) { this.jobId = result.job_id; this.importId = result.import_id; this.phase = 'DRAFT'; this.outcomeUnknown = false; this.review = null; },
    acceptReview(result) {
      this.review = {job_id:result.job_id, can_start:result.can_start === true, review_sha256:result.review_sha256,
        bulk_revision:result.bulk_revision, profile_sha256:result.profile_sha256,
        waiting_counts:{MAIL_UNAVAILABLE:result.waiting_counts?.MAIL_UNAVAILABLE || 0}, blocked_reasons:[...(result.blocked_reasons || [])]};
    },
    reset() { this.$reset(); },
  },
});
export const useBulkImportStore = defineStore('bulkImport', createBulkImportStoreOptions());
