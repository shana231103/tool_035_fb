<!-- File: frontend/src/views/JobsView.vue -->
<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between pb-4 border-b border-slate-800">
      <div>
        <h2 class="text-2xl font-bold text-white">Batch Jobs History</h2>
        <p class="text-sm text-slate-400 mt-1">Review past submissions, success metrics, and case archives.</p>
      </div>
      <button
        @click="jobStore.fetchHistory(0)"
        :disabled="jobStore.historyLoading"
        class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition"
      >
        Refresh List
      </button>
    </div>

    <p v-if="jobStore.historyError || jobStore.detailError" role="alert" class="text-rose-300">{{ jobStore.historyError || jobStore.detailError }}</p>
    <p v-if="jobStore.historyLoading" role="status" class="text-slate-400">Refreshing history…</p>
    <div class="flex items-center gap-4 text-sm text-slate-300">
      <button :disabled="jobStore.historyLoading || jobStore.historyOffset === 0"
        @click="jobStore.fetchHistory(jobStore.historyOffset - jobStore.pageSize)"
        class="rounded-lg bg-slate-800 px-4 py-2 disabled:opacity-40">Previous</button>
      <span>Page {{ Math.floor(jobStore.historyOffset / jobStore.pageSize) + 1 }}</span>
      <button :disabled="jobStore.historyLoading || !jobStore.historyHasMore"
        @click="jobStore.fetchHistory(jobStore.historyOffset + jobStore.pageSize)"
        class="rounded-lg bg-slate-800 px-4 py-2 disabled:opacity-40">Next</button>
    </div>
    <!-- History List -->
    <div class="bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
      <table class="w-full text-left text-xs">
        <thead class="bg-slate-950/70 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
          <tr>
            <th class="py-3.5 px-4">Campaign Name</th>
            <th class="py-3.5 px-4">Created Date</th>
            <th class="py-3.5 px-4">Proxy Country</th>
            <th class="py-3.5 px-4">Status</th>
            <th class="py-3.5 px-4 text-center">Progress (Submitted/Total)</th>
            <th class="py-3.5 px-4 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/60 font-mono">
          <tr v-if="jobStore.historyJobs.length === 0 && !jobStore.historyLoading">
            <td colspan="6" class="py-8 text-center text-slate-500 font-sans">
              No batch jobs found.
            </td>
          </tr>
          <tr
            v-for="job in jobStore.historyJobs"
            :key="job.id"
            class="hover:bg-slate-800/30 transition"
          >
            <td class="py-4 px-4 font-sans font-bold text-slate-100">
              {{ job.name }}
            </td>
            <td class="py-4 px-4 text-slate-400 font-sans">
              {{ new Date(job.created_at).toLocaleString() }}
            </td>
            <td class="py-4 px-4 font-sans text-slate-300">
              {{ job.preferred_country || "Auto" }}
            </td>
            <td class="py-4 px-4 font-sans">
              <span class="px-2.5 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-800 text-slate-300">
                {{ job.status }}
              </span>
            </td>
            <td class="py-4 px-4 text-center font-bold">
              <span class="text-emerald-400">{{ job.stats?.submitted || 0 }}</span>
              <span class="text-slate-500"> / </span>
              <span class="text-slate-300">{{ job.stats?.total || 0 }}</span>
            </td>
            <td class="py-4 px-4 text-right font-sans">
              <button
                @click="inspectJob(job.id)"
                class="px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-400 text-xs font-semibold transition"
              >
                Inspect Tasks
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue';
import { useRouter } from "vue-router";
import { useJobStore } from "../stores/jobStore";

const router = useRouter();
const jobStore = useJobStore();
onMounted(() => {
  jobStore.initWebSocketListener();
  return jobStore.fetchHistory();
});

const inspectJob = async (jobId) => {
  if (await jobStore.selectJob(jobId)) router.push("/");
};
</script>
