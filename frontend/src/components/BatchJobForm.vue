<!-- File: frontend/src/components/BatchJobForm.vue -->
<template>
  <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl shadow-2xl">
    <div class="flex items-center justify-between mb-6 pb-4 border-b border-slate-800">
      <div>
        <h2 class="text-xl font-bold text-white flex items-center gap-2">
          <span class="w-3 h-3 rounded-full bg-indigo-500 animate-pulse"></span>
          Create Batch Report Job
        </h2>
        <p class="text-sm text-slate-400 mt-1">
          Facebook · Copyright · batched up to 30 URLs per report · four form pages
        </p>
      </div>
      <span class="px-3 py-1 bg-indigo-500/10 text-indigo-400 text-xs font-semibold rounded-full border border-indigo-500/20">
        DMCA Form 1523801815366035
      </span>
    </div>

    <form @submit.prevent="handleSubmit" class="space-y-6">
      <!-- Campaign Name & Rights Profile -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Job / Campaign Name *
          </label>
          <input
            v-model="form.name"
            type="text"
            required
            placeholder="e.g. October Copyright Protection Batch 1"
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Copyright Owner Profile *
          </label>
          <select
            v-model="form.owner_profile_id"
            required
            class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition"
          >
            <option value="" disabled>Select Rights Holder</option>
            <option v-for="p in proxyStore.profiles" :key="p.id" :value="p.id" :disabled="p.submission_eligible !== true || p.owner_role !== 'OWNER'">
              {{ p.rights_owner_name || p.full_name }} ({{ p.email }}) {{ !p.submission_eligible ? '— update OWNER profile' : '' }}
            </option>
          </select>
        </div>
      </div>

      <p class="text-xs text-indigo-300">Before Start, open Microsoft mailbox in the header, connect and confirm a mapping for this profile's contact email. Creating a draft does not require a connected mailbox; execution checks mapping and evidence readiness.</p>

      <!-- Target URLs Textarea -->
      <div>
        <div class="flex items-center justify-between mb-2">
          <label class="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Infringing Facebook URLs (One per line) *
          </label>
          <div class="flex items-center gap-2">
            <span v-if="hasInvalidMetaUrls" class="text-xs text-rose-400 font-semibold flex items-center gap-1">
              <span>⚠️</span> {{ invalidUrlsCount }} Unsupported URL(s)
            </span>
            <span class="text-xs text-slate-500 font-mono">
              {{ parsedUrlsCount }} URL(s) detected
            </span>
          </div>
        </div>
        <textarea
          v-model="rawUrlsText"
          rows="5"
          required
          placeholder="https://www.facebook.com/reel/123456789&#10;https://www.facebook.com/artist/posts/123456789"
          class="w-full bg-slate-950 border border-slate-800 rounded-xl p-4 text-sm font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition"
        ></textarea>
        <p class="text-[11px] text-slate-400 mt-1.5">
          You can report up to 30 URLs/IDs. URLs are automatically batched into Meta Form Page 4 (separated by a space, comma or semicolon).
        </p>
      </div>

      <!-- Original Work Source / Upload Proof -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-950/60 p-4 rounded-xl border border-slate-800/80">
        <div>
          <div class="flex items-center justify-between mb-2">
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-400">
              Direct public original work URL (required)
            </label>
            <span v-if="isLocalhostOriginal" class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 text-[10px] font-bold border border-rose-500/40">
              Localhost Blocked
            </span>
          </div>
          <input
            v-model="form.original_work_url"
            required
            type="url"
            placeholder="https://mywebsite.com/original-artwork.jpg"
            :class="isLocalhostOriginal ? 'border-rose-500/60 focus:ring-rose-500' : 'border-slate-800 focus:ring-indigo-500'"
            class="w-full bg-slate-900 border rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-2 transition"
          />
          <p v-if="isLocalhostOriginal" class="text-[11px] text-rose-400 mt-1.5 flex items-center gap-1">
            <span>⚠️</span> Localhost & private IPs cannot be accessed by Meta reviewers. Provide a direct public URL.
          </p>
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Optional local evidence attachment (archival only)
          </label>
          <input
            type="file"
            accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            @change="handleFileUpload"
            class="w-full text-xs text-slate-400 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-500 file:cursor-pointer transition"
          />
          <p class="text-[11px] text-slate-400 mt-1.5">Static PNG, JPEG or WebP · up to 10 MiB. Stored as a normalized PNG archive.</p>
          <p v-if="!form.original_work_url && !proofFile" class="text-[10px] text-amber-400/80 mt-1.5">
            * A public source URL is required. Uploading here does not publish your work.
          </p>
        </div>
      </div>

      <!-- Custom DMCA Explanation Textarea (ISSUE-06) -->
      <div>
        <div class="flex items-center justify-between mb-2">
          <label class="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Custom DMCA Legal Explanation (Optional)
          </label>
          <div class="flex items-center gap-2">
            <span class="text-[10px] text-slate-500">
              Leave blank to auto-generate tailored DMCA legal text
            </span>
            <span
              class="text-[10px] font-mono px-1.5 py-0.5 rounded"
              :class="(form.custom_explanation || '').length > 450 ? 'bg-amber-500/20 text-amber-400' : 'text-slate-400'"
            >
              {{ (form.custom_explanation || '').length }}/500
            </span>
          </div>
        </div>
        <textarea
          v-model="form.custom_explanation"
          rows="2"
          maxlength="500"
          placeholder="Leave blank to use the standard tailored DMCA legal statement, or enter custom legal explanation here..."
          class="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition"
        ></textarea>
      </div>

      <!-- Proxy Country -->
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          Proxy Routing Country
        </label>
        <select
          v-model="form.preferred_country"
          class="w-full max-w-md bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">Auto / Any Available</option>
          <option value="SG">🇸🇬 Singapore (SG)</option>
          <option value="AU">🇦🇺 Australia (AU)</option>
          <option value="JP">🇯🇵 Japan (JP)</option>
          <option value="KR">🇰🇷 South Korea (KR)</option>
          <option value="JO">🇯🇴 Jordan (JO)</option>
        </select>
      </div>

      <!-- Submit Button -->
      <div class="pt-2">
        <button
          type="submit"
          :disabled="isSubmitting || parsedUrlsCount === 0 || isLocalhostOriginal"
          class="w-full py-3.5 px-6 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold shadow-lg shadow-indigo-600/30 disabled:opacity-50 disabled:cursor-not-allowed transition duration-200 flex items-center justify-center gap-2"
        >
          <svg v-if="isSubmitting" class="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          <span>{{ isSubmitting ? "Ingesting Batch Job..." : "Review 4-Factor Checklist & Enqueue" }}</span>
        </button>
      </div>
    </form>

    <!-- Pre-Submit 4-Factor Review Modal -->
    <PreSubmitChecklistModal
      :isOpen="isChecklistModalOpen"
      :ownerProfile="selectedOwnerProfile"
      :originalWorkUrl="form.original_work_url"
      :proofFile="proofFile"
      :customExplanation="form.custom_explanation"
      :parsedTasks="parsedTasksForModal"
      :isSubmitting="isSubmitting"
      @confirm="handleConfirmSubmit"
      @close="isChecklistModalOpen = false"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { useJobStore } from "../stores/jobStore";
