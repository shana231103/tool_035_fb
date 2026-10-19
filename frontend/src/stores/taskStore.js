// File: frontend/src/stores/taskStore.js
import {defineStore} from 'pinia';
import {markRaw} from 'vue';
import {tasksApi} from '../services/tasksApi.js';
import {wsService} from '../services/websocket.js';
import {authLifecycle} from '../services/authLifecycle.js';
import {useAuthStore} from './authStore.js';
import {useBrowserStore} from './browserStore.js';
import {createTaskCommands, isDefiniteCommandRejection} from '../services/taskCommands.js';
import {parseTask, parseTaskPage, parseAvailability, parseStartReceipt, parseControl,
  parseTaskEvent, unknownAvailability, startBlockReason, availabilityMessage, safeActionError} from '../services/taskView.js';

export function createTaskStoreOptions(api = tasksApi, socket = wsService, lifecycle = authLifecycle,
  browser = () => useBrowserStore(), identity = () => {
    const auth = useAuthStore();
    return {operatorId: auth.operator?.id, sessionId: auth.sessionContext};
  }, delay = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  const commands = createTaskCommands();
  let refreshPromise = null, refreshAgain = false;
  const current = (store, epoch, channel, generation) => epoch === lifecycle.currentEpoch &&
    (channel === undefined || store.generations[channel] === generation);
  return {
    state: () => ({tasks: [], activeTaskId: null, activeTask: null, historyTasks: [],
      historyOffset: 0, historyHasMore: false, historyLoaded: false, historyLoading: false, historyError: null,
      executionAvailability: unknownAvailability(lifecycle.currentEpoch), isLoading: false, detailLoading: false,
      error: null, actionLoading: false, actionError: null, logs: [], pendingStart: null, pendingControl: null,
      controlWaiting: false, controlMessage: null,
      generations: {latest: 0, history: 0, detail: 0, availability: 0, mutation: 0, control: 0},
      authEpoch: lifecycle.currentEpoch, unsubscribeWs: null}),
    getters: {
      isSlotBusy: state => state.executionAvailability.reason === 'BUSY',
      isSlotReady: state => state.executionAvailability.state === 'ready' && state.executionAvailability.available,
      isRecoveryRequired: state => state.executionAvailability.reason === 'RECOVERY_REQUIRED',
      availabilityText: state => availabilityMessage(state.executionAvailability),
      activeTaskStatus: state => state.activeTask?.status ?? null,
      startDisabledReason: state => state.detailLoading ? 'Đang tải trạng thái tác vụ…' : state.actionLoading ? 'Đang xử lý thao tác…' :
        startBlockReason(state.activeTask, state.executionAvailability, browser(), state.pendingStart),
      canStartActiveTask() {return !this.actionLoading && !this.detailLoading && !this.startDisabledReason;},
      canStopActiveTask: state => !state.activeTask?.legacy_read_only && !state.pendingControl &&
        ((state.activeTask?.status === 'DRAFT' && (!state.pendingStart || state.pendingStart.state === 'RESOLVED')) ||
          (state.activeTask?.is_running === true && !!state.activeTask?.attempt_id)),
      canRetryActiveTask: state => !state.activeTask?.legacy_read_only && state.activeTask?.status === 'FAILED' &&
        state.activeTask?.is_retriable === true,
      totalInfringementsCount: state => state.tasks.reduce((sum, task) => sum + task.targetCount, 0),
      totalSubmittedCount: state => state.tasks.filter(task => task.status === 'SUBMITTED').length,
    },
    actions: {
      async _snapshot(channel, load, apply) {
        const epoch = lifecycle.currentEpoch, generation = ++this.generations[channel];
        const loading = {latest: 'isLoading', history: 'historyLoading', detail: 'detailLoading'}[channel];
        const error = channel === 'history' ? 'historyError' : 'error';
        this[loading] = true; this[error] = null;
        try {
          const result = await load();
          if (!current(this, epoch, channel, generation)) return false;
          apply(result); return true;
        } catch (err) {
          if (current(this, epoch, channel, generation)) this[error] = safeActionError(err);
          return false;
        } finally {if (current(this, epoch, channel, generation)) this[loading] = false;}
      },
      _applyTask(task) {
        if (this.activeTaskId === task.id && (!this.activeTask || task.version >= this.activeTask.version)) this.activeTask = task;
        for (const rows of [this.tasks, this.historyTasks]) {
          const index = rows.findIndex(item => item.id === task.id);
          if (index >= 0 && task.version >= rows[index].version) rows[index] = task;
        }
      },
      fetchTasks() {
        return this._snapshot('latest', async () => parseTaskPage(await api.listTasks({limit: 50, offset: 0})), page => {
          this.tasks = page.items;
          if (!this.activeTaskId && page.items.length) void this.selectTask(page.items[0].id);
        });
      },
      fetchHistory(offset = 0) {
        return this._snapshot('history', async () => parseTaskPage(await api.listTasks({limit: 50, offset})), page => {
          const rows = offset === 0 ? page.items : [...this.historyTasks, ...page.items];
          this.historyTasks = [...new Map(rows.map(item => [item.id, item])).values()];
          this.historyOffset = page.offset + page.items.length;
          this.historyHasMore = page.has_more; this.historyLoaded = true;
        });
      },
      async selectTask(taskId) {
        if (this.activeTaskId !== taskId) {this.activeTaskId = taskId; this.activeTask = null;}
        return Promise.all([this.refreshActiveTask(taskId), browser().refresh(taskId)]);
      },
      refreshActiveTask(taskId = this.activeTaskId) {
        if (!taskId || taskId !== this.activeTaskId) return Promise.resolve(false);
        return this._snapshot('detail', async () => parseTask(await api.getTask(taskId)), task => this._applyTask(task));
      },
      async checkExecutionStatus() {
        const epoch = lifecycle.currentEpoch, generation = ++this.generations.availability;
        this.executionAvailability = {...unknownAvailability(epoch), state: 'loading'};
        try {
          const view = parseAvailability(await api.getExecutionStatus(), epoch);
          if (!current(this, epoch, 'availability', generation)) return null;
          this.executionAvailability = view; return view;
        } catch {
          if (current(this, epoch, 'availability', generation)) this.executionAvailability = {...unknownAvailability(epoch), state: 'error'};
          return null;
        }
      },
      async _mutation(work) {
        if (this.actionLoading) return null;
        const epoch = lifecycle.currentEpoch, generation = ++this.generations.mutation;
        this.actionLoading = true; this.actionError = null;
        const valid = () => current(this, epoch, 'mutation', generation);
        try {return await work(epoch, valid);} catch (err) {
          if (valid()) this.actionError = safeActionError(err);
          return null;
        } finally {if (valid()) this.actionLoading = false;}
      },
      createTask(form) {
        return this._mutation(async (_, valid) => {
          const task = parseTask(await api.createTask(form));
          if (!valid()) return null;
          ++this.generations.detail;
          this.tasks = [task, ...this.tasks.filter(item => item.id !== task.id)].slice(0, 50);
          this.activeTaskId = task.id; this.activeTask = task;
          await Promise.all([this.checkExecutionStatus(), browser().refresh(task.id)]);
          return valid() ? task : null;
        });
      },
      startTask(taskId, expectedVersion) {
        if (this.actionLoading || taskId !== this.activeTaskId || !this.canStartActiveTask) return Promise.resolve(null);
        const intent = commands.beginStart({...identity(), authEpoch: lifecycle.currentEpoch, taskId,
          expectedVersion: expectedVersion ?? this.activeTask.version});
        this.pendingStart = markRaw(intent);
        return this._sendStart(intent);
      },
      _sendStart(intent) {
        return this._mutation(async (_, valid) => {
          const previouslyUnknown = intent.state === 'UNKNOWN';
          intent.state = 'PENDING';
          try {
            const receipt = parseStartReceipt(await api.startTask(intent.taskId, intent.payload), intent);
            if (!valid()) return null;
            if (!commands.resolveStart(intent, receipt)) {intent.receipt = receipt; commands.markUnknown(intent);}
            await this.resyncVisibleState(); return receipt;
          } catch (err) {
            if (valid()) {
              if (!previouslyUnknown && isDefiniteCommandRejection(err)) {
                commands.rejectStart(intent); this.pendingStart = null;
              } else commands.markUnknown(intent);
              await this.resyncVisibleState();
            }
            throw err;
          }
        });
      },
      async checkStartResult(taskId = this.pendingStart?.taskId) {
        const intent = commands.currentStart(taskId, lifecycle.currentEpoch), epoch = lifecycle.currentEpoch;
        if (!intent || intent.state === 'PENDING') return null;
        try {
          const receipt = parseStartReceipt(await api.getStartReceipt(taskId, intent.commandId), intent);
          if (!current(this, epoch) || commands.currentStart(taskId, epoch) !== intent) return null;
          if (!commands.resolveStart(intent, receipt)) {intent.receipt = receipt; commands.markUnknown(intent);}
          this.actionError = null; await this.resyncVisibleState(); return receipt;
        } catch (err) {
          if (current(this, epoch)) this.actionError = safeActionError(err);
          // A 404 cannot prove that an unsettled admission writer was absent.
          return null;
        }
      },
      retryPendingStart(taskId) {
        const intent = commands.currentStart(taskId, lifecycle.currentEpoch), context = identity();
        if (!intent || intent.state !== 'UNKNOWN' || intent.receipt?.authority_contract_version === 1 ||
            intent.operatorId !== context.operatorId || intent.sessionId !== context.sessionId) return Promise.resolve(null);
        return this._sendStart(intent);
      },
      stopTask(taskId) {
        if (this.actionLoading || taskId !== this.activeTaskId || !this.canStopActiveTask) return Promise.resolve(null);
        const task = this.activeTask, commandId = crypto.randomUUID();
        const pending = {taskId, commandId, status: 'UNKNOWN', payload: Object.freeze({command_id: commandId,
          expected_version: task.version, attempt_id: task.attempt_id ?? null})};
        this.pendingControl = pending;
        return this._mutation(async (_, valid) => {
          try {
            const receipt = parseControl(await api.stopTask(taskId, pending.payload), commandId);
            if (!valid()) return null;
            this.pendingControl = {...pending, ...receipt};
            await this.checkControlResult(); await this.resyncVisibleState(); return receipt;
          } catch (err) {
            if (valid()) {
              if (isDefiniteCommandRejection(err)) {
                this.pendingControl = null; this.controlMessage = null;
                await this.resyncVisibleState();
              } else this.controlMessage = 'Chưa xác định kết quả — kiểm tra lại.';
            }
            throw err;
          }
        });
      },
      async checkControlResult() {
        if (!this.pendingControl || this.controlWaiting) return null;
        const pending = this.pendingControl, epoch = lifecycle.currentEpoch, generation = ++this.generations.control;
        this.controlWaiting = true;
        let elapsed = 0, index = 0;
        const started = Date.now();
        try {
          while (elapsed < 30000 && current(this, epoch, 'control', generation)) {
            const remaining = 30000 - Math.max(elapsed, Date.now() - started);
            if (remaining <= 0) break;
            const receipt = parseControl(await api.getControlStatus(pending.commandId, {timeout: Math.min(remaining, 5000)}), pending.commandId);
            if (!current(this, epoch, 'control', generation)) return null;
            this.pendingControl = {...pending, ...receipt};
            if (receipt.status !== 'ADMITTED') {
              this.controlMessage = receipt.status === 'COMPLETE' ? 'Đã hoàn tất lệnh dừng và dọn dẹp.' : 'Cần phục hồi tài nguyên.';
              if (receipt.status === 'COMPLETE') this.pendingControl = null;
              await this.resyncVisibleState(); return receipt;
            }
            const wait = Math.min([1000, 2000, 5000][Math.min(index++, 2)],
              30000 - Math.max(elapsed, Date.now() - started));
            if (wait <= 0) break;
            await delay(wait); elapsed += wait;
          }
          if (current(this, epoch, 'control', generation)) this.controlMessage = 'Chưa xác định kết quả — kiểm tra lại.';
        } catch {
          if (current(this, epoch, 'control', generation)) this.controlMessage = 'Chưa xác định kết quả — kiểm tra lại.';
        } finally {if (current(this, epoch, 'control', generation)) this.controlWaiting = false;}
        return null;
      },
      retryTask(taskId, expectedVersion) {
        if (taskId !== this.activeTaskId || !this.canRetryActiveTask) return Promise.resolve(null);
        return this._mutation(async (_, valid) => {
          try {
            const task = parseTask(await api.retryTask(taskId, {expected_version: expectedVersion ?? this.activeTask.version}));
            if (!valid()) return null;
            this._applyTask(task); await this.resyncVisibleState(); return task;
          } catch (err) {if (valid()) await this.resyncVisibleState(); throw err;}
        });
      },
      async resyncVisibleState() {
        const work = [this.fetchTasks(), this.checkExecutionStatus(), browser().refresh(this.activeTaskId)];
        if (this.activeTaskId) work.push(this.refreshActiveTask());
        if (this.historyLoaded) {
          // Refresh every currently visible page using GET; retain offset pagination semantics.
          const count = Math.max(this.historyOffset, 50), epoch = lifecycle.currentEpoch;
          work.push(this._snapshot('history', async () => {
            const pages = await Promise.all(Array.from({length: Math.ceil(count / 50)}, (_, page) =>
              api.listTasks({limit: 50, offset: page * 50}).then(parseTaskPage)));
            return pages;
          }, pages => {
            if (!current(this, epoch)) return;
            this.historyTasks = pages.flatMap(page => page.items);
            const last = pages.at(-1); this.historyOffset = last.offset + last.items.length; this.historyHasMore = last.has_more;
          }));
        }
        return Promise.all(work);
      },
      receiveEvent(raw) {
        if (raw?.type === 'RECONNECTED') {
          void this.resyncVisibleState();
          if (this.pendingStart?.state === 'UNKNOWN') void this.checkStartResult();
          if (this.pendingControl) void this.checkControlResult();
          return;
        }
        const event = parseTaskEvent(raw);
        if (!event) return;
        const snapshots = [this.activeTask, ...this.tasks, ...this.historyTasks].filter(task => task?.id === event.taskId);
        if (!snapshots.length || snapshots.every(task => task.version >= event.version)) return;
        // Invalidate in-flight reads before coalescing GETs; never apply an incomplete WS DTO.
        for (const channel of ['latest', 'history', 'detail', 'availability']) ++this.generations[channel];
        refreshAgain = true;
        if (refreshPromise) return;
        const epoch = lifecycle.currentEpoch;
        const scheduled = Promise.resolve().then(async () => {
          while (refreshAgain && current(this, epoch)) {refreshAgain = false; await this.resyncVisibleState();}
        }).finally(() => {if (refreshPromise === scheduled) refreshPromise = null;});
        refreshPromise = scheduled;
      },
      initWebSocketListener() {
        if (!this.unsubscribeWs) this.unsubscribeWs = socket.subscribe(event => this.receiveEvent(event));
      },
      resetForAuth(epoch) {
        commands.reset(); refreshAgain = false; refreshPromise = null;
        for (const key of Object.keys(this.generations)) ++this.generations[key];
        this.tasks = []; this.activeTaskId = null; this.activeTask = null; this.historyTasks = [];
        this.historyOffset = 0; this.historyHasMore = false; this.historyLoaded = false;
        this.historyLoading = false; this.historyError = null; this.isLoading = false; this.detailLoading = false;
        this.error = null; this.actionLoading = false; this.actionError = null; this.logs = [];
        this.pendingStart = null; this.pendingControl = null; this.controlWaiting = false; this.controlMessage = null;
        this.executionAvailability = unknownAvailability(epoch); this.authEpoch = epoch;
      },
      stop() {this.unsubscribeWs?.(); this.unsubscribeWs = null; ++this.generations.control; this.controlWaiting = false;},
    },
  };
}

export const useTaskStore = defineStore('task', createTaskStoreOptions());
authLifecycle.registerStoreHook({
  resetForAuth(epoch) {try {useTaskStore().resetForAuth(epoch);} catch {}},
  stop() {try {useTaskStore().stop();} catch {}},
});
