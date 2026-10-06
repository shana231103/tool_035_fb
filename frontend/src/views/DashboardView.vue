<!-- File: frontend/src/views/DashboardView.vue -->
<template>
  <div class="space-y-8">
    <!-- Top KPI Metrics -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-xl relative overflow-hidden group hover:border-indigo-500/50 transition">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Infringements</span>
          <span class="p-2 rounded-xl bg-indigo-500/10 text-indigo-400">📊</span>
        </div>
        <div class="text-3xl font-black text-white mt-3">{{ jobStore.totalInfringementsCount }}</div>
        <p class="text-xs text-slate-500 mt-1">Processed across campaigns</p>
      </div>

      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-xl relative overflow-hidden group hover:border-emerald-500/50 transition">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Submitted Reports</span>
          <span class="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">🛡️</span>
        </div>
        <div class="text-3xl font-black text-emerald-400 mt-3">{{ jobStore.totalSubmittedCount }}</div>
        <p class="text-xs text-slate-500 mt-1">Confirmed with Meta Case ID</p>
      </div>

      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-xl relative overflow-hidden group hover:border-sky-500/50 transition">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Active Queue Jobs</span>
          <span class="p-2 rounded-xl bg-sky-500/10 text-sky-400">⚡</span>
        </div>
        <div class="text-3xl font-black text-sky-400 mt-3">{{ jobStore.activeJobsCount }}</div>
        <p class="text-xs text-slate-500 mt-1">Running worker threads</p>
      </div>

      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-xl relative overflow-hidden group hover:border-amber-500/50 transition">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Active Proxies</span>
          <span class="p-2 rounded-xl bg-amber-500/10 text-amber-400">🌐</span>
        </div>
        <div class="text-3xl font-black text-amber-400 mt-3">{{ proxyStore.activeProxiesCount }}</div>
        <p class="text-xs text-slate-500 mt-1">SG, AU, JP, KR, JO Nodes</p>
      </div>
    </div>

    <!-- Main Workspace Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
      <!-- Left Column: Form & Live Logs (5 cols) -->
      <div class="lg:col-span-5 space-y-6">
        <BatchJobForm />
        <LogStreamViewer />
      </div>

      <!-- Right Column: Job Selector & Live Table (7 cols) -->
      <div class="lg:col-span-7 space-y-6">
        <!-- Job Picker Tabs -->
        <div class="flex items-center justify-between bg-slate-900/60 border border-slate-800 p-3 rounded-2xl">
          <span class="text-xs font-bold uppercase tracking-wider text-slate-400 ml-2">Active Jobs</span>
          <div class="flex items-center gap-2 overflow-x-auto max-w-md">
            <button
              v-for="job in jobStore.jobs.slice(0, 5)"
              :key="job.id"
              @click="jobStore.selectJob(job.id)"
              :class="jobStore.selectedJob?.id === job.id ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'"
              class="px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition"
            >
              {{ job.name }}
            </button>
          </div>
        </div>

        <!-- Progress Table -->
        <JobStatusTable />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from "vue";
import BatchJobForm from "../components/BatchJobForm.vue";
import JobStatusTable from "../components/JobStatusTable.vue";
import LogStreamViewer from "../components/LogStreamViewer.vue";
import { useJobStore } from "../stores/jobStore";
import { useProxyStore } from "../stores/proxyStore";

const jobStore = useJobStore();
const proxyStore = useProxyStore();

onMounted(async () => {
  await Promise.all([
    jobStore.fetchJobs(),
    proxyStore.fetchProxies(),
    proxyStore.fetchProfiles(),
  ]);
  if (jobStore.jobs.length > 0 && !jobStore.selectedJob) {
    await jobStore.selectJob(jobStore.jobs[0].id);
  }
  jobStore.initWebSocketListener();
});
</script>