import { useProxyStore } from "../stores/proxyStore";
import PreSubmitChecklistModal from "./PreSubmitChecklistModal.vue";
import { isLocalhostOrPrivateUrl, parseFacebookBatchUrls } from "../utils/urlValidator";

const jobStore = useJobStore();
const proxyStore = useProxyStore();

const rawUrlsText = ref("");
const proofFile = ref(null);
const isSubmitting = ref(false);
const isChecklistModalOpen = ref(false);

const form = reactive({
  name: "",
  owner_profile_id: "",
  original_work_url: "",
  preferred_country: "",
  concurrency: 1,
  delay_min: 0,
  delay_max: 0,
  custom_explanation: "",
});

const isLocalhostOriginal = computed(() => {
  return isLocalhostOrPrivateUrl(form.original_work_url);
});

const parsedBatch = computed(() => {
  return parseFacebookBatchUrls(rawUrlsText.value);
});

const parsedUrlsCount = computed(() => {
  return parsedBatch.value.all.length;
});

const invalidUrlsCount = computed(() => {
  return parsedBatch.value.invalid.length;
});

const hasInvalidMetaUrls = computed(() => {
  return parsedBatch.value.hasNonMeta;
});

const parsedTasksForModal = computed(() => {
  return parsedBatch.value.valid;
});

