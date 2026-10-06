<!-- File: frontend/src/components/ProfileManagerModal.vue -->
<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80" @click="$emit('close')">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl p-6 max-h-[92vh] overflow-auto" @click.stop>
      <div class="flex justify-between mb-4">
        <h3 class="text-lg font-bold text-white">Facebook · Copyright profiles</h3>
        <button @click="$emit('close')" aria-label="Close profiles">✕</button>
      </div>
      <p class="text-xs text-slate-400 mb-4">Only rights owners can run reports. The rights owner name is also the electronic signature; the sender's full name remains separate.</p>
      <form @submit.prevent="save" class="grid grid-cols-2 gap-3">
        <label v-for="field in fields" :key="field.key" class="text-xs text-slate-300">
          {{ field.label }}
          <input v-model="profile[field.key]" :type="field.type || 'text'" :required="field.required !== false"
            :maxlength="field.key === 'country' ? 10 : 255" :list="field.key === 'rights_jurisdiction' ? 'jurisdictions' : undefined"
            class="block w-full mt-1 bg-slate-950 border border-slate-700 rounded-lg p-2" />
        </label>
        <datalist id="jurisdictions"><option v-for="country in jurisdictions" :key="country" :value="country" /></datalist>
        <p v-if="legacyEdit" class="col-span-2 text-xs text-amber-300">Historical role: {{ historicalRole || 'Missing' }}. Saving requires explicit confirmation as the rights owner; opening this form does not change the stored role.</p>
        <label class="col-span-2 flex gap-2 text-xs text-slate-300"><input v-model="ownerConfirmed" type="checkbox" required />I confirm I am the named rights owner (Yes).</label>
        <p class="col-span-2 text-xs text-slate-400">Electronic signature: {{ profile.rights_owner_name || 'Enter rights owner name' }}. Jurisdiction must match Meta's English option, e.g. “Vietnam”. Connect and map this contact email through Microsoft before execution.</p>
        <p v-if="error" role="alert" class="col-span-2 text-xs text-rose-400">{{ error }}</p>
        <div class="col-span-2 flex gap-3 justify-end">
          <button v-if="editingId" type="button" @click="reset" class="text-xs">Cancel edit</button>
          <button :disabled="saving || !ownerConfirmed" class="px-4 py-2 rounded-lg bg-indigo-600 disabled:opacity-40 text-sm">{{ editingId ? 'Save profile' : 'Register profile' }}</button>
        </div>
      </form>
      <div class="mt-5 divide-y divide-slate-800">
        <div v-for="item in proxyStore.profiles" :key="item.id" class="py-3 flex justify-between gap-3 text-xs">
          <div>
            <strong>{{ item.rights_owner_name || item.full_name }}</strong>
            <p class="text-slate-400">Sender: {{ item.sender_name || 'Missing' }} · {{ item.email }}</p>
            <p v-if="!item.submission_eligible" class="text-amber-400">{{ item.submission_block_reason || 'Confirm OWNER and complete names and jurisdiction before reporting.' }}</p>
          </div>
          <div class="flex gap-3">
            <button @click="edit(item)" class="text-indigo-400">Edit</button>
            <button @click="proxyStore.deleteProfile(item.id)" class="text-rose-400">Remove</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, watch } from 'vue';
import { profilesApi } from '../services/api';
import { useProxyStore } from '../stores/proxyStore';
const props = defineProps({ isOpen: Boolean });
defineEmits(['close']);
const proxyStore = useProxyStore();
const blank = () => ({full_name:'', email:'', country:'', organization_name:'', rights_owner_name:'', sender_name:'', rights_jurisdiction:''});
const profile = reactive(blank());
const editingId = ref(null), error = ref(''), saving = ref(false);
const ownerConfirmed = ref(false), legacyEdit = ref(false), historicalRole = ref(null);
const fields = [
  {key:'full_name', label:'Profile display name'}, {key:'rights_owner_name', label:'Rights owner name'},
  {key:'sender_name', label:'Your full name / sender'}, {key:'email', label:'Contact email', type:'email'},
  {key:'country', label:'Profile country (legacy)'}, {key:'rights_jurisdiction', label:'Where are you asserting rights?'},
  {key:'organization_name', label:'Organization (optional)', required:false},
];
const jurisdictions = ['Vietnam','Singapore','Australia','Jordan','Japan','South Korea','United States of America','United Kingdom'];
function reset() { Object.assign(profile, blank()); editingId.value = null; error.value = ''; ownerConfirmed.value = false; legacyEdit.value = false; historicalRole.value = null; }
watch(() => props.isOpen, () => reset());
function edit(item) {
  reset();
  for (const key of Object.keys(profile)) profile[key] = item[key] || '';
  editingId.value = item.id;
  historicalRole.value = item.owner_role;
  legacyEdit.value = !item.submission_eligible;
}
async function save() {
  if (!ownerConfirmed.value) { error.value = 'Explicit rights owner confirmation is required.'; return; }
  saving.value = true; error.value = '';
  try {
    const payload = Object.fromEntries(Object.entries(profile).map(([key,value]) => [key,value.trim()]));
    payload.owner_role = 'OWNER';
    if (editingId.value) await profilesApi.updateProfile(editingId.value, payload);
    else await profilesApi.createProfile(payload);
    await proxyStore.fetchProfiles(); reset();
  } catch (err) { error.value = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Check the required profile fields.'; }
  finally { saving.value = false; }
}
</script>
