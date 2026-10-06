// File: frontend/src/stores/jobStore.js
import { defineStore } from 'pinia';
import { jobsApi } from '../services/api.js';
import { wsService } from '../services/websocket.js';
import { taskStats, safeTaskProgress, preserveReceipts } from '../utils/jobProgress.js';
export { taskStats, safeTaskProgress } from '../utils/jobProgress.js';

const errorText = error => error.response?.data?.detail || error.message;
const mailboxStartErrors = {
  MAPPING_INVALID: 'Mailbox mapping is missing or does not match this job’s profile email. Open Microsoft mailbox, wait for CONNECTED, then Confirm mapping and Save mapping using the profile contact email before starting.',
  AUTH_REQUIRED: 'Connect and finish Microsoft sign-in before starting. Wait for CONNECTED, then confirm the mailbox mapping for this job’s profile email.',
  DISCONNECTED: 'The Microsoft mailbox was disconnected. Reconnect and save its email mapping before starting.',
  EVIDENCE_REQUIRED: 'The mailbox email template is unsupported. Re-save mapping with the provided Meta report email type.',
};
const channels = ['latest', 'history', 'detail'];

export function createJobStoreOptions(api = jobsApi, socket = wsService) {
  return {
    state: () => ({
      jobs: [], historyJobs: [], historyOffset: 0, pageSize: 50, historyHasMore: false,
      historyVisited: false, historyLoading: false, historyError: null,
      selectedJobId: null, selectedJob: null, detailLoading: false, detailError: null,
      isLoading: false, error: null, logs: [], listenerInitialized: false,
      retryingJobId: null,
      generations: {latest: 0, history: 0, detail: 0},
      revisions: {latest: 0, history: 0, detail: 0},
    }),
    getters: {
      activeJobsCount: state => state.jobs.filter(job => job.status === 'RUNNING').length,
      completedJobsCount: state => state.jobs.filter(job => job.status === 'COMPLETED').length,
      totalInfringementsCount: state => state.jobs.reduce((n, job) => n + (job.stats?.total || 0), 0),
      totalSubmittedCount: state => state.jobs.reduce((n, job) => n + (job.stats?.submitted || 0), 0),
    },
    actions: {
      async _snapshot(channel, load, apply, current = () => true) {
        const generation = ++this.generations[channel];
        const loading = {latest: 'isLoading', history: 'historyLoading', detail: 'detailLoading'}[channel];
        const error = {latest: 'error', history: 'historyError', detail: 'detailError'}[channel];
        this[loading] = true;
        this[error] = null;
        try {
          while (generation === this.generations[channel] && current()) {
            const revision = this.revisions[channel];
            const snapshot = await load();
            if (generation !== this.generations[channel] || !current()) return false;
            if (revision !== this.revisions[channel]) continue;
            apply(snapshot);
            return true;
          }
          return false;
        } catch (failure) {
          if (generation === this.generations[channel] && current()) this[error] = errorText(failure);
          return false;
        } finally {
          if (generation === this.generations[channel]) this[loading] = false;
        }
      },
      fetchJobs() {
        return this._snapshot('latest', () => api.listJobs(), items => {
          this.jobs = items.map(job => preserveReceipts(job, this.jobs.find(old => old.id === job.id)));
        });
      },
      fetchHistory(offset = this.historyOffset) {
        if (!Number.isInteger(offset) || offset < 0) return Promise.resolve(false);
        this.historyVisited = true;
        if (offset !== this.historyOffset) this.historyJobs = [];
        this.historyOffset = offset;
        return this._snapshot('history', () => api.listJobsPage(this.pageSize, offset), page => {
          this.historyJobs = page.items.map(job => preserveReceipts(job,
            this.historyJobs.find(old => old.id === job.id)));
          this.historyHasMore = page.has_more;
        }, () => this.historyOffset === offset);
      },
      selectJob(jobId) {
        if (this.selectedJobId !== jobId) this.selectedJob = null;
        this.selectedJobId = jobId;
        return this.refreshSelectedJob(jobId);
      },
      refreshSelectedJob(jobId = this.selectedJobId) {
        if (!jobId || jobId !== this.selectedJobId) return Promise.resolve(false);
        return this._snapshot('detail', () => api.getJob(jobId), job => {
          this.selectedJob = preserveReceipts(job, this.selectedJob);
        }, () => this.selectedJobId === jobId);
      },
      resyncVisibleState() {
        const work = [this.fetchJobs()];
        if (this.historyVisited) work.push(this.fetchHistory(this.historyOffset));
        if (this.selectedJobId) work.push(this.refreshSelectedJob(this.selectedJobId));
        return Promise.all(work);
      },
      async createJob(formData) {
        this.isLoading = true;
        this.error = null;
        try {
          const job = await api.createJob(formData);
          ++this.generations.latest;
          ++this.generations.detail;
          this.jobs = [job, ...this.jobs.filter(old => old.id !== job.id)].slice(0, 50);
          this.selectedJobId = job.id;
          this.selectedJob = job;
          this.detailLoading = false;
          this.addLog(`Created Batch Job "${job.name}" with ${job.tasks.length} tasks.`);
          if (this.historyVisited) await this.fetchHistory(0);
          return job;
        } catch (failure) {
          this.error = errorText(failure);
          throw failure;
        } finally { this.isLoading = false; }
      },
      async startJob(jobId) {
        if (this.retryingJobId === jobId) return;
        this.error = null;
        try {
          await api.startJob(jobId);
          this.addLog(`Triggered START for Job ID: ${jobId}`);
          await this.resyncVisibleState();
        } catch (failure) { this.error = mailboxStartErrors[failure.response?.data?.detail] || errorText(failure); }
      },
      async stopJob(jobId) {
        this.error = null;
        try {
          await api.stopJob(jobId);
          this.addLog(`Triggered STOP for Job ID: ${jobId}`);
          await this.resyncVisibleState();
        } catch (failure) { this.error = errorText(failure); }
      },
      async retryFailedTasks(jobId) {
        if (this.retryingJobId) return false;
        this.retryingJobId = jobId;
        this.error = null;
        try {
          const result = await api.retryFailedTasks(jobId);
          this.addLog(`Requeued ${result.retried_count} failed tasks. Start Execution when ready.`);
          await this.resyncVisibleState();
          return true;
        } catch (failure) {
          this.error = errorText(failure);
          await this.resyncVisibleState();
          this.error = errorText(failure);
          return false;
        } finally { this.retryingJobId = null; }
      },
      addLog(text) {
        this.logs.unshift({id: Date.now() + Math.random(), timestamp: new Date().toLocaleTimeString(), text});
        if (this.logs.length > 200) this.logs.pop();
      },
      receiveEvent(message) {
        if (message.type === 'RECONNECTED') {
          this.resyncVisibleState();
          return;
        }
        if (!['JOB_UPDATE', 'TASK_UPDATE'].includes(message.type) || !message.data) return;
        for (const channel of channels) {
          if (channel !== 'detail' || this.selectedJobId === message.job_id) ++this.revisions[channel];
        }
        const jobs = new Set([...this.jobs, ...this.historyJobs, this.selectedJob].filter(Boolean));
        for (const job of jobs) {
          if (job.id !== message.job_id) continue;
          if (message.type === 'JOB_UPDATE') {
            if (message.data.status) job.status = message.data.status;
            if (message.data.stats) job.stats = Object.fromEntries(Object.keys(taskStats([]))
              .filter(key => key in message.data.stats).map(key => [key, message.data.stats[key]]));
            if ('completed_at' in message.data) job.completed_at = message.data.completed_at;
          } else {
            const task = job.tasks?.find(item => item.id === message.task_id);
            if (task && !(task.status === 'SUBMITTED' && task.receipt_text && message.data.status !== 'SUBMITTED')) {
              Object.assign(task, safeTaskProgress(message.data));
            }
            job.stats = taskStats(job.tasks || []);
          }
        }
        this.addLog(`[${message.type === 'JOB_UPDATE' ? 'Job' : 'Task'} ${String(message.task_id || message.job_id).slice(0, 8)}] Status: ${message.data.status}`);
      },
      initWebSocketListener() {
        if (this.listenerInitialized) return;
        this.listenerInitialized = true;
        socket.subscribe(message => this.receiveEvent(message));
        socket.connect();
      },
    },
  };
}

export const useJobStore = defineStore('jobs', createJobStoreOptions());
