<!-- File: frontend/src/components/LogStreamViewer.vue -->
<template>
  <div class="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col h-72 font-mono text-xs">
    <div class="bg-slate-900/90 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
        <span class="font-sans font-bold text-slate-200 text-xs">Live Worker Event Stream</span>
      </div>
      <button @click="jobStore.logs = []" class="text-slate-500 hover:text-slate-300 font-sans text-xs">
        Clear
      </button>
    </div>

    <div class="flex-1 p-4 overflow-y-auto space-y-1.5 scrollbar-thin">
      <div v-if="jobStore.logs.length === 0" class="text-slate-600 italic">
        Awaiting task submissions and automation events...
      </div>
      <div
        v-for="log in jobStore.logs"
        :key="log.id"
        class="leading-relaxed flex items-start gap-2 text-slate-300"
      >
        <span class="text-slate-500 shrink-0">[{{ log.timestamp }}]</span>
        <span :class="getLogColor(log.text)">{{ log.text }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useJobStore } from "../stores/jobStore";

const jobStore = useJobStore();

const getLogColor = (text) => {
  if (text.includes("SUBMITTED") || text.includes("Case")) return "text-emerald-400 font-semibold";
  if (text.includes("RUNNING") || text.includes("START")) return "text-sky-400";
  if (text.includes("FAILED") || text.includes("Error")) return "text-rose-400 font-semibold";
  return "text-slate-300";
};
</script>
