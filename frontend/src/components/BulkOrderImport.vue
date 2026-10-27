<!-- File: frontend/src/components/BulkOrderImport.vue -->
<template>
  <section class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
    <h2 class="text-xl font-bold text-white">Nhập nhiều đơn · xoay vòng mail OTP</h2>
    <p class="text-xs text-slate-400">
      Hai TXT UTF-8, tối đa 2 MiB/tệp. Chọn file và kết nối chỉ chuẩn bị dữ liệu. Tạo bản nháp, xem xét rồi bấm Chạy riêng.
      <span class="block mt-1 font-semibold text-indigo-300">Chạy tối đa 3 tác vụ đồng thời.</span>
    </p>
    <label class="block text-xs">Tên lượt nhập<input v-model="form.name" maxlength="255" class="block w-full mt-1 p-2 bg-slate-950 border border-slate-700 rounded-lg" :disabled="locked" /></label>
    <label class="block text-xs">Hồ sơ OWNER<select v-model="form.profile_id" :disabled="locked" class="block w-full mt-1 p-2 bg-slate-950 border border-slate-700 rounded-lg"><option value="">Chọn chủ sở hữu</option><option v-for="profile in profiles.profiles" :key="profile.id" :value="profile.id" :disabled="!profile.submission_eligible || profile.owner_role !== 'OWNER'">{{ profile.rights_owner_name }} · {{ profile.sender_name }}</option></select></label>
    <p class="text-xs text-slate-400">Chủ sở hữu, người gửi và chữ ký dùng hồ sơ đã chọn. Mail được gán trong file sẽ điền ô email hiện có của Meta và nhận OTP.</p>
    <label class="block text-xs">File đơn (tối đa 1.000 khối)<input type="file" accept=".txt,text/plain" :disabled="locked" @change="selectOrders" class="block w-full mt-1 text-xs" /></label>
    <details class="text-xs text-slate-400"><summary>Cấu trúc mẫu (chỉ Facebook)</summary><pre class="whitespace-pre-wrap mt-2">tên website
https://example.com/original.jpg
website đã fake bài
https://www.facebook.com/example/posts/123

