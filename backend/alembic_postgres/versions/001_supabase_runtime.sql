CREATE TABLE browser_runtime_bindings (
	singleton_id INTEGER NOT NULL, 
	installation_id VARCHAR(36) NOT NULL, 
	provider_binding_id VARCHAR(36) NOT NULL, 
	host_binding_digest VARCHAR(128) NOT NULL, 
	schema_version INTEGER NOT NULL, 
	PRIMARY KEY (singleton_id), 
	CONSTRAINT ck_browser_singleton CHECK (singleton_id = 1)
);

ALTER TABLE browser_runtime_bindings ENABLE ROW LEVEL SECURITY;

CREATE TABLE legacy_task_metadata (
	id VARCHAR(36) NOT NULL, 
	source_revision VARCHAR(50) NOT NULL, 
	raw_task_id VARCHAR(36), 
	raw_batch_job_id VARCHAR(36), 
	raw_profile_id VARCHAR(36), 
	raw_proxy_id VARCHAR(36), 
	raw_status VARCHAR(50), 
	raw_targets TEXT, 
	raw_evidence TEXT, 
	pre_conversion_digest VARCHAR(64), 
	disposition VARCHAR(50) NOT NULL, 
	provenance TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_legacy_task_metadata_raw_task_id ON legacy_task_metadata (raw_task_id);

ALTER TABLE legacy_task_metadata ENABLE ROW LEVEL SECURITY;

CREATE TABLE operator_accounts (
	id VARCHAR(36) NOT NULL, 
	username_key VARCHAR(64), 
	username_display VARCHAR(64), 
	password_hash VARCHAR(255), 
	status VARCHAR(20) NOT NULL, 
	auth_version INTEGER NOT NULL, 
	run_version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_operator_accounts_username_key ON operator_accounts (username_key);

ALTER TABLE operator_accounts ENABLE ROW LEVEL SECURITY;

CREATE TABLE operator_artifacts (
	id VARCHAR(36) NOT NULL, 
	operator_account_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	task_id VARCHAR(36), 
	kind VARCHAR(20) NOT NULL, 
	storage_key VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id)
);

CREATE INDEX ix_operator_artifacts_job_id ON operator_artifacts (job_id);

CREATE INDEX ix_operator_artifacts_operator_account_id ON operator_artifacts (operator_account_id);

CREATE INDEX ix_operator_artifacts_scope ON operator_artifacts (operator_account_id, job_id);

CREATE UNIQUE INDEX ix_operator_artifacts_storage_key ON operator_artifacts (storage_key);

CREATE INDEX ix_operator_artifacts_task_id ON operator_artifacts (task_id);

ALTER TABLE operator_artifacts ENABLE ROW LEVEL SECURITY;

CREATE TABLE operator_sessions (
	id VARCHAR(36) NOT NULL, 
	secret_digest BYTEA NOT NULL, 
	operator_id VARCHAR(36) NOT NULL, 
	auth_version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	last_seen_at TIMESTAMP WITH TIME ZONE, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	idle_expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(operator_id) REFERENCES operator_accounts (id)
);

CREATE INDEX ix_operator_sessions_expires_at ON operator_sessions (expires_at);

CREATE INDEX ix_operator_sessions_operator_id ON operator_sessions (operator_id);

CREATE UNIQUE INDEX ix_operator_sessions_secret_digest ON operator_sessions (secret_digest);

ALTER TABLE operator_sessions ENABLE ROW LEVEL SECURITY;

CREATE TABLE owner_profiles (
	id VARCHAR(36) NOT NULL, 
	operator_account_id VARCHAR(36) NOT NULL, 
	full_name VARCHAR(255) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	country VARCHAR(10) NOT NULL, 
	organization_name VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE, 
	rights_owner_name VARCHAR(255), 
	sender_name VARCHAR(255), 
	rights_jurisdiction VARCHAR(255), 
	owner_role VARCHAR(255), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_owner_profiles_owner UNIQUE (id, operator_account_id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id)
);

CREATE INDEX ix_owner_profiles_operator_account_id ON owner_profiles (operator_account_id);

ALTER TABLE owner_profiles ENABLE ROW LEVEL SECURITY;

CREATE TABLE proxies (
	id VARCHAR(36) NOT NULL, 
	operator_account_id VARCHAR(36) NOT NULL, 
	protocol VARCHAR(10), 
	host VARCHAR(255) NOT NULL, 
	port INTEGER NOT NULL, 
	country VARCHAR(10) NOT NULL, 
	username VARCHAR(255), 
	password VARCHAR(255), 
	status VARCHAR(20), 
	latency_ms INTEGER, 
	consecutive_failures INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE, 
	last_checked_at TIMESTAMP WITH TIME ZONE, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_proxies_owner UNIQUE (id, operator_account_id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id)
);

CREATE INDEX ix_proxies_operator_account_id ON proxies (operator_account_id);

ALTER TABLE proxies ENABLE ROW LEVEL SECURITY;

CREATE TABLE proxy_owner_refs (
	proxy_id VARCHAR(36) NOT NULL, 
	operator_account_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (proxy_id, operator_account_id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id)
);

CREATE INDEX ix_proxy_owner_refs_operator_account_id ON proxy_owner_refs (operator_account_id);

ALTER TABLE proxy_owner_refs ENABLE ROW LEVEL SECURITY;

CREATE TABLE task_control_receipts (
	operator_account_id VARCHAR(36) NOT NULL, 
	command_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(50) NOT NULL, 
	target_id TEXT NOT NULL, 
	target_generation INTEGER NOT NULL, 
	initiating_session_id VARCHAR(36) NOT NULL, 
	auth_version INTEGER NOT NULL, 
	admitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	result_code VARCHAR(50) NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (operator_account_id, command_id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id)
);

ALTER TABLE task_control_receipts ENABLE ROW LEVEL SECURITY;

CREATE TABLE batch_jobs (
	id VARCHAR(36) NOT NULL, 
	operator_account_id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	owner_profile_id VARCHAR(36) NOT NULL, 
	preferred_country VARCHAR(10), 
	concurrency INTEGER, 
	delay_min INTEGER, 
	delay_max INTEGER, 
	status VARCHAR(20), 
	execution_run_version INTEGER NOT NULL, 
	pause_reason VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_batch_jobs_owner UNIQUE (id, operator_account_id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id), 
	FOREIGN KEY(owner_profile_id) REFERENCES owner_profiles (id)
);

CREATE INDEX ix_batch_jobs_operator_account_id ON batch_jobs (operator_account_id);

ALTER TABLE batch_jobs ENABLE ROW LEVEL SECURITY;

CREATE TABLE report_tasks (
	id VARCHAR(36) NOT NULL, 
	operator_account_id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	owner_profile_id VARCHAR(36), 
	preferred_country VARCHAR(10), 
	target_urls_json TEXT NOT NULL, 
	version INTEGER NOT NULL, 
	run_version INTEGER, 
	last_start_command_id VARCHAR(36), 
	legacy_read_only BOOLEAN NOT NULL, 
	display_summary TEXT, 
	legacy_batch_job_id VARCHAR(36), 
	batch_job_id VARCHAR(36), 
	target_url TEXT, 
	target_platform VARCHAR(50), 
	target_content_type VARCHAR(50), 
	original_url TEXT NOT NULL, 
	explanation TEXT NOT NULL, 
	status VARCHAR(50), 
	retry_count INTEGER, 
	max_retries INTEGER, 
	proxy_id VARCHAR(36), 
	meta_case_number VARCHAR(100), 
	screenshot_path VARCHAR(500), 
	error_message TEXT, 
	infringing_account VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	attempt_id VARCHAR(36), 
	input_snapshot JSON, 
	verification JSON, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	receipt_text TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_report_tasks_owner UNIQUE (id, operator_account_id), 
	CONSTRAINT fk_report_tasks_profile_owner FOREIGN KEY(owner_profile_id, operator_account_id) REFERENCES owner_profiles (id, operator_account_id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id), 
	FOREIGN KEY(legacy_batch_job_id) REFERENCES batch_jobs (id), 
	FOREIGN KEY(batch_job_id) REFERENCES batch_jobs (id)
);

CREATE INDEX ix_report_tasks_infringing_account ON report_tasks (infringing_account);

CREATE INDEX ix_report_tasks_operator_account_id ON report_tasks (operator_account_id);

CREATE INDEX ix_report_tasks_operator_created ON report_tasks (operator_account_id, created_at, id);

CREATE INDEX ix_report_tasks_operator_status ON report_tasks (operator_account_id, status, updated_at);

ALTER TABLE report_tasks ENABLE ROW LEVEL SECURITY;

CREATE TABLE browser_session_leases (
	operation_id VARCHAR(36) NOT NULL, 
	installation_id VARCHAR(36) NOT NULL, 
	provider_binding_id VARCHAR(36) NOT NULL, 
	task_id VARCHAR(36) NOT NULL, 
	attempt_id VARCHAR(36) NOT NULL, 
	marker_nonce VARCHAR(128) NOT NULL, 
	profile_id VARCHAR(128), 
	phase VARCHAR(32) NOT NULL, 
	cleanup_state VARCHAR(32) NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	next_retry_at TIMESTAMP WITH TIME ZONE, 
	retries INTEGER NOT NULL, 
	safe_reason VARCHAR(64), 
	charged BOOLEAN NOT NULL, 
	completion_evidence VARCHAR(32) NOT NULL, 
	audit_reference VARCHAR(128), 
	PRIMARY KEY (operation_id), 
	CONSTRAINT uq_browser_attempt UNIQUE (installation_id, task_id, attempt_id), 
	CONSTRAINT uq_browser_profile UNIQUE (provider_binding_id, profile_id), 
	CONSTRAINT ck_browser_counters CHECK (version >= 0 AND retries >= 0), 
	CONSTRAINT ck_browser_charge CHECK ((phase = 'CLOSED' AND charged = false AND cleanup_state = 'CONFIRMED' AND completion_evidence <> 'UNKNOWN') OR (phase <> 'CLOSED' AND charged = true)), 
	FOREIGN KEY(task_id) REFERENCES report_tasks (id) ON DELETE RESTRICT
);

CREATE INDEX ix_browser_installation_charge ON browser_session_leases (installation_id, charged, updated_at);

CREATE INDEX ix_browser_task_charge ON browser_session_leases (installation_id, task_id, charged);

ALTER TABLE browser_session_leases ENABLE ROW LEVEL SECURITY;

CREATE TABLE task_artifact_links (
	artifact_id VARCHAR(36) NOT NULL, 
	task_id VARCHAR(36) NOT NULL, 
	operator_account_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (artifact_id, task_id), 
	CONSTRAINT fk_task_artifact_links_task FOREIGN KEY(task_id, operator_account_id) REFERENCES report_tasks (id, operator_account_id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id)
);

CREATE INDEX ix_task_artifact_links_lookup ON task_artifact_links (task_id, operator_account_id);

CREATE INDEX ix_task_artifact_links_operator_account_id ON task_artifact_links (operator_account_id);

ALTER TABLE task_artifact_links ENABLE ROW LEVEL SECURITY;

CREATE TABLE task_execution_slot (
	singleton_id INTEGER NOT NULL, 
	generation INTEGER NOT NULL, 
	phase VARCHAR(30) NOT NULL, 
	task_id VARCHAR(36), 
	operator_account_id VARCHAR(36), 
	attempt_id VARCHAR(36), 
	run_version INTEGER, 
	command_id VARCHAR(36), 
	runtime_epoch VARCHAR(36), 
	admitted_at TIMESTAMP WITH TIME ZONE, 
	recovery_id VARCHAR(36), 
	recovery_reason TEXT, 
	recovery_started_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (singleton_id), 
	CONSTRAINT ck_task_execution_slot_singleton CHECK (singleton_id = 1), 
	CONSTRAINT fk_slot_task_owner FOREIGN KEY(task_id, operator_account_id) REFERENCES report_tasks (id, operator_account_id), 
	CONSTRAINT ck_task_execution_slot_phase_invariants CHECK ((phase = 'FREE' AND task_id IS NULL AND operator_account_id IS NULL AND attempt_id IS NULL AND run_version IS NULL AND command_id IS NULL AND runtime_epoch IS NULL AND admitted_at IS NULL AND recovery_id IS NULL AND recovery_reason IS NULL AND recovery_started_at IS NULL) OR (phase IN ('ADMITTED', 'RUNNING', 'DRAINING') AND task_id IS NOT NULL AND operator_account_id IS NOT NULL AND attempt_id IS NOT NULL AND run_version IS NOT NULL AND command_id IS NOT NULL AND runtime_epoch IS NOT NULL AND admitted_at IS NOT NULL AND recovery_id IS NULL AND recovery_reason IS NULL AND recovery_started_at IS NULL) OR (phase = 'RECOVERY_REQUIRED' AND recovery_id IS NOT NULL AND recovery_reason IS NOT NULL AND recovery_started_at IS NOT NULL AND ((task_id IS NOT NULL AND operator_account_id IS NOT NULL AND attempt_id IS NOT NULL AND run_version IS NOT NULL AND command_id IS NOT NULL AND runtime_epoch IS NOT NULL AND admitted_at IS NOT NULL) OR (task_id IS NULL AND operator_account_id IS NULL AND attempt_id IS NULL AND run_version IS NULL AND command_id IS NULL AND runtime_epoch IS NULL AND admitted_at IS NULL))))
);

ALTER TABLE task_execution_slot ENABLE ROW LEVEL SECURITY;

CREATE TABLE task_start_receipts (
	operator_account_id VARCHAR(36) NOT NULL, 
	command_id VARCHAR(36) NOT NULL, 
	task_id VARCHAR(36) NOT NULL, 
	attempt_id VARCHAR(36) NOT NULL, 
	slot_generation INTEGER NOT NULL, 
	run_version INTEGER NOT NULL, 
	runtime_epoch VARCHAR(36) NOT NULL, 
	admitted_task_version INTEGER NOT NULL, 
	admitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	payload_fingerprint TEXT NOT NULL, 
	authority_contract_version INTEGER NOT NULL, 
	outcome_phase VARCHAR(30) NOT NULL, 
	PRIMARY KEY (operator_account_id, command_id), 
	CONSTRAINT fk_start_receipts_task_owner FOREIGN KEY(task_id, operator_account_id) REFERENCES report_tasks (id, operator_account_id), 
	FOREIGN KEY(operator_account_id) REFERENCES operator_accounts (id)
);

CREATE INDEX ix_task_start_receipts_task ON task_start_receipts (task_id, operator_account_id, admitted_at);

ALTER TABLE task_start_receipts ENABLE ROW LEVEL SECURITY;

INSERT INTO operator_accounts (id, username_key, username_display, password_hash, status, auth_version, run_version, created_at, updated_at) VALUES ('00000000-0000-0000-0000-000000000001', 'system_default', 'system_default', 'dummy_hash', 'QUARANTINED', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO task_execution_slot (singleton_id, generation, phase) VALUES (1, 0, 'FREE');
