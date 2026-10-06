<!-- File: frontend/src/components/JobStatusTable.vue -->
<template>
  <div class="bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden backdrop-blur-xl shadow-2xl">
    <!-- Header with controls -->
    <div class="p-6 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-bold text-white">
            {{ selectedJob ? selectedJob.name : "Select a Job to view progress" }}
          </h3>
          <span
            v-if="selectedJob"
            :class="statusBadgeClass(selectedJob.status)"
            class="px-2.5 py-0.5 text-xs font-semibold rounded-full uppercase"
          >
            {{ selectedJob.status }}
          </span>
        </div>
        <p v-if="selectedJob" class="text-xs text-slate-400 mt-1">
          Job ID: <span class="font-mono">{{ selectedJob.id }}</span>
        </p>
      </div>

      <!-- Action Buttons -->
      <div v-if="selectedJob" class="flex items-center gap-3">
        <button
          v-if="selectedJob.status !== 'RUNNING'"
          @click="jobStore.startJob(selectedJob.id)"
          :disabled="!!ownerBlockReason || !!executionBlockReason || retryLoading"
          class="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-lg shadow-emerald-600/20 transition flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
          </svg>
          Start Execution
        </button>

        <button
          v-if="selectedJob.status === 'RUNNING'"
          @click="jobStore.stopJob(selectedJob.id)"
          class="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold shadow-lg shadow-amber-600/20 transition flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
          Pause Job
        </button>
        <button
          v-if="retryCount > 0"
          @click="jobStore.retryFailedTasks(selectedJob.id)"
          :disabled="retryLoading"
          class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold"
        >{{ retryLoading ? 'Retrying…' : `Retry failed tasks (${retryCount})` }}</button>
      </div>
    </div>

    <p v-if="ownerBlockReason" role="status" class="px-6 py-3 text-xs text-amber-300">{{ ownerBlockReason }}</p>
    <p v-if="executionBlockReason" role="status" class="px-6 py-3 text-xs text-amber-300">{{ executionBlockReason }}</p>
    <p v-if="jobStore.error || jobStore.detailError" role="alert" class="px-6 py-3 text-xs text-rose-300">{{ jobStore.error || jobStore.detailError }}</p>
    <p v-if="jobStore.detailLoading" role="status" class="px-6 py-2 text-xs text-slate-400">Refreshing selected job…</p>
    <p v-if="selectedJob" class="px-6 py-2 text-xs text-slate-400">Execution requires a confirmed OWNER profile and a ready Microsoft mailbox mapping. Open Microsoft mailbox in the header to connect or reauthenticate.</p>

    <!-- Stats Summary Counter -->
    <div v-if="selectedJob" class="grid grid-cols-2 sm:grid-cols-4 gap-px bg-slate-800 border-b border-slate-800 text-center">
      <div class="bg-slate-900/90 p-4">
        <span class="text-xs uppercase tracking-wider text-slate-500 font-semibold">Total URLs</span>
        <div class="text-2xl font-black text-slate-100 mt-1">{{ selectedJob.stats?.total || 0 }}</div>
      </div>
      <div class="bg-slate-900/90 p-4">
        <span class="text-xs uppercase tracking-wider text-emerald-400 font-semibold">Submitted</span>
        <div class="text-2xl font-black text-emerald-400 mt-1">{{ selectedJob.stats?.submitted || 0 }}</div>
      </div>
      <div class="bg-slate-900/90 p-4">
        <span class="text-xs uppercase tracking-wider text-amber-400 font-semibold">Pending / In-flight</span>
        <div class="text-2xl font-black text-amber-400 mt-1">{{ pendingOrActive(selectedJob.stats) }}</div>
        <p class="text-xs text-amber-300 mt-1">Needs review: {{ selectedJob.stats?.needs_review || 0 }}</p>
      </div>
      <div class="bg-slate-900/90 p-4">
        <span class="text-xs uppercase tracking-wider text-rose-400 font-semibold">Failed</span>
        <div class="text-2xl font-black text-rose-400 mt-1">{{ selectedJob.stats?.failed || 0 }}</div>
      </div>
    </div>

    <!-- Tasks Table -->
    <div class="overflow-x-auto">
      <table class="w-full text-left text-xs">
        <thead class="bg-slate-950/70 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
          <tr>
            <th class="py-3 px-4">#</th>
            <th class="py-3 px-4">Platform</th>
            <th class="py-3 px-4">Account / Page</th>
            <th class="py-3 px-4">Infringing URL</th>
            <th class="py-3 px-4">Status</th>
            <th class="py-3 px-4">Case Number</th>
            <th class="py-3 px-4">Retries</th>
            <th class="py-3 px-4 text-right">Proof Screenshot</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/60 font-mono">
          <tr v-if="!selectedJob || selectedJob.tasks.length === 0">
            <td colspan="8" class="py-8 text-center text-slate-500 font-sans">
              No tasks available for this job.
            </td>
          </tr>
          <tr
            v-for="(task, idx) in selectedJob?.tasks || []"
            :key="task.id"
            class="hover:bg-slate-800/30 transition"
          >
            <td class="py-3.5 px-4 text-slate-500">{{ idx + 1 }}</td>
            <td class="py-3.5 px-4">
              <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-sans font-semibold text-[10px]">
                {{ task.target_platform }}
              </span>
            </td>
            <td class="py-3.5 px-4 font-mono text-slate-300">
              <span
                v-if="task.infringing_account"
                class="px-2 py-0.5 rounded bg-indigo-950/70 border border-indigo-800/40 text-indigo-300 font-sans font-medium text-[11px]"
              >
                {{ formatAccountBadge(task.infringing_account) }}
              </span>
              <span
                v-else-if="extractFallbackAccount(task.target_url)"
                class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700/60 text-slate-300 font-sans font-medium text-[11px]"
              >
                {{ extractFallbackAccount(task.target_url) }}
              </span>
              <span v-else class="text-slate-600">—</span>
            </td>
            <td class="py-3.5 px-4 max-w-xs truncate">
              <a :href="task.target_url" target="_blank" class="text-indigo-400 hover:underline">
                {{ task.target_url }}
              </a>
            </td>
            <td class="py-3.5 px-4">
              <span :class="statusBadgeClass(task.status)" class="px-2 py-0.5 rounded text-[10px] font-sans font-bold">
                {{ task.status }}
              </span>
              <button v-if="['WAITING_EMAIL_SLOT','WAITING_EMAIL_CODE','VERIFYING_EMAIL'].includes(task.status)" @click="verificationTaskId = task.id" class="block mt-2 text-xs text-indigo-300">Automatic verification progress</button>
              <p v-if="task.error_message" class="text-xs text-amber-300 max-w-xs mt-1">{{ task.error_message }}</p>
              <p v-if="task.receipt_text" class="text-xs text-emerald-300 mt-1">{{ task.receipt_text }}</p>
            </td>
            <td class="py-3.5 px-4 text-emerald-400 font-bold">
              {{ task.meta_case_number || "—" }}
            </td>
            <td class="py-3.5 px-4 text-slate-400">
              {{ task.retry_count }}
            </td>
            <td class="py-3.5 px-4 text-right font-sans">
              <button
                v-if="task.screenshot_path"
                @click="viewScreenshot(task.screenshot_path)"
                class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition"
              >
                View Proof
              </button>
              <span v-else class="text-slate-600 text-xs">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Post-submission Lifecycle Notice (ISSUE-07) -->
    <div
      v-if="selectedJob && selectedJob.tasks?.some(t => t.status === 'SUBMITTED')"
      class="p-3 bg-indigo-950/30 border-t border-slate-800/80 px-6 flex items-center justify-between text-[11px] text-slate-400"
    >
      <span class="flex items-center gap-1.5 text-indigo-300 font-medium">
        <span>📬</span> Next steps: Monitor registered owner email for confirmation, optional Case Number, and final decision. Submitted does not mean removed.
      </span>
      <span class="text-slate-500 font-mono">Meta SOP Step 12</span>
    </div>

    <EmailVerificationModal :task="verificationTask" @close="verificationTaskId = null" />

    <!-- Screenshot Modal -->
    <div
      v-if="activeScreenshotUrl"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
      @click="activeScreenshotUrl = null"
    >
      <div class="max-w-4xl w-full bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden p-4 shadow-2xl" @click.stop>
        <div class="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
          <h4 class="font-bold text-white text-sm">Submission Confirmation Screenshot</h4>
          <button @click="activeScreenshotUrl = null" class="text-slate-400 hover:text-white">✕</button>
        </div>
        <img :src="activeScreenshotUrl" alt="Meta report screenshot" class="w-full max-h-[75vh] object-contain rounded-lg" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import EmailVerificationModal from "./EmailVerificationModal.vue";
