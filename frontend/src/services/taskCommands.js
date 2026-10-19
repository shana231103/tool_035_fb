// File: frontend/src/services/taskCommands.js
// One intent per store/session; no durable client replay queue.
export function createTaskCommands(uuid = () => crypto.randomUUID()) {
  let pending = null;
  return {
    beginStart(context) {
      if (pending && pending.state !== 'RESOLVED') throw new Error('Chưa xác định kết quả lệnh bắt đầu.');
      const commandId = uuid();
      pending = {context: Object.freeze({...context}), ...context, commandId,
        payload: Object.freeze({command_id: commandId, expected_version: context.expectedVersion}),
        state: 'PENDING', receipt: null};
      return pending;
    },
    resolveStart(intent, receipt) {
      if (pending !== intent || receipt.authority_contract_version !== 2) return false;
      intent.receipt = receipt;
      intent.state = 'RESOLVED';
      return true;
    },
    markUnknown(intent) {if (pending === intent) intent.state = 'UNKNOWN';},
    rejectStart(intent) {if (pending === intent) {intent.state = 'REJECTED'; pending = null;}},
    currentStart(taskId, authEpoch) {
      return pending?.taskId === taskId && pending.authEpoch === authEpoch ? pending : null;
    },
    reset() {pending = null;},
  };
}

export function isDefiniteCommandRejection(error) {
  const status = error?.response?.status;
  const code = error?.response?.data?.safe_code || error?.response?.data?.detail?.code;
  return [400, 401, 403, 404, 409, 422].includes(status) &&
    !['START_OUTCOME_UNKNOWN', 'CONTROL_OUTCOME_UNKNOWN', 'RECEIPT_OUTCOME_UNKNOWN'].includes(code);
}
