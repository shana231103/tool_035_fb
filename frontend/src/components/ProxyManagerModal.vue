<!-- File: frontend/src/components/ProxyManagerModal.vue -->
<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm" @click="$emit('close')">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl overflow-hidden p-6 shadow-2xl space-y-6" @click.stop>
      <div class="flex items-center justify-between pb-4 border-b border-slate-800">
        <div>
          <h3 class="text-lg font-bold text-white flex items-center gap-2">
            Geo-Targeted Proxy Routing Pool
          </h3>
          <p class="text-xs text-slate-400 mt-1">
            Meta IP Form requires residential proxies from SG, AU, JP, KR, or JO.
          </p>
        </div>
        <button @click="$emit('close')" class="text-slate-400 hover:text-white text-lg">✕</button>
      </div>

      <!-- Add Proxy Form -->
      <form @submit.prevent="handleAddProxy" class="grid grid-cols-1 sm:grid-cols-4 gap-3 bg-slate-950 p-4 rounded-xl border border-slate-800">
        <div class="sm:col-span-2">
          <label class="block text-[11px] font-semibold uppercase text-slate-400 mb-1">Host / IP *</label>
          <input
            v-model="newProxy.host"
            type="text"
            required
            placeholder="123.45.67.89"
            class="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label class="block text-[11px] font-semibold uppercase text-slate-400 mb-1">Port *</label>
          <input
            v-model.number="newProxy.port"
            type="number"
            required
            placeholder="8080"
            class="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label class="block text-[11px] font-semibold uppercase text-slate-400 mb-1">Country *</label>
          <select
            v-model="newProxy.country"
            required
            class="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="SG">Singapore (SG)</option>
            <option value="AU">Australia (AU)</option>
            <option value="JP">Japan (JP)</option>
            <option value="KR">South Korea (KR)</option>
            <option value="JO">Jordan (JO)</option>
          </select>
        </div>
        <div class="sm:col-span-4 flex justify-end">
          <button
            type="submit"
            :disabled="proxyStore.isLoading"
            class="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md transition"
          >
            Add Proxy Server
          </button>
        </div>
      </form>

      <!-- Proxy List Table -->
      <div class="max-h-72 overflow-y-auto border border-slate-800 rounded-xl">
        <table class="w-full text-left text-xs font-mono">
          <thead class="bg-slate-950 text-slate-400 sticky top-0 border-b border-slate-800 font-sans">
            <tr>
              <th class="py-2.5 px-3">Country</th>
              <th class="py-2.5 px-3">Address</th>
              <th class="py-2.5 px-3">Status</th>
              <th class="py-2.5 px-3">Latency</th>
              <th class="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800">
            <tr v-if="proxyStore.proxies.length === 0">
              <td colspan="5" class="py-6 text-center text-slate-500 font-sans">No proxies registered. Add one above.</td>
            </tr>
            <tr v-for="proxy in proxyStore.proxies" :key="proxy.id" class="hover:bg-slate-800/40">
              <td class="py-2.5 px-3 font-sans font-bold text-slate-200">{{ proxy.country }}</td>
              <td class="py-2.5 px-3 text-slate-300">{{ proxy.protocol }}://{{ proxy.host }}:{{ proxy.port }}</td>
              <td class="py-2.5 px-3">
                <span :class="proxy.status === 'ACTIVE' ? 'text-emerald-400' : 'text-amber-400'" class="font-sans font-semibold">
                  {{ proxy.status }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-slate-400 font-sans">{{ proxy.latency_ms > 0 ? `${proxy.latency_ms}ms` : '—' }}</td>
              <td class="py-2.5 px-3 text-right font-sans space-x-2">
                <button
                  @click="proxyStore.testProxy(proxy.id)"
                  :disabled="proxyStore.testingProxyId === proxy.id"
                  class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] transition"
                >
                  {{ proxyStore.testingProxyId === proxy.id ? "Testing..." : "Test Latency" }}
                </button>
                <button
                  @click="proxyStore.deleteProxy(proxy.id)"
                  class="px-2 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-[11px] transition"
                >
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive } from "vue";
import { useProxyStore } from "../stores/proxyStore";

defineProps({
  isOpen: Boolean,
});

defineEmits(["close"]);

const proxyStore = useProxyStore();

const newProxy = reactive({
  host: "",
  port: 8080,
  country: "SG",
  protocol: "http",
  username: "",
  password: "",
});

const handleAddProxy = async () => {
  if (!newProxy.host) return;
  await proxyStore.addProxy({ ...newProxy });
  newProxy.host = "";
  newProxy.port = 8080;
};
</script>
