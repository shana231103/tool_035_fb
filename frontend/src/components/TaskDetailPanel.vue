<!-- File: frontend/src/components/TaskDetailPanel.vue -->
<template>
  <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl shadow-xl space-y-6">
    <!-- Empty State -->
    <div v-if="!task" class="py-12 text-center text-slate-500">
      <div class="text-4xl mb-3">📋</div>
      <p class="text-sm font-semibold">Chưa có tác vụ nào được chọn</p>
      <p class="text-xs text-slate-600 mt-1">Hãy tạo tác vụ mới hoặc chọn một tác vụ từ danh sách để xem chi tiết.</p>
    </div>

    <!-- Active Task View -->
    <template v-else>
      <!-- Header & Status -->
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
        <div>
          <div class="flex items-center gap-3">
            <h2 class="text-base font-extrabold text-white">{{ task.name }}</h2>
            <span :class="statusBadgeClass" class="px-2.5 py-0.5 rounded-full text-[11px] font-bold border">
              {{ task.status }}
            </span>
          </div>
          <div class="flex items-center gap-3 text-[11px] text-slate-400 mt-1 font-mono">
            <span>ID: {{ task.id.substring(0, 8) }}...</span>
            <span>•</span>
            <span>QG: {{ task.preferred_country || "SG" }}</span>
            <span>•</span>
            <span>Phiên bản: v{{ task.version }}</span>
            <span v-if="task.retry_count > 0" class="text-amber-400">• Retry: {{ task.retry_count }}</span>
          </div>
        </div>

        <!-- Action Controls -->
        <div class="flex items-center gap-2">
          <!-- Start Button (Draft) -->
          <button
            v-if="task.status === 'DRAFT'"
            @click="handleStart"
            :disabled="!taskStore.canStartActiveTask || taskStore.actionLoading"
            class="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition shadow-lg shadow-emerald-600/20 flex items-center gap-1.5"
            :title="taskStore.startDisabledReason || 'Bắt đầu thực thi'"
          >
            <span>▶️</span>
            <span>Bắt Đầu Báo Cáo</span>
          </button>

          <!-- Stop Button (Preparing / Submitting) -->
          <button
            v-if="taskStore.canStopActiveTask"
            @click="handleStop"
            :disabled="taskStore.actionLoading"
            class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white text-xs font-bold transition shadow-lg shadow-rose-600/20 flex items-center gap-1.5"
          >
            <span>⏹️</span>
            <span>Dừng Tác Vụ</span>
          </button>

          <!-- Retry Button (Failed / Stopped) -->
          <button
            v-if="taskStore.canRetryActiveTask"
            @click="handleRetry"
            :disabled="taskStore.actionLoading"
            class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold transition shadow-lg shadow-indigo-600/20 flex items-center gap-1.5"
          >
            <span>🔄</span>
            <span>Thử Lại (Reset DRAFT)</span>
          </button>
        </div>
      </div>

      <div v-if="taskStore.startDisabledReason && task.status === 'DRAFT'" role="status" class="text-xs text-amber-300">
        {{ taskStore.startDisabledReason }}
        <button class="ml-2 text-indigo-300 underline" @click="taskStore.resyncVisibleState()">Kiểm tra lại</button>
      </div>
      <div v-if="taskStore.pendingStart?.state === 'UNKNOWN'" class="space-y-2 text-xs text-amber-300" role="status">
        <p>Chưa xác định kết quả lệnh bắt đầu. Lệnh được giữ trong phiên này.</p>
        <p v-if="taskStore.pendingStart.receipt?.authority_contract_version === 1">Lệnh lịch sử chỉ đọc: {{ taskStore.pendingStart.receipt.legacy_outcome_phase }}</p>
        <button class="mr-3 text-indigo-300 underline" @click="taskStore.checkStartResult()">Kiểm tra kết quả</button>
        <button v-if="taskStore.pendingStart.receipt?.authority_contract_version !== 1" :disabled="taskStore.actionLoading"
          class="text-indigo-300 underline disabled:opacity-40" @click="taskStore.retryPendingStart(taskStore.pendingStart.taskId)">Gửi lại cùng lệnh</button>
      </div>
      <p v-if="taskStore.actionError" role="alert" class="text-xs text-rose-300">{{ taskStore.actionError }}</p>
      <div v-if="taskStore.pendingControl || taskStore.controlMessage" role="status" class="text-xs text-amber-300">
        {{ taskStore.controlWaiting ? 'Đang chờ lệnh dừng và dọn dẹp…' : taskStore.controlMessage }}
        <button v-if="taskStore.pendingControl" :disabled="taskStore.controlWaiting" class="ml-2 text-indigo-300 underline"
          @click="taskStore.checkControlResult()">Kiểm tra kết quả dừng</button>
      </div>

      <!-- Slot Busy Warning Banner -->
      <div v-if="task.status === 'DRAFT' && taskStore.isSlotBusy" class="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-300 text-xs flex items-center gap-2">
        <span class="animate-pulse">⚠️</span>
        <span>Hệ thống đang thực thi một tác vụ khác. Bạn có thể bấm bắt đầu ngay khi tác vụ hiện tại hoàn tất.</span>
      </div>

      <!-- Current Step Progress -->
      <div v-if="isProcessing" class="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3.5">
        <div class="flex items-center justify-between text-xs text-slate-400 mb-1.5">
          <span class="font-semibold text-slate-300">Tiến trình hiện tại:</span>
          <span class="font-mono text-indigo-400">{{ task.status }}</span>
        </div>
        <div class="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
          <div
            class="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full transition-all duration-500"
            :class="isProcessing ? 'animate-pulse w-2/3' : task.status === 'SUBMITTED' ? 'w-full' : 'w-1/3'"
          ></div>
        </div>
      </div>

      <!-- Error Message Banner -->
      <div v-if="task.safe_error_code" class="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs">
        <div class="font-bold flex items-center gap-1.5 mb-1">
          <span>❌</span>
          <span>Lỗi thực thi:</span>
        </div>
        <p class="font-mono text-[11px] break-words">{{ task.safe_error_code }}</p>
      </div>

      <!-- Submission Case ID (if SUBMITTED) -->
      <div v-if="task.case_number" class="p-3.5 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-300 text-xs flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span>🛡️</span>
          <span><strong>Meta Case ID:</strong> <span class="font-mono">{{ task.case_number }}</span></span>
        </div>
        <span class="text-[11px] text-emerald-400">Đã gửi xác nhận</span>
      </div>

      <!-- Target URLs Section -->
      <div v-if="task.receipt_text" class="rounded-xl border border-emerald-500/20 p-3 text-xs text-slate-300 whitespace-pre-wrap break-words">
        {{ task.receipt_text }}
      </div>
      <p v-if="task.completed_at" class="text-xs text-slate-500">Kết thúc: {{ new Date(task.completed_at).toLocaleString() }}</p>

      <!-- Target URLs Section -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400">
            Danh sách mục tiêu vi phạm ({{ targetsList.length }} URLs)
          </h3>
          <span class="text-[11px] text-slate-500">Facebook Links</span>
        </div>

        <div class="bg-slate-950 border border-slate-800/80 rounded-xl divide-y divide-slate-800/60 max-h-60 overflow-y-auto">
          <div
            v-for="(target, idx) in targetsList"
            :key="idx"
            class="p-2.5 flex items-center justify-between text-xs hover:bg-slate-900/40 transition"
          >
            <div class="flex items-center gap-2.5 min-w-0 pr-3">
              <span class="w-5 h-5 rounded-md bg-slate-900 text-slate-500 flex items-center justify-center font-mono text-[10px] shrink-0">
                {{ idx + 1 }}
              </span>
              <span class="text-slate-300 font-mono text-[11px] truncate" :title="target">
                {{ target }}
              </span>
            </div>
            <a
              :href="target"
              target="_blank"
              rel="noopener noreferrer"
              class="text-indigo-400 hover:text-indigo-300 text-[11px] shrink-0 font-medium"
            >
              Mở ↗
            </a>
          </div>
        </div>
      </div>

      <!-- Original Work Link -->
      <div class="pt-2 text-xs text-slate-400 flex items-center justify-between">
        <span>Tác phẩm gốc:</span>
        <a
          :href="task.originalUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="text-indigo-400 hover:underline truncate max-w-sm font-mono text-[11px]"
        >
          {{ task.originalUrl || 'Không có dữ liệu lịch sử' }}
        </a>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useTaskStore } from "../stores/taskStore";

