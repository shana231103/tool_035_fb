<!-- File: frontend/src/App.vue -->
<template>
  <div class="min-h-screen bg-slate-950 flex flex-col font-sans">
    <!-- Top Navigation Header -->
    <header class="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-40">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <!-- Logo & Branding -->
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <div>
            <h1 class="font-extrabold text-white text-base leading-none tracking-tight">Meta Copyright Reporter</h1>
            <span class="text-[10px] text-indigo-400 font-semibold uppercase tracking-wider">Automated DMCA Enforcement</span>
          </div>
        </div>

        <!-- Navigation Links & Modal Triggers -->
        <nav class="flex items-center gap-2">
          <router-link
            to="/"
            active-class="bg-indigo-600/10 text-indigo-400 border-indigo-500/30"
            class="px-3 py-1.5 rounded-xl border border-transparent text-xs font-semibold text-slate-300 hover:text-white transition"
          >
            Dashboard
          </router-link>
          <router-link
            to="/jobs"
            active-class="bg-indigo-600/10 text-indigo-400 border-indigo-500/30"
            class="px-3 py-1.5 rounded-xl border border-transparent text-xs font-semibold text-slate-300 hover:text-white transition"
          >
            History & Archive
          </router-link>

          <div class="h-4 w-px bg-slate-800 mx-2"></div>

          <button
            @click="isProxyModalOpen = true"
            class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold text-slate-300 hover:text-white hover:border-slate-700 transition flex items-center gap-1.5"
          >
            <span>🌐</span>
            <span>Proxies</span>
            <span v-if="proxyStore.proxies.length > 0" class="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] text-slate-400">
              {{ proxyStore.proxies.length }}
            </span>
          </button>

          <button
            @click="isProfileModalOpen = true"
            class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold text-slate-300 hover:text-white hover:border-slate-700 transition flex items-center gap-1.5"
          >
            <span>👤</span>
            <span>Profiles</span>
          </button>
          <button @click="isMailboxModalOpen = true" class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold text-slate-300 hover:text-white">
            Microsoft mailbox
          </button>
        </nav>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <router-view />
    </main>

    <!-- Modals -->
    <ProxyManagerModal :isOpen="isProxyModalOpen" @close="isProxyModalOpen = false" />
    <ProfileManagerModal :isOpen="isProfileModalOpen" @close="isProfileModalOpen = false" />
    <MicrosoftMailboxModal :isOpen="isMailboxModalOpen" @close="isMailboxModalOpen = false" />
  </div>
</template>

<script setup>
import { ref } from "vue";
import ProfileManagerModal from "./components/ProfileManagerModal.vue";
import ProxyManagerModal from "./components/ProxyManagerModal.vue";
import MicrosoftMailboxModal from "./components/MicrosoftMailboxModal.vue";
import { useProxyStore } from "./stores/proxyStore";

const proxyStore = useProxyStore();
const isProxyModalOpen = ref(false);
const isProfileModalOpen = ref(false);
const isMailboxModalOpen = ref(false);
</script>