tên website
https://example.com/another.jpg
website đã fake bài
https://www.facebook.com/reel/456</pre></details>
    <label class="block text-xs">File Mail|Refresh_Token|Client_id (tối đa 100 dòng)<input type="file" accept=".txt,text/plain" :disabled="locked" @change="selectMail" class="block w-full mt-1 text-xs" /></label>
    <p class="text-xs text-slate-400">Tối đa 2 kết nối đồng thời. Token chỉ ở bộ nhớ tạm; tệp được bỏ khỏi ô chọn ngay. Khởi động lại backend cần kết nối lại.</p>
    <label class="block text-xs">Giải thích (tùy chọn)<textarea v-model="form.custom_explanation" maxlength="500" :disabled="locked" rows="2" class="block w-full mt-1 p-2 bg-slate-950 border border-slate-700 rounded-lg" /></label>
    <label class="block text-xs">Quốc gia proxy<select v-model="form.preferred_country" :disabled="locked" class="ml-2 p-1 bg-slate-950 border border-slate-700 rounded-lg"><option value="">Tự động</option><option v-for="country in ['SG','AU','JP','KR','JO']" :key="country">{{ country }}</option></select></label>
    <BulkOrderPreview :orders="orders" :rows="store.rows" :errors="store.errors" :preview="store.preview" />
    <label v-if="excludedCount" class="flex gap-2 text-xs text-amber-300"><input v-model="store.exclusionsAccepted" type="checkbox" :disabled="locked" />Tôi đã xem {{ excludedCount }} mail bị loại và đồng ý chỉ dùng mail thành công theo thứ tự dòng.</label>
    <label v-if="store.preview?.content_matches.length" class="flex gap-2 text-xs text-amber-300"><input v-model="store.duplicatesAccepted" type="checkbox" :disabled="locked" />Tôi đã kiểm tra lượt trùng, bằng chứng gửi và vẫn muốn tạo lượt mới.</label>
    <p v-if="store.error" role="alert" class="text-xs text-rose-300">{{ store.error }}</p>
    <p v-if="cleanupIds.length" class="text-xs text-amber-300">Chưa xác nhận dọn kết nối. <button class="underline" @click="session.retryCleanup()">Thử dọn lại</button></p>
    <p v-if="store.importId" class="text-xs break-all text-slate-400">Mã nhập để tra cứu: {{ store.importId }}</p>
    <div class="flex flex-wrap gap-3 text-xs">
      <button @click="preview" :disabled="!canPreview" class="px-3 py-2 rounded-lg bg-indigo-600 disabled:opacity-40">Xem trước</button>
      <button @click="checklist = true" :disabled="!canCreate" class="px-3 py-2 rounded-lg bg-indigo-600 disabled:opacity-40">Xác nhận</button>
      <button v-if="store.outcomeUnknown" @click="lookup" :disabled="store.busy" class="px-3 py-2 rounded-lg bg-amber-700">Tra cứu cùng mã nhập</button>
      <button @click="reset" :disabled="store.busy && !connecting || store.outcomeUnknown" class="px-3 py-2 rounded-lg border border-slate-700">{{ connecting ? 'Hủy kết nối' : 'Lượt nhập mới' }}</button>
    </div>
    <p v-if="store.jobId" class="text-xs text-emerald-300">Đã tạo bản nháp. Xem bảng công việc, kiểm tra trước Chạy rồi bấm Start Execution.</p>
    <PreSubmitChecklistModal :isOpen="checklist" :ownerProfile="checklistProfile" :originalWorkUrl="orders[0]?.original_url || ''" :parsedTasks="checklistTasks" :customExplanation="form.custom_explanation" :isSubmitting="store.busy" @close="checklist = false" @confirm="createDraft" />
  </section>
