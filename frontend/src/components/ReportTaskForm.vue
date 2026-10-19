<!-- File: frontend/src/components/ReportTaskForm.vue -->
<template>
  <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl shadow-xl">
    <div class="flex items-center justify-between mb-5">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold text-sm">
          📝
        </div>
        <div>
          <h2 class="text-sm font-bold text-white tracking-wide">Tạo Tác Vụ Báo Cáo Mới</h2>
          <p class="text-[11px] text-slate-400">Standalone Report Task (1–30 URLs, thực thi tuần tự)</p>
        </div>
      </div>

      <!-- Execution Status Tag -->
      <div
        :class="slotStatusBadgeClass"
        class="px-2.5 py-1 rounded-full text-[11px] font-semibold border flex items-center gap-1.5"
      >
        <span class="w-2 h-2 rounded-full" :class="slotStatusDotClass"></span>
        <span>{{ slotStatusLabel }}</span>
      </div>
    </div>

    <form @submit.prevent="handleSubmit" class="space-y-4">
      <!-- Task Name -->
      <div>
        <label class="block text-xs font-semibold text-slate-300 mb-1">
          Tên tác vụ <span class="text-rose-400">*</span>
        </label>
        <input
          v-model="form.name"
          type="text"
          placeholder="Ví dụ: Report DMCA Post Vi phạm #01"
          required
          class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
        />
      </div>

      <!-- Profile & Country -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-300 mb-1">
            Chủ sở hữu Profile <span class="text-rose-400">*</span>
          </label>
          <select
            v-model="form.owner_profile_id"
            required
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
          >
            <option value="" disabled>-- Chọn hồ sơ đại diện --</option>
            <option v-for="p in proxyStore.profiles" :key="p.id" :value="p.id">
              {{ p.full_name }} ({{ p.email }})
            </option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-semibold text-slate-300 mb-1">
            Quốc gia Proxy ưu tiên
          </label>
          <select
            v-model="form.preferred_country"
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500 transition"
          >
            <option value="SG">Singapore (SG)</option>
            <option value="AU">Australia (AU)</option>
            <option value="JP">Japan (JP)</option>
            <option value="KR">Korea (KR)</option>
            <option value="JO">Jordan (JO)</option>
          </select>
        </div>
      </div>

      <!-- Target URLs (1..30) -->
      <div>
        <div class="flex items-center justify-between mb-1">
          <label class="block text-xs font-semibold text-slate-300">
            Danh sách URL vi phạm (1–30 URLs) <span class="text-rose-400">*</span>
          </label>
          <span
            :class="urlCountColor"
            class="text-[11px] font-bold"
          >
            {{ parsedUrls.all.length }} / 30 URL
          </span>
        </div>
        <textarea
          v-model="form.rawUrls"
          rows="4"
          placeholder="Nhập 1 đến 30 liên kết Facebook vi phạm (mỗi dòng một URL):
https://www.facebook.com/infringing_post_1
https://www.facebook.com/reel/12345678"
          class="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-white font-mono placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition resize-y"
        ></textarea>
        <p v-if="urlValidationError" class="text-[11px] text-rose-400 mt-1 font-medium">
          ⚠️ {{ urlValidationError }}
        </p>
      </div>

      <!-- Original Work URL -->
      <div>
        <label class="block text-xs font-semibold text-slate-300 mb-1">
          Liên kết tác phẩm gốc bản quyền <span class="text-rose-400">*</span>
        </label>
        <input
          v-model="form.original_work_url"
          type="url"
          placeholder="https://facebook.com/original_creator_post"
          required
          class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition font-mono"
        />
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-300 mb-1">Nội dung giải trình (tùy chọn)</label>
        <textarea v-model="form.custom_explanation" rows="3" maxlength="10000"
          class="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-white focus:outline-none focus:border-indigo-500"></textarea>
      </div>

      <!-- Proof of Work File (Raster images) -->
      <div>
        <label class="block text-xs font-semibold text-slate-300 mb-1">
          Tệp bằng chứng bản quyền (Proof of Work)
        </label>
        <div class="flex items-center gap-3">
          <input
            type="file"
            ref="fileInput"
            @change="handleFileChange"
            accept=".png,.jpg,.jpeg,.webp"
            class="hidden"
          />
          <button
            type="button"
            @click="$refs.fileInput.click()"
            class="px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 text-xs text-slate-300 hover:text-white transition flex items-center gap-1.5"
          >
            <span>📎</span>
            <span>{{ selectedFile ? selectedFile.name : "Tải ảnh bằng chứng (.png, .jpg, .webp)" }}</span>
          </button>
          <button
            v-if="selectedFile"
            type="button"
            @click="clearFile"
            class="text-xs text-rose-400 hover:underline"
          >
            Gỡ bỏ
          </button>
        </div>
        <p class="text-[10px] text-slate-500 mt-1">Chấp nhận PNG, JPG, WEBP tối đa 10MB.</p>
      </div>

      <!-- Error banner -->
      <div v-if="taskStore.actionError" class="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs">
        {{ taskStore.actionError }}
      </div>

      <!-- Submit button -->
      <div class="pt-2">
        <button
          type="submit"
          :disabled="isSubmitDisabled"
          class="w-full py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
        >
          <span v-if="taskStore.actionLoading" class="animate-spin">⏳</span>
          <span>{{ taskStore.actionLoading ? "Đang tạo tác vụ..." : "Tạo Tác Vụ (DRAFT)" }}</span>
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from "vue";
import { useTaskStore } from "../stores/taskStore";
import { useProxyStore } from "../stores/proxyStore";
import { parseFacebookBatchUrls } from "../utils/urlValidator";