import { useJobStore } from "../stores/jobStore";
import { useProxyStore } from "../stores/proxyStore";
import { extractAccountHandle } from "../utils/urlValidator";
import { pendingOrActive } from '../utils/jobProgress.js';
import { retryFailedCount, startBlockReason } from '../utils/jobRetry.js';

const jobStore = useJobStore();
const proxyStore = useProxyStore();
const selectedJob = computed(() => jobStore.selectedJob);
const retryCount = computed(() => retryFailedCount(selectedJob.value));
const retryLoading = computed(() => jobStore.retryingJobId === selectedJob.value?.id);
const executionBlockReason = computed(() => startBlockReason(selectedJob.value));
const ownerBlockReason = computed(() => {
  if (!selectedJob.value) return '';
  const profile = proxyStore.profiles.find(item=>item.id === selectedJob.value.owner_profile_id);
  if (!profile) return 'Load or restore the owner profile before execution.';
  return profile.submission_eligible === true && profile.owner_role === 'OWNER' ? '' :
    profile.submission_block_reason || 'This historical profile requires explicit OWNER confirmation and completion.';
});
const activeScreenshotUrl = ref(null);
const verificationTaskId = ref(null);
const verificationTask = computed(() => selectedJob.value?.tasks.find(task => task.id === verificationTaskId.value) || null);

const viewScreenshot = (path) => {
  activeScreenshotUrl.value = path.startsWith("http") ? path : `/static/screenshots/${path}`;
};

const formatAccountBadge = (account) => {
  if (!account) return "";
  return account.startsWith("@") || account.startsWith("id=") ? account : `@${account}`;
};

const extractFallbackAccount = (url) => {
  return extractAccountHandle(url);
};

const statusBadgeClass = (status) => {
  switch (status) {
    case "SUBMITTED":
    case "COMPLETED":
      return "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
    case "RUNNING":
      return "bg-sky-500/10 text-sky-400 border border-sky-500/20 animate-pulse";
    case "QUEUED":
      return "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
    case "FAILED":
      return "bg-rose-500/10 text-rose-400 border border-rose-500/20";
    case "WAITING_EMAIL_SLOT":
    case "WAITING_EMAIL_CODE":
    case "VERIFYING_EMAIL":
    case "SUBMITTING":
    case "NEEDS_REVIEW":
    case "PAUSED":
      return "bg-amber-500/10 text-amber-400 border border-amber-500/20";
    default:
      return "bg-slate-800 text-slate-400";
  }
};
</script>
