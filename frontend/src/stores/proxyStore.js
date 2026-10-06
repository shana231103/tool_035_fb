// File: frontend/src/stores/proxyStore.js
import { defineStore } from "pinia";
import { profilesApi, proxiesApi } from "../services/api";

export const useProxyStore = defineStore("proxies", {
  state: () => ({
    proxies: [],
    profiles: [],
    isLoading: false,
    testingProxyId: null,
    error: null,
  }),

  getters: {
    activeProxiesCount: (state) =>
      state.proxies.filter((p) => p.status === "ACTIVE").length,
    proxiesByCountry: (state) => (country) =>
      state.proxies.filter((p) => p.country === country),
  },

  actions: {
    async fetchProxies() {
      try {
        this.proxies = await proxiesApi.listProxies();
      } catch (err) {
        this.error = err.response?.data?.detail || err.message;
      }
    },

    async addProxy(payload) {
      this.isLoading = true;
      try {
        const created = await proxiesApi.addProxy(payload);
        this.proxies.push(created);
        return created;
      } catch (err) {
        this.error = err.response?.data?.detail || err.message;
        throw err;
      } finally {
        this.isLoading = false;
      }
    },

    async testProxy(proxyId) {
      this.testingProxyId = proxyId;
      try {
        const result = await proxiesApi.testProxy(proxyId);
        const target = this.proxies.find((p) => p.id === proxyId);
        if (target) {
          target.status = result.status;
          target.latency_ms = result.latency_ms;
        }
        return result;
      } catch (err) {
        this.error = err.response?.data?.detail || err.message;
        throw err;
      } finally {
        this.testingProxyId = null;
      }
    },

    async deleteProxy(proxyId) {
      try {
        await proxiesApi.deleteProxy(proxyId);
        this.proxies = this.proxies.filter((p) => p.id !== proxyId);
      } catch (err) {
        this.error = err.response?.data?.detail || err.message;
      }
    },

    async fetchProfiles() {
      try {
        this.profiles = await profilesApi.listProfiles();
      } catch (err) {
        this.error = err.response?.data?.detail || err.message;
      }
    },

    async addProfile(payload) {
      this.isLoading = true;
      try {
        const created = await profilesApi.createProfile(payload);
        this.profiles.push(created);
        return created;
      } catch (err) {
        this.error = err.response?.data?.detail || err.message;
        throw err;
      } finally {
        this.isLoading = false;
      }
    },

    async deleteProfile(profileId) {
      try {
        await profilesApi.deleteProfile(profileId);
        this.profiles = this.profiles.filter((p) => p.id !== profileId);
      } catch (err) {
        this.error = err.response?.data?.detail || err.message;
      }
    },
  },
});
