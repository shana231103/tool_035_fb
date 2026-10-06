<!-- File: frontend/src/components/MicrosoftMailboxModal.vue -->
<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80" @click="close">
    <section class="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl p-6 max-h-[92vh] overflow-auto" @click.stop>
      <div class="flex justify-between mb-4"><h3 class="font-bold text-white">Microsoft mailbox</h3><button @click="close" aria-label="Close Microsoft mailbox">✕</button></div>
      <p class="text-xs text-slate-300 mb-3">Connect the mailbox that receives your Meta contact email. Delegated Mail.Read permits reading mailbox contents; filtering by folder or template does not narrow Microsoft's permission.</p>
      <p class="text-xs text-slate-400 mb-4">Connections and tokens stay in backend memory. Restart requires reconnecting. Local disconnect clears this tool's session; revoke Microsoft consent separately to remove the grant.</p>
      <p v-if="store.configuration && !store.configuration.login_configured" role="status" class="text-xs text-amber-300 mb-3">Enter and apply your Microsoft application ID below before connecting.</p>
      <form @submit.prevent="saveClientId" class="flex flex-wrap gap-2 mb-2">
        <label class="text-xs flex-1">Microsoft Application (client) ID
          <input v-model="clientId" required autocomplete="off" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" class="block w-full mt-1 rounded-lg bg-slate-950 border border-slate-700 p-2 font-mono" />
        </label>
        <button :disabled="store.busy || !clientId.trim()" class="self-end bg-slate-700 rounded-lg px-4 py-2 text-sm disabled:opacity-40">Apply ID</button>
      </form>
      <p class="text-xs text-slate-400 mb-3">The application ID is public, not a password or client secret. Changes apply until the backend restarts. Disconnect existing mailboxes before changing it.</p>
      <p class="text-xs text-slate-400 mb-3">Use your own Microsoft app registration with delegated User.Read and Mail.Read, personal accounts supported, and public client flows enabled.</p>
      <p v-if="clientSaved" role="status" class="text-xs text-emerald-300 mb-3">Application ID applied. You can connect your Microsoft mailbox.</p>
      <form @submit.prevent="connect" class="flex flex-wrap gap-2 mb-4">
        <label class="text-xs flex-1">Account hint (optional)
          <input v-model="accountHint" type="email" autocomplete="off" class="block w-full mt-1 rounded-lg bg-slate-950 border border-slate-700 p-2" />
        </label>
        <button :disabled="store.busy || !!store.prompt || !store.configuration?.login_configured" class="self-end bg-indigo-600 rounded-lg px-4 py-2 text-sm disabled:opacity-40">Connect / reauthenticate</button>
      </form>
      <div v-if="store.prompt" class="bg-indigo-950/40 border border-indigo-800 rounded-xl p-4 space-y-2 mb-4">
        <p class="text-sm">Open Microsoft's sign-in page and enter this Microsoft device login code:</p>
        <a v-if="loginUrl" :href="loginUrl" target="_blank" rel="noopener noreferrer" class="text-indigo-300 underline break-all">{{ loginUrl }}</a>
        <p class="text-xl font-mono tracking-widest select-all">{{ store.prompt.user_code }}</p>
        <p class="text-xs text-slate-400">Expires: {{ store.prompt.expires_at }}. This signs in to Microsoft; Meta verification runs automatically after mapping.</p>
        <p class="text-xs text-amber-300">Complete Microsoft sign-in and permissions in the linked page. Keep this panel open until Login: CONNECTED appears; closing now cancels the pending login.</p>
        <button @click="store.cancelLogin()" class="text-xs text-amber-300">Cancel login</button>
      </div>
      <p v-if="store.loginStatus" role="status" class="text-xs text-indigo-300 mb-3">Login: {{ store.loginStatus }}</p>
      <p v-if="store.error" role="alert" class="text-xs text-rose-400 mb-3">{{ store.error }}</p>
      <div class="flex justify-between mb-2"><h4 class="text-sm font-semibold">Connections</h4><button @click="store.fetchConnections()" class="text-xs text-indigo-300">Refresh</button></div>
      <p v-if="!store.connections.some(connection => connection.status === 'connected')" class="text-xs text-amber-300 py-3">No connected mailbox. Finish Microsoft sign-in, wait for CONNECTED, then confirm and save the mapping for your profile contact email before Start Execution.</p>
      <div v-for="connection in store.connections" :key="connection.id" class="border-t border-slate-800 py-3 space-y-2">
        <p class="text-sm">{{ connection.masked_email }} · {{ connection.status }}</p>
        <p class="text-xs text-slate-400">Meta mapping: {{ connection.mapped_email_masked || 'Not mapped' }}<span v-if="connection.expires_at"> · Session: {{ connection.expires_at }}</span></p>
        <p v-if="connection.safe_reason" class="text-xs text-amber-300">{{ connection.safe_reason }}</p>
        <div class="flex gap-4 text-xs">
          <button @click="selectConnection(connection.id)" :disabled="store.busy || connection.status !== 'connected'" class="text-indigo-300 disabled:opacity-40">Confirm mapping</button>
          <button @click="store.disconnect(connection.id)" :disabled="store.busy" class="text-rose-300">Disconnect</button>
        </div>
      </div>
      <form v-if="selectedId" @submit.prevent="saveMapping" class="border-t border-slate-700 mt-3 pt-4 space-y-3">
        <h4 class="text-sm font-semibold">Map the Meta contact email</h4>
        <label class="block text-xs">Meta contact email
          <input v-model="mapping.meta_email" type="email" required autocomplete="off" class="block mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg p-2" />
        </label>
        <label class="block text-xs">Authenticated primary mailbox email (required for alias mappings)
          <input v-model="mapping.primary_email" type="email" :required="!!aliases.trim()" autocomplete="off" class="block mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg p-2" />
        </label>
        <label class="block text-xs">Confirmed aliases (one per line, only if evidence proves delivery to this mailbox)
          <textarea v-model="aliases" rows="2" autocomplete="off" class="block mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg p-2"></textarea>
        </label>
        <div class="flex gap-4 text-xs"><label v-for="folder in ['inbox','junkemail']" :key="folder" class="flex gap-2"><input v-model="mapping.folders" type="checkbox" :value="folder" />{{ folder === 'inbox' ? 'Inbox' : 'Junk Email' }}</label></div>
        <p class="text-xs">Email type: {{ store.configuration?.template_label || 'Unavailable' }}</p>
        <p class="text-xs text-amber-300">Use this mailbox only for the current report while it runs. Other Meta code requests can mix up incoming codes. Automatic resend is unavailable for this email type.</p>
        <label class="flex gap-2 text-xs"><input v-model="mappingConfirmed" type="checkbox" required />I confirmed this email receives Meta mail here and will avoid other code requests while reporting.</label>
        <div class="flex justify-end gap-3 text-sm"><button type="button" @click="clearMapping">Cancel</button><button :disabled="store.busy || !mappingConfirmed || !mapping.folders.length || !store.configuration?.template_version" class="bg-indigo-600 rounded-lg px-4 py-2 disabled:opacity-40">Save mapping</button></div>
      </form>
      <p class="text-xs text-slate-500 mt-4">No Meta code entry is required. Device login codes are cleared when this panel closes; no login or mailbox secrets are stored in browser storage.</p>
    </section>
  </div>
