 USE ehealth_auth;

CREATE TABLE IF NOT EXISTS record_versions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  record_id INT NOT NULL,
  version_no INT NOT NULL,
  data_snapshot LONGTEXT NOT NULL,
  data_hash CHAR(64) NOT NULL,
  blockchain_tx_hash VARCHAR(255) NULL,
  updated_by INT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_record_versions_record_version (record_id, version_no),
  KEY idx_record_versions_record (record_id, created_at),
  CONSTRAINT fk_record_versions_record FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
  CONSTRAINT fk_record_versions_user FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS integrity_node_states (
  id INT AUTO_INCREMENT PRIMARY KEY,
  record_id INT NOT NULL,
  node_name VARCHAR(100) NOT NULL,
  behavior_mode ENUM('normal','offline','delayed','compromised') NOT NULL DEFAULT 'normal',
  status ENUM('pending','valid','mismatch','offline','delayed','compromised') NOT NULL DEFAULT 'pending',
  last_seen_hash CHAR(64) NULL,
  last_verification_time DATETIME NULL,
  status_note VARCHAR(255) NULL,
  local_version_no INT NULL,
  last_blockchain_hash CHAR(64) NULL,
  signature_verified TINYINT(1) NOT NULL DEFAULT 0,
  sync_status ENUM('pending','synced','stale','offline','rejected','compromised') NOT NULL DEFAULT 'pending',
  last_broadcast_at DATETIME NULL,
  UNIQUE KEY uq_integrity_node_record_name (record_id, node_name),
  KEY idx_integrity_node_record (record_id),
  CONSTRAINT fk_integrity_node_states_record FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS integrity_simulations (
  record_id INT PRIMARY KEY,
  tamper_enabled TINYINT(1) NOT NULL DEFAULT 0,
  tampered_payload LONGTEXT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_integrity_simulations_record FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS record_change_requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  record_id INT NOT NULL,
  version_no INT NOT NULL,
  requested_by INT NOT NULL,
  requester_role VARCHAR(20) NOT NULL,
  payload_hash CHAR(64) NOT NULL,
  proposed_snapshot LONGTEXT NULL,
  signer_key_id VARCHAR(120) NOT NULL,
  signature_hash CHAR(64) NOT NULL,
  signature_verified TINYINT(1) NOT NULL DEFAULT 0,
  blockchain_tx_hash VARCHAR(255) NULL,
  request_status ENUM('broadcast','ledger_anchored','rejected') NOT NULL DEFAULT 'broadcast',
  request_note VARCHAR(255) NULL,
  approval_threshold INT NOT NULL DEFAULT 70,
  accepted_nodes INT NOT NULL DEFAULT 0,
  rejected_nodes INT NOT NULL DEFAULT 0,
  broadcast_at DATETIME NOT NULL,
  ledger_updated_at DATETIME NULL,
  finalized_at DATETIME NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  KEY idx_record_change_requests_record (record_id, version_no),
  CONSTRAINT fk_record_change_requests_record FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
  CONSTRAINT fk_record_change_requests_user FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS record_change_node_votes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  change_request_id INT NOT NULL,
  record_id INT NOT NULL,
  node_name VARCHAR(100) NOT NULL,
  identity_checked TINYINT(1) NOT NULL DEFAULT 0,
  identity_verified TINYINT(1) NOT NULL DEFAULT 0,
  vote_status ENUM('pending','accepted','rejected') NOT NULL DEFAULT 'pending',
  reviewed_at DATETIME NULL,
  note VARCHAR(255) NULL,
  UNIQUE KEY uq_record_change_node_vote (change_request_id, node_name),
  KEY idx_record_change_node_votes_record (record_id, change_request_id),
  CONSTRAINT fk_record_change_node_votes_request FOREIGN KEY (change_request_id) REFERENCES record_change_requests(id) ON DELETE CASCADE,
  CONSTRAINT fk_record_change_node_votes_record FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);
