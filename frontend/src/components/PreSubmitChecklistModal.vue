<!-- File: frontend/src/components/PreSubmitChecklistModal.vue -->
<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80" @click="$emit('close')">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl p-6 max-h-[92vh] overflow-auto" @click.stop>
      <div class="flex justify-between mb-4"><h3 class="font-bold text-white">Review Facebook · Copyright report</h3><button @click="$emit('close')">✕</button></div>
      <ol class="space-y-3 text-sm text-slate-300">
        <li>1. Rights: <strong>Copyright</strong></li>
        <li>2. Platform: <strong>Facebook</strong> · batched up to 30 URLs per report</li>
        <li class="bg-slate-950 rounded-lg p-3">
          3. Rights owner: {{ ownerProfile?.rights_owner_name || 'Missing' }}<br />
          Jurisdiction: {{ ownerProfile?.rights_jurisdiction || 'Missing' }}<br />
          Role: {{ ownerProfile?.owner_role || 'Missing' }}
        </li>
        <li class="bg-slate-950 rounded-lg p-3">
          4. Original: {{ originalWorkUrl || 'Missing public source URL' }}<br />
          Sender: {{ ownerProfile?.sender_name || 'Missing' }}<br />
          Electronic signature: {{ ownerProfile?.rights_owner_name || 'Missing' }}<br />
          Email and confirmation: {{ ownerProfile?.email }}<br />
          Explanation: {{ customExplanation || 'Standard text: review its accuracy for your work.' }}
          <p class="mt-2 text-xs text-amber-300">The tool reads a correlated code from your connected Microsoft mailbox. Connect and map the contact email before Start. Court order remains unchecked. Submitting confirms Meta's declaration statement; use accurate details.</p>
        </li>
      </ol>
      <ul class="text-xs mt-3 max-h-32 overflow-auto"><li v-for="task in parsedTasks" :key="task.url" class="py-1 break-all">{{ task.url }}</li></ul>
      <p class="text-xs text-slate-400 mt-3">Original sources must link directly to your work. Meta states it cannot review material on cloud file hosting services. Local uploads do not replace a public source URL.</p>
      <p v-if="proofFile" class="text-xs text-slate-400">Local attachment: {{ proofFile.name }} (archival only)</p>
      <p v-if="blockingError" role="alert" class="text-rose-400 text-sm mt-3">{{ blockingError }}</p>
      <div class="space-y-2 mt-4 pt-3 border-t border-slate-800">
        <label class="flex items-center gap-3 text-xs font-semibold text-indigo-400 cursor-pointer select-none pb-2 border-b border-slate-800 hover:text-indigo-300 transition">
          <input
            type="checkbox"
            v-model="allChecked"
            :indeterminate.prop="isIndeterminate"
            class="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
          />
          <span>Check all (Select all 4 declarations)</span>
        </label>
        <div class="space-y-2 pt-1">
          <label v-for="(label, index) in factors" :key="label" class="flex items-start gap-3 text-xs text-slate-300 cursor-pointer hover:text-slate-100 transition">
            <input
              type="checkbox"
              v-model="checked[index]"
              class="mt-0.5 rounded border-slate-700 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
            />
            <span>{{ label }}</span>
          </label>
        </div>
      </div>
      <div class="flex justify-between mt-5">
        <button @click="$emit('close')" :disabled="isSubmitting" class="px-4 py-2 text-sm">Back to edit</button>
        <button @click="$emit('confirm')" :disabled="!canSubmit || isSubmitting" class="px-4 py-2 rounded-lg bg-indigo-600 disabled:opacity-40 text-sm">Confirm & enqueue</button>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, ref, watch } from 'vue';
import { validateOriginalWorkUrl } from '../utils/urlValidator';
const props = defineProps({isOpen:Boolean, ownerProfile:Object, originalWorkUrl:String, proofFile:Object, parsedTasks:{type:Array,default:()=>[]}, isSubmitting:Boolean, customExplanation:String});
defineEmits(['confirm','close']);
const checked = ref([false,false,false,false]);
const factors = ['I am the named rights owner, and the same owner name is my electronic signature.', 'The original source is public, direct and accurately identifies my work.', 'I reviewed every Facebook target and its infringement of this work.', 'My explanation, contact details and declaration are accurate and made in good faith.'];

const allChecked = computed({
  get: () => checked.value.length > 0 && checked.value.every(Boolean),
  set: (val) => {
    checked.value = factors.map(() => Boolean(val));
  }
});

const isIndeterminate = computed(() => {
  const count = checked.value.filter(Boolean).length;
  return count > 0 && count < factors.length;
});

watch(() => [props.isOpen,props.ownerProfile,props.originalWorkUrl,props.parsedTasks,props.customExplanation], () => { checked.value = [false,false,false,false]; }, {deep:true});
const blockingError = computed(() => {
  const p = props.ownerProfile;
  if (!p || p.submission_eligible !== true || p.owner_role !== 'OWNER') return p?.submission_block_reason || 'Confirm OWNER and complete the profile before enqueueing.';
  const original = validateOriginalWorkUrl(props.originalWorkUrl);
  if (!original.valid) return original.error;
  if (!props.parsedTasks.length || props.parsedTasks.some(t=>t.platform !== 'FACEBOOK')) return 'Every target must be on Facebook.';
  return '';
});
const canSubmit = computed(() => checked.value.every(Boolean) && !blockingError.value);
</script>