const selectedOwnerProfile = computed(() => {
  return proxyStore.profiles.find((p) => p.id === form.owner_profile_id) || null;
});

const handleFileUpload = (e) => {
  const file = e.target.files[0];
  proofFile.value = null;
  if (file && (!/\.(png|jpe?g|webp)$/i.test(file.name) || file.size > 10485760 || file.size === 0)) {
    e.target.value = '';
    alert('Choose a nonempty static PNG, JPEG or WebP image up to 10 MiB.');
    return;
  }
  proofFile.value = file || null;
};

const handleSubmit = () => {
  // 1. Validate Campaign Name & Owner Profile
  if (!form.name.trim()) {
    alert("Please enter a Job / Campaign Name.");
    return;
  }
  if (!form.owner_profile_id) {
    alert("Please select a Copyright Owner Profile.");
    return;
  }
  if (selectedOwnerProfile.value?.submission_eligible !== true || selectedOwnerProfile.value?.owner_role !== 'OWNER') {
    alert("Confirm OWNER and complete owner, sender and jurisdiction in your profile first.");
    return;
  }

  // 2. Validate Target URLs
  if (parsedBatch.value.all.length === 0) {
    alert("Please enter at least one Facebook target URL.");
    return;
  }
  if (parsedBatch.value.invalid.length > 0) {
    alert("Every target must be a Facebook URL. Remove unsupported URLs before continuing.");
    return;
  }

  // 3. The public original URL is required independently of the archive.
  if (!form.original_work_url.trim()) {
    alert("A direct public original work URL is required. Local uploads cannot replace it.");
    return;
  }

  // 4. Localhost rejection guard
  if (isLocalhostOriginal.value) {
    alert("Submission Blocked: Localhost or private IP URLs cannot be accessed by Meta reviewers. Please provide a direct public original work URL.");
    return;
  }

  // All preliminary client checks pass: open Pre-Submit 4-Factor Review Modal
  isChecklistModalOpen.value = true;
};

const handleConfirmSubmit = async () => {
  const validUrlStrings = parsedBatch.value.valid.map((t) => t.url);
  if (validUrlStrings.length === 0) return;

  isSubmitting.value = true;
  try {
    const formData = new FormData();
    formData.append("name", form.name);
    formData.append("owner_profile_id", form.owner_profile_id);
    formData.append("target_urls_json", JSON.stringify(validUrlStrings));
    if (form.original_work_url) formData.append("original_work_url", form.original_work_url.trim());
    if (form.preferred_country) formData.append("preferred_country", form.preferred_country);
    formData.append("concurrency", form.concurrency);
    formData.append("delay_min", form.delay_min);
    formData.append("delay_max", form.delay_max);
    if (form.custom_explanation) formData.append("custom_explanation", form.custom_explanation.trim());
    if (proofFile.value) formData.append("proof_file", proofFile.value);

    await jobStore.createJob(formData);

    // Reset form and modal
    isChecklistModalOpen.value = false;
    rawUrlsText.value = "";
    proofFile.value = null;
    form.name = "";
    form.original_work_url = "";
    form.custom_explanation = "";
  } catch (err) {
    alert("Error creating batch job: " + (err.response?.data?.detail || err.message));
  } finally {
    isSubmitting.value = false;
  }
};
</script>