const taskStore = useTaskStore();
const task = computed(() => taskStore.activeTask);

const targetsList = computed(() => {
  if (!task.value) return [];
  return task.value.target_urls;
});

const isProcessing = computed(() => {
  return task.value?.is_running === true;
});

const statusBadgeClass = computed(() => {
  switch (task.value?.status) {
    case "DRAFT":
      return "bg-slate-800 text-slate-300 border-slate-700";
    case "PREPARING":
      return "bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse";
    case "SUBMITTING":
      return "bg-sky-500/10 text-sky-400 border-sky-500/30 animate-pulse";
    case "SUBMITTED":
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
    case "FAILED":
      return "bg-rose-500/10 text-rose-400 border-rose-500/30";
    case "CANCELLED":
      return "bg-slate-700 text-slate-400 border-slate-600";
    case "NEEDS_REVIEW":
      return "bg-orange-500/10 text-orange-400 border-orange-500/30";
    default:
      return "bg-slate-800 text-slate-400 border-slate-700";
  }
});

async function handleStart() {
  if (!task.value) return;
  try {
    await taskStore.startTask(task.value.id, task.value.version);
  } catch (err) {
    console.error("Start task error:", err);
  }
}

async function handleStop() {
  if (!task.value) return;
  if (!confirm("Bạn có chắc chắn muốn dừng tác vụ này?")) return;
  try {
    await taskStore.stopTask(task.value.id);
  } catch (err) {
    console.error("Stop task error:", err);
  }
}

async function handleRetry() {
  if (!task.value) return;
  try {
    await taskStore.retryTask(task.value.id, task.value.version);
  } catch (err) {
    console.error("Retry task error:", err);
  }
}
</script>
