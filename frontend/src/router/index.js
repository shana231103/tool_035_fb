// File: frontend/src/router/index.js
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/authStore.js";
import { authLifecycle } from "../services/authLifecycle.js";
import DashboardView from "../views/DashboardView.vue";
import TaskHistoryView from "../views/TaskHistoryView.vue";
import LoginView from "../views/LoginView.vue";

const routes = [
  {
    path: "/login",
    name: "Login",
    component: LoginView,
    meta: { requiresAuth: false, guestOnly: true },
  },
  {
    path: "/",
    name: "Dashboard",
    component: DashboardView,
    meta: { requiresAuth: true },
  },
  {
    path: "/tasks",
    name: "Tasks",
    component: TaskHistoryView,
    meta: { requiresAuth: true },
  },
  {
    path: "/jobs",
    redirect: "/tasks",
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/",
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

authLifecycle.setRouter(router);

let bootstrapPromise = null;

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore();

  if (authStore.status === "unknown") {
    if (!bootstrapPromise) {
      bootstrapPromise = authLifecycle.bootstrap();
    }
    await bootstrapPromise;
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ path: "/login" });
  } else if (to.meta.guestOnly && authStore.isAuthenticated) {
    next({ path: "/" });
  } else {
    next();
  }
});
