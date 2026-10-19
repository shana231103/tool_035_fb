<!-- File: frontend/src/views/TaskHistoryView.vue -->
<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-extrabold text-white tracking-tight">Lịch Sử Tác Vụ Báo Cáo</h1>
        <p class="text-xs text-slate-400 mt-1">Danh sách toàn bộ các tác vụ báo cáo bản quyền đơn lẻ</p>
      </div>

      <!-- Filters & Refresh -->
      <div class="flex items-center gap-3">
        <select
          v-model="statusFilter"
          @change="handleFilterChange"
          class="bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500 transition"
        >
          <option value="">Tất cả trạng thái</option>
          <option value="DRAFT">DRAFT (Bản nháp)</option>
          <option value="PREPARING">PREPARING (Đang chuẩn bị)</option>
          <option value="SUBMITTING">SUBMITTING (Đang gửi)</option>
          <option value="SUBMITTED">SUBMITTED (Đã hoàn tất)</option>
          <option value="FAILED">FAILED (Thất bại)</option>
          <option value="RUNNING">RUNNING (Đang chạy)</option>
          <option value="WAITING_EMAIL_CODE">WAITING_EMAIL_CODE (Chờ mã)</option>
          <option value="VERIFYING_EMAIL">VERIFYING_EMAIL (Xác minh)</option>
          <option value="CANCELLED">CANCELLED (Đã dừng)</option>
          <option value="NEEDS_REVIEW">NEEDS_REVIEW (Cần kiểm tra)</option>
        </select>

        <button
          @click="refreshList"
          :disabled="taskStore.historyLoading"
          class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition flex items-center gap-1.5"
        >
          <span>🔄</span>
          <span>Làm mới</span>
        </button>
      </div>
    </div>

    <!-- Tasks History Table -->
    <div class="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden backdrop-blur-xl shadow-xl">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-950/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
            <tr>
              <th class="py-3 px-4">Tên Tác Vụ</th>
              <th class="py-3 px-4">Trạng Thái</th>
              <th class="py-3 px-4">Số URLs</th>
              <th class="py-3 px-4">Quốc Gia</th>
              <th class="py-3 px-4">Ngày Tạo</th>
              <th class="py-3 px-4 text-right">Thao Tác</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800/60">
            <tr
              v-for="item in filteredTasks"
              :key="item.id"
              class="hover:bg-slate-800/30 transition cursor-pointer"
              :class="taskStore.activeTaskId === item.id ? 'bg-indigo-950/20' : ''"
              @click="handleSelect(item.id)"
            >
              <td class="py-3 px-4 font-semibold text-white">
                <div class="truncate max-w-xs">{{ item.name }}</div>
                <div class="text-[10px] font-mono text-slate-500">{{ item.id.substring(0, 8) }}...</div>
              </td>
              <td class="py-3 px-4">
                <span
                  :class="getStatusBadgeClass(item.status)"
                  class="px-2 py-0.5 rounded-full text-[10px] font-bold border"
                >
                  {{ item.status }}
                </span>
              </td>
              <td class="py-3 px-4 font-mono text-slate-300">
                {{ item.targetCount }}
              </td>
              <td class="py-3 px-4 font-mono text-slate-400">
                {{ item.preferred_country || "SG" }}
              </td>
              <td class="py-3 px-4 text-slate-400 text-[11px]">
                {{ formatDate(item.created_at) }}
              </td>
              <td class="py-3 px-4 text-right">
                <button
                  @click.stop="handleSelectAndGo(item.id)"
                  class="px-2.5 py-1 rounded-lg bg-indigo-600/10 border border-indigo-500/30 text-indigo-400 hover:bg-indigo-600 hover:text-white text-[11px] font-semibold transition"
                >
                  Xem chi tiết
                </button>
              </td>
            </tr>

            <!-- Empty Row -->
            <tr v-if="filteredTasks.length === 0 && !taskStore.historyLoading">
              <td colspan="6" class="py-12 text-center text-slate-500">
                <div class="text-3xl mb-2">📭</div>
                <p>Không có tác vụ nào phù hợp.</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Load More / Pagination -->
      <div v-if="taskStore.historyHasMore" class="p-4 border-t border-slate-800/80 text-center">
        <button
          @click="loadMore"
          :disabled="taskStore.historyLoading"
          class="px-4 py-2 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 text-xs font-semibold text-slate-300 hover:text-white transition"
        >
          {{ taskStore.historyLoading ? "Đang tải thêm..." : "Tải thêm tác vụ cũ ⬇️" }}
        </button>
      </div>
    </div>
    <p v-if="taskStore.historyError" role="alert" class="text-xs text-rose-300">{{ taskStore.historyError }}</p>
  </div>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { useTaskStore } from "../stores/taskStore";
import { useAuthStore } from "../stores/authStore.js";

const router = useRouter();
const taskStore = useTaskStore();
const authStore = useAuthStore();

const statusFilter = ref("");

const filteredTasks = computed(() => {
  const list = taskStore.historyTasks;
  if (!statusFilter.value) return list;
  return list.filter((t) => t.status === statusFilter.value);
});

function getStatusBadgeClass(status) {
  switch (status) {
    case "DRAFT":
      return "bg-slate-800 text-slate-300 border-slate-700";
    case "PREPARING":
      return "bg-amber-500/10 text-amber-400 border-amber-500/30";
    case "SUBMITTING":
      return "bg-sky-500/10 text-sky-400 border-sky-500/30";
    case "SUBMITTED":
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
    case "FAILED":
      return "bg-rose-500/10 text-rose-400 border-rose-500/30";
    case "CANCELLED":
      return "bg-slate-700 text-slate-400 border-slate-600";
    default:
      return "bg-slate-800 text-slate-400 border-slate-700";
  }
}

function formatDate(isoStr) {
  if (!isoStr) return "-";
  try {
    return new Date(isoStr).toLocaleString();
  } catch {
    return isoStr;
  }
}

function handleSelect(id) {
  taskStore.selectTask(id);
}

function handleSelectAndGo(id) {
  taskStore.selectTask(id);
  router.push("/");
}

async function refreshList() {
  await taskStore.fetchHistory(0);
}

async function loadMore() {
  if (taskStore.historyHasMore) {
    await taskStore.fetchHistory(taskStore.historyOffset);
  }
}

async function handleFilterChange() {
  // Can trigger server-side or local filter
}

watch(() => authStore.sessionContext, async session => {
  if (!session || !authStore.isAuthenticated) return;
  taskStore.initWebSocketListener();
  await taskStore.fetchHistory(0);
}, {immediate: true});
</script>
