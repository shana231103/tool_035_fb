// File: frontend/src/main.js
import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router/index.js";
import { authLifecycle } from "./services/authLifecycle.js";
import { useTaskStore } from "./stores/taskStore.js";
import { useProxyStore } from "./stores/proxyStore.js";
import { useMailboxStore } from "./stores/mailboxStore.js";
import { useBrowserStore } from "./stores/browserStore.js";
import "./style.css";

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.use(router);

authLifecycle.registerStoreHook({
  resetForAuth: (epoch) => useTaskStore().resetForAuth(epoch),
  stop: () => useTaskStore().stop(),
});
authLifecycle.registerStoreHook({
  resetForAuth: (epoch) => useProxyStore().resetForAuth(epoch),
});
authLifecycle.registerStoreHook({
  resetForAuth: (epoch) => useMailboxStore().resetForAuth(epoch),
});
authLifecycle.registerStoreHook({
  resetForAuth: (epoch) => useBrowserStore().resetForAuth(epoch),
  stop: () => useBrowserStore().stop(),
});

app.mount("#app");