</template>
<script setup>
import { computed, reactive, ref, watch, onUnmounted } from 'vue';
import { useMailboxStore } from '../stores/mailboxStore';
import { microsoftLoginUrl } from '../services/microsoftLoginUrl.js';
const props = defineProps({isOpen:Boolean});
const emit = defineEmits(['close']);
const store = useMailboxStore();
const accountHint = ref(''), selectedId = ref(null), aliases = ref(''), mappingConfirmed = ref(false);
const clientId = ref(''), clientSaved = ref(false);
const blank = () => ({meta_email:'', primary_email:'', folders:['inbox']});
const mapping = reactive(blank());
const loginUrl = computed(() => microsoftLoginUrl(store.prompt?.verification_uri));
function clearMapping() { selectedId.value = null; aliases.value = ''; mappingConfirmed.value = false; Object.assign(mapping, blank()); }
function selectConnection(id) { clearMapping(); selectedId.value = id; }
async function connect() { await store.startLogin(accountHint.value); accountHint.value = ''; }
async function saveClientId() { clientSaved.value = await store.configureClient(clientId.value); }
async function saveMapping() {
  if (!mappingConfirmed.value || !mapping.folders.length || !store.configuration?.template_version) return;
  const payload = {meta_email:mapping.meta_email.trim(), confirmed_aliases:aliases.value.split(/\r?\n/).map(value=>value.trim()).filter(Boolean),
    folders:[...mapping.folders], template_version:store.configuration?.template_version || ''};
  if (mapping.primary_email.trim()) payload.primary_email = mapping.primary_email.trim();
  if (await store.saveMapping(selectedId.value, payload)) clearMapping();
}
function close() { emit('close'); }
watch(() => props.isOpen, async (open) => {
  if (open) { await store.fetchConfiguration(); await store.fetchConnections(); }
  else { accountHint.value = ''; clientSaved.value = false; clearMapping(); await store.cancelLogin(); }
});
watch(() => store.configuration, (value) => { clientId.value = value?.client_id || ''; });
watch(() => store.connections, (connections) => { if (selectedId.value && !connections.some(item=>item.id === selectedId.value)) clearMapping(); });
onUnmounted(() => { store.cancelLogin(); });
</script>
