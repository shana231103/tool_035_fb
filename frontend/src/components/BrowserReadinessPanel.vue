<!-- File: frontend/src/components/BrowserReadinessPanel.vue -->
<template>
  <section class="rounded-xl border border-slate-700 bg-slate-900 px-4 py-3" aria-label="Trình duyệt tự động">
    <div class="flex items-center justify-between gap-4">
      <p role="status" aria-live="polite" :class="browser.canStart ? 'text-emerald-300' : 'text-amber-200'">
        {{ message }}
      </p>
      <button @click="browser.refresh()" :disabled="browser.loading"
        class="rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-200 disabled:opacity-40">
        Kiểm tra lại
      </button>
    </div>
    <p v-if="browser.status?.pending || browser.status?.unknown" class="mt-2 text-sm text-slate-400">
      Một phiên trình duyệt đang cần xử lý. Kết quả báo cáo đã xác nhận vẫn được giữ nguyên.
    </p>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue';
import { useBrowserStore } from '../stores/browserStore.js';
import { browserUnavailable } from '../services/browserStatus.js';
const browser = useBrowserStore();
const message = computed(() => browser.loading ? 'Đang kiểm tra trình duyệt…'
  : browser.canStart ? 'Trình duyệt đã sẵn sàng.' : browserUnavailable);
onMounted(() => browser.init());
onUnmounted(() => browser.stop());
</script>
