<!-- File: frontend/src/views/DashboardView.vue -->
<template>
  <div class="space-y-8">
    <p v-if="taskStore.error" role="alert" class="text-xs text-rose-300">{{ taskStore.error }}</p>
    <!-- Top KPI Metrics -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-xl relative overflow-hidden group hover:border-indigo-500/50 transition shadow-lg">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Tổng URLs Vi Phạm</span>
          <span class="p-2 rounded-xl bg-indigo-500/10 text-indigo-400">📊</span>
        </div>
        <div class="text-3xl font-black text-white mt-3">{{ taskStore.totalInfringementsCount }}</div>
        <p class="text-xs text-slate-500 mt-1">Ghi nhận qua các tác vụ</p>
      </div>

      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-xl relative overflow-hidden group hover:border-emerald-500/50 transition shadow-lg">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Báo Cáo Thành Công</span>
          <span class="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">🛡️</span>
        </div>
        <div class="text-3xl font-black text-emerald-400 mt-3">{{ taskStore.totalSubmittedCount }}</div>
        <p class="text-xs text-slate-500 mt-1">Đã xác nhận Meta Case ID</p>
      </div>

      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-xl relative overflow-hidden group hover:border-sky-500/50 transition shadow-lg">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Trạng Thái Slot</span>
          <span class="p-2 rounded-xl bg-sky-500/10 text-sky-400">⚡</span>
        </div>
        <div class="text-2xl font-black text-sky-400 mt-3 flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full" :class="taskStore.isSlotReady ? 'bg-emerald-400' : 'bg-amber-400'"></span>
          <span>{{ taskStore.executionAvailability.reason || 'CHƯA KIỂM TRA' }}</span>
        </div>
        <p class="text-xs text-slate-500 mt-1">{{ taskStore.availabilityText }}</p>
      </div>

      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-xl relative overflow-hidden group hover:border-amber-500/50 transition shadow-lg">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Proxies Hoạt Động</span>
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
        <BrowserReadinessPanel />
        <ReportTaskForm />
        <LogStreamViewer />
      </div>

      <!-- Right Column: Task Selector & Task Detail Panel (7 cols) -->
      <div class="lg:col-span-7 space-y-6">
        <!-- Task Picker Bar -->
        <div class="flex items-center justify-between bg-slate-900/60 border border-slate-800 p-3 rounded-2xl backdrop-blur-xl">
          <span class="text-xs font-bold uppercase tracking-wider text-slate-400 ml-2">Tác Vụ Gần Đây</span>
          <div class="flex items-center gap-2 overflow-x-auto max-w-md">
            <button
              v-for="t in taskStore.tasks.slice(0, 5)"
              :key="t.id"
              @click="taskStore.selectTask(t.id)"
              :class="taskStore.activeTaskId === t.id ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'"
              class="px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition"
            >
              {{ t.name }}
            </button>
          </div>
        </div>

        <!-- Task Detail Panel -->
        <TaskDetailPanel />
      </div>
    </div>
  </div>
</template>

<script setup>
import { watch } from "vue";
import ReportTaskForm from "../components/ReportTaskForm.vue";
import TaskDetailPanel from "../components/TaskDetailPanel.vue";
import LogStreamViewer from "../components/LogStreamViewer.vue";
import BrowserReadinessPanel from "../components/BrowserReadinessPanel.vue";
import { useTaskStore } from "../stores/taskStore";
import { useProxyStore } from "../stores/proxyStore";
import { useAuthStore } from "../stores/authStore.js";

const taskStore = useTaskStore();
const proxyStore = useProxyStore();
const authStore = useAuthStore();

watch(() => authStore.sessionContext, async session => {
  if (!session || !authStore.isAuthenticated) return;
  taskStore.initWebSocketListener();
  await Promise.all([
    taskStore.fetchTasks(),
    taskStore.checkExecutionStatus(),
    proxyStore.fetchProxies(),
    proxyStore.fetchProfiles(),
  ]);
}, {immediate: true});
</script>