</template>
<script setup>
import { computed, onUnmounted, reactive, ref, watch } from 'vue';
import { useProxyStore } from '../stores/proxyStore.js';
import { useJobStore } from '../stores/jobStore.js';
import { useBulkImportStore } from '../stores/bulkImportStore.js';
import { mailboxApi } from '../services/api.js';
import { bulkJobsApi } from '../services/bulkJobsApi.js';
import { bulkReasonMessage } from '../utils/bulkMessages.js';
import { createBulkMailboxSession } from '../services/bulkMailboxConnect.js';
import { readBulkFile, parseBulkOrders } from '../utils/bulkOrderFile.js';
import BulkOrderPreview from './BulkOrderPreview.vue';
import PreSubmitChecklistModal from './PreSubmitChecklistModal.vue';
const profiles = useProxyStore(), jobs = useJobStore(), store = useBulkImportStore();
const form = reactive({name:'', profile_id:'', preferred_country:'', custom_explanation:''});
const orders = ref([]), checklist = ref(false), connecting = ref(false), ordersLoading = ref(false), cleanupIds = ref([]);
let ordersText = '', pendingCreate = null, fileEpoch = 0;
const session = createBulkMailboxSession(mailboxApi, (rows, ids) => { store.setRows(rows); cleanupIds.value = ids; });
const selectedProfile = computed(() => profiles.profiles.find(profile => profile.id === form.profile_id));
const checklistProfile = computed(() => selectedProfile.value ? {...selectedProfile.value, email:'Theo mail được gán của từng đơn trong bảng xem trước'} : null);
const checklistTasks = computed(() => orders.value.flatMap(order => order.target_urls.map(url => ({url, platform:'FACEBOOK'}))));
const excludedCount = computed(() => store.rows.filter(row => row.status === 'excluded').length);
const locked = computed(() => store.busy || ordersLoading.value || !!store.jobId || store.outcomeUnknown);
const canPreview = computed(() => !locked.value && !cleanupIds.value.length && !store.errors.length && orders.value.length > 0 && session.references().length > 0 && !!form.name.trim() && selectedProfile.value?.submission_eligible === true);
const canCreate = computed(() => canPreview.value && store.preview?.can_create && (!excludedCount.value || store.exclusionsAccepted) && (!store.preview.content_matches.length || store.duplicatesAccepted));
watch([form, selectedProfile], () => { store.invalidate(); checklist.value = false; pendingCreate = null; }, {deep:true});
const message = error => {
  const reason = error?.response?.data?.detail;
  return typeof reason === 'string' && /^[A-Z_]+$/.test(reason) ? bulkReasonMessage(reason) : 'Không hoàn tất yêu cầu. Kiểm tra trạng thái rồi thử lại.';
};
async function selectOrders(event) {
  const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
  const generation = ++fileEpoch; store.error = ''; store.invalidate(); ordersLoading.value = true;
  try { const text = await readBulkFile(file); if (generation !== fileEpoch) return; ordersText = text; const parsed = parseBulkOrders(text); orders.value = parsed.orders; store.setErrors(parsed.errors); }
  catch (error) { if (generation === fileEpoch) { ordersText = ''; orders.value = []; store.setErrors([{source_line:1, reason:error.message}]); } }
  finally { if (generation === fileEpoch) ordersLoading.value = false; }
}
async function selectMail(event) {
  const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
  const generation = ++fileEpoch; store.busy = true; connecting.value = true; store.error = ''; store.invalidate();
  try { let text = await readBulkFile(file); if (generation !== fileEpoch) return; const work = session.connect(text); text = ''; await work; }
  catch (error) { if (generation === fileEpoch) store.error = message(error); }
  finally { if (generation === fileEpoch) {store.busy = false; connecting.value = false;} }
}
const payload = () => ({...form, name:form.name.trim(), orders_text:ordersText, mailboxes:session.references(), preferred_country:form.preferred_country || null, custom_explanation:form.custom_explanation.trim() || null});
async function preview() {
  if (!canPreview.value) return;
  const revision = store.revision; store.busy = true; store.error = '';
  try { const result = await bulkJobsApi.preview(payload()); if (store.acceptPreview(result, revision)) orders.value = result.normalized_orders || orders.value; }
  catch (error) { store.error = message(error); }
  finally { store.busy = false; }
}
async function acceptCreated(result) { session.handoff(); store.created(result); pendingCreate = null; checklist.value = false; await jobs.fetchJobs(); await jobs.selectJob(result.job_id); }
async function createDraft() {
  if (!canCreate.value) return;
  store.busy = true; store.error = '';
  if (!pendingCreate) { store.beginImport(crypto.randomUUID()); pendingCreate = {import_id:store.importId, preview:payload(), expected_profile_sha256:store.preview.profile_sha256, preview_sha256:store.preview.preview_sha256, duplicate_ack_sha256:store.duplicatesAccepted ? store.preview.duplicate_ack_sha256 : null}; }
  try { await acceptCreated(await bulkJobsApi.create(pendingCreate)); }
  catch (error) {
    if (!error.response || error.response.status >= 500) { store.outcomeUnknown = true; store.error = 'Kết quả tạo chưa rõ. Tra cứu cùng mã nhập; không tạo lượt mới.'; }
    else { store.error = message(error); pendingCreate = null; store.invalidate(); }
  } finally { store.busy = false; }
}
async function lookup() {
  if (!store.importId) return; store.busy = true;
  try { await acceptCreated(await bulkJobsApi.lookup(store.importId)); }
  catch (error) { if (error.response?.status === 404 && pendingCreate) { try {await acceptCreated(await bulkJobsApi.create(pendingCreate));} catch (failure) {store.error = message(failure);} } else store.error = message(error); }
  finally { store.busy = false; }
}
async function reset() { fileEpoch++; checklist.value = false; await session.cancel(); ordersText = ''; pendingCreate = null; orders.value = []; store.reset(); connecting.value = false; ordersLoading.value = false; }
onUnmounted(() => {fileEpoch++; ordersText = ''; pendingCreate = null; session.cancel();});
</script>
