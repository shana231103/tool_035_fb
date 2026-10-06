<!-- File: frontend/src/components/EmailVerificationModal.vue -->
<template>
  <div v-if="task" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80" @click="$emit('close')">
    <section class="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4" @click.stop>
      <div class="flex justify-between"><h3 class="font-bold">Automatic email verification</h3><button @click="$emit('close')" aria-label="Close verification">✕</button></div>
      <p class="text-xs text-slate-400 break-all">Task {{ task.id }} · {{ task.target_url }}</p>
      <p class="text-sm">{{ task.verification?.masked_email || 'Mapped Microsoft mailbox' }} · {{ task.status }}</p>
      <p role="status" class="text-sm text-indigo-300">{{ progressText }}</p>
      <p class="text-xs text-slate-400">Requested: {{ task.verification?.requested_at || 'Pending' }}<br />Tool wait deadline: {{ task.verification?.expires_at || 'Pending' }}</p>
      <p class="text-xs text-slate-400">Microsoft Graph reads a correlated code from the connected mailbox. Only Meta's response confirms verification. Unknown mail templates or form states stop before submission.</p>
      <p v-if="task.verification?.last_error" class="text-amber-400 text-sm">{{ task.verification.last_error }}</p>
      <p v-if="error" role="alert" class="text-rose-400 text-sm">{{ error }}</p>
      <p v-if="accepted" role="status" class="text-indigo-300 text-xs">Resend command accepted. Waiting for the form and a new correlated email.</p>
      <div class="flex justify-between gap-4">
        <button @click="resend" :disabled="!canResend || busy" class="text-xs disabled:opacity-40">Request another email</button>
        <button @click="refresh" :disabled="busy" class="rounded-lg bg-slate-800 px-4 py-2 text-sm">Refresh progress</button>
      </div>
      <p class="text-xs text-slate-400">Resend is available only when the observed form supports it and the attempt budget allows it.</p>
    </section>
  </div>
</template>
<script setup>
import { ref, computed, watch, onUnmounted } from 'vue';
import { verificationApi } from '../services/api';
import { useJobStore } from '../stores/jobStore';
const props = defineProps({task:Object});
defineEmits(['close']);
const store = useJobStore();
const error = ref(''), busy = ref(false), accepted = ref(false), now = ref(Date.now());
const timer = setInterval(() => { now.value = Date.now(); }, 1000);
onUnmounted(() => clearInterval(timer));
const canResend = computed(() => props.task?.status === 'WAITING_EMAIL_CODE' &&
  !!props.task.attempt_id && !!props.task.verification?.challenge_id &&
  props.task.verification.resend_supported === true && Date.parse(props.task.verification.expires_at) > now.value);
const progressText = computed(() => ({WAITING_EMAIL_SLOT:'Waiting for the email slot.',
  WAITING_EMAIL_CODE:'Reading the connected Microsoft mailbox.', VERIFYING_EMAIL:'Meta is checking the code.',
  SUBMITTING:'Email verification completed; report submission is in progress.', SUBMITTED:'Report receipt confirmed.'
}[props.task?.status] || 'This verification attempt has ended. Review task state.'));
watch(() => [props.task?.id,props.task?.verification?.challenge_id,props.task?.status], () => { accepted.value=false; error.value=''; });
async function refresh() { if (store.selectedJob) await store.selectJob(store.selectedJob.id); }
async function resend() {
  if (!canResend.value || busy.value) return;
  const task = props.task, challenge = task.verification.challenge_id;
  busy.value = true; error.value = '';
  try {
    await verificationApi.resend(task.id,{attempt_id:task.attempt_id,challenge_id:challenge});
    if (props.task?.id === task.id && props.task.verification?.challenge_id === challenge) accepted.value = true;
    await refresh();
  } catch { error.value = 'Resend was not accepted. Refresh task state and check the current challenge.'; }
  finally { busy.value = false; }
}
</script>
