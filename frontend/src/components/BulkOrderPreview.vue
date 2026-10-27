<!-- File: frontend/src/components/BulkOrderPreview.vue -->
<template>
  <section class="space-y-3 text-xs">
    <p class="text-slate-300">{{ orders.length }} đơn · {{ readyCount }} mail sẵn sàng. Mỗi khối giữ nguyên một đơn (tối đa 30 URL vi phạm).</p>
    <p v-if="errors.length" role="alert" class="text-rose-300">File đơn có lỗi; cần sửa tất cả trước khi tạo bản nháp.</p>
    <ul class="max-h-40 overflow-auto text-rose-300"><li v-for="(error,index) in errors" :key="index">Dòng {{ error.source_line }}: {{ bulkReasonMessage(error.reason) }}</li></ul>
    <div v-if="rows.length" class="max-h-40 overflow-auto border border-slate-800 rounded-lg p-2">
      <p v-for="row in rows" :key="row.source_line" :class="row.status === 'excluded' ? 'text-amber-300' : 'text-slate-300'">Mail dòng {{ row.source_line }} · {{ row.masked_email }} · {{ bulkRowStatus(row.status) }} {{ bulkReasonMessage(row.reason) }}</p>
    </div>
    <div v-if="preview?.content_matches?.length" class="text-amber-300 border border-amber-700 rounded-lg p-3">
      <p>Nội dung tương tự đã tồn tại. Kiểm tra lịch sử và bằng chứng gửi trước khi tạo lượt mới:</p>
      <p v-for="match in preview.content_matches" :key="match.job_id">{{ match.job_id }} · {{ match.status }} · đã gửi {{ match.submitted_count }} · {{ match.has_uncertain ? 'có kết quả chưa rõ' : '' }}</p>
    </div>
    <div v-if="orders.length" class="overflow-x-auto border border-slate-800 rounded-lg">
      <table class="w-full text-left"><thead class="bg-slate-950 text-slate-400"><tr><th class="p-2">Đơn / dòng</th><th class="p-2">Gốc / vi phạm</th><th class="p-2">Mail được gán</th></tr></thead>
        <tbody><tr v-for="order in pageOrders" :key="order.sequence" class="border-t border-slate-800"><td class="p-2">{{ order.sequence }} / {{ order.source_line }}</td><td class="p-2 break-all"><p>{{ order.original_url }}</p><details><summary>{{ order.target_urls.length }} URL vi phạm</summary><p v-for="(url,index) in order.target_urls" :key="index">{{ url }}</p></details></td><td class="p-2">{{ assignments.get(order.sequence) || 'Chưa xem trước' }}</td></tr></tbody>
      </table>
    </div>
    <div v-if="orders.length > 100" class="flex justify-between"><button :disabled="page === 0" @click="page--">Trang trước</button><span>{{ page + 1 }}/{{ Math.ceil(orders.length / 100) }}</span><button :disabled="(page + 1) * 100 >= orders.length" @click="page++">Trang sau</button></div>
  </section>
</template>
<script setup>
import { computed, ref, watch } from 'vue';
import { bulkReasonMessage, bulkRowStatus } from '../utils/bulkMessages.js';
const props = defineProps({orders:{type:Array,default:()=>[]}, rows:{type:Array,default:()=>[]}, errors:{type:Array,default:()=>[]}, preview:Object});
const page = ref(0);
watch(() => props.orders, () => {page.value = 0;});
const pageOrders = computed(() => props.orders.slice(page.value * 100, (page.value + 1) * 100));
const readyCount = computed(() => props.rows.filter(row => row.status === 'ready').length);
const assignments = computed(() => new Map((props.preview?.masked_assignments || []).map(row => [row.sequence, row.masked_email])));
</script>
