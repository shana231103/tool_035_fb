// File: frontend/src/main.js
import { createPinia } from "pinia";
import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import "./style.css";
import DashboardView from "./views/DashboardView.vue";
import JobsView from "./views/JobsView.vue";

const routes = [
  { path: "/", name: "Dashboard", component: DashboardView },
  { path: "/jobs", name: "Jobs", component: JobsView },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.use(router);
app.mount("#app");