const taskStore = useTaskStore();
const proxyStore = useProxyStore();

const fileInput = ref(null);
const selectedFile = ref(null);

const form = reactive({
  name: "",
  owner_profile_id: "",
  preferred_country: "SG",
  rawUrls: "",
  original_work_url: "",
  custom_explanation: "",
});

const parsedUrls = computed(() => {
  return parseFacebookBatchUrls(form.rawUrls);
});

const urlValidationError = computed(() => {
  const count = parsedUrls.value.all.length;
  if (count === 0 && form.rawUrls.trim().length > 0) {
    return "Không tìm thấy URL hợp lệ.";
  }
  if (count > 30) {
    return `Vượt quá giới hạn: ${count}/30 URLs. Vui lòng giảm bớt.`;
  }
  if (parsedUrls.value.invalid.length > 0) {
    return `Có ${parsedUrls.value.invalid.length} liên kết không phải Facebook hợp lệ.`;
  }
  return null;
});

const urlCountColor = computed(() => {
  const count = parsedUrls.value.all.length;
  if (count === 0) return "text-slate-500";
  if (count > 30) return "text-rose-400";
  return "text-indigo-400";
});

const slotStatusLabel = computed(() => {
  switch (taskStore.executionAvailability?.reason) {
    case "BUSY":
      return "Slot bận (Đang chạy)";
    case "RECOVERY_REQUIRED":
      return "Cần phục hồi";
    case "UNAVAILABLE":
      return "Không khả dụng";
    case "READY":
      return "Slot sẵn sàng";
    default:
      return taskStore.availabilityText;
  }
});

const slotStatusBadgeClass = computed(() => {
  switch (taskStore.executionAvailability?.reason) {
    case "BUSY":
      return "bg-amber-500/10 text-amber-400 border-amber-500/30";
    case "RECOVERY_REQUIRED":
      return "bg-rose-500/10 text-rose-400 border-rose-500/30";
    case "READY":
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
    default:
      return "bg-slate-800 text-slate-400 border-slate-700";
  }
});

const slotStatusDotClass = computed(() => {
  switch (taskStore.executionAvailability?.reason) {
    case "BUSY":
      return "bg-amber-400 animate-pulse";
    case "RECOVERY_REQUIRED":
      return "bg-rose-400";
    case "READY":
      return "bg-emerald-400";
    default:
      return "bg-slate-400";
  }
});

const isSubmitDisabled = computed(() => {
  const count = parsedUrls.value.valid.length;
  return (
    taskStore.actionLoading ||
    !form.name.trim() ||
    !form.owner_profile_id ||
    !form.original_work_url.trim() ||
    count === 0 ||
    count > 30 ||
    parsedUrls.value.invalid.length > 0
  );
});

function handleFileChange(event) {
  const file = event.target.files[0];
  if (!file) return;

  const validTypes = ["image/png", "image/jpeg", "image/webp"];
  if (!validTypes.includes(file.type)) {
    alert("Chỉ chấp nhận file ảnh định dạng PNG, JPG, hoặc WEBP.");
    event.target.value = "";
    selectedFile.value = null;
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    alert("Kích thước tệp không được vượt quá 10MB.");
    event.target.value = "";
    selectedFile.value = null;
    return;
  }
  selectedFile.value = file;
}

function clearFile() {
  selectedFile.value = null;
  if (fileInput.value) {
    fileInput.value.value = "";
  }
}

async function handleSubmit() {
  if (isSubmitDisabled.value) return;

  const targetUrls = parsedUrls.value.valid.map((item) => item.url);
  const formData = new FormData();
  formData.append("name", form.name.trim());
  formData.append("owner_profile_id", form.owner_profile_id);
  formData.append("target_urls_json", JSON.stringify(targetUrls));
  formData.append("original_work_url", form.original_work_url.trim());
  formData.append("preferred_country", form.preferred_country);
  if (form.custom_explanation.trim()) formData.append("custom_explanation", form.custom_explanation.trim());

  if (selectedFile.value) {
    formData.append("proof", selectedFile.value);
  }

  try {
    const created = await taskStore.createTask(formData);
    if (!created) return;
    // Reset form on success
    form.name = "";
    form.rawUrls = "";
    form.original_work_url = "";
    form.custom_explanation = "";
    clearFile();
  } catch (err) {
    console.error("Create task failed:", err);
  }
}
</script>
