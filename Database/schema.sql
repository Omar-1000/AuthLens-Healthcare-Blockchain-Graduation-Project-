DROP DATABASE IF EXISTS ehealth_auth;
CREATE DATABASE ehealth_auth;
USE ehealth_auth;

-- =====================================
-- 1) USERS
-- =====================================
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  role ENUM('patient','doctor','admin','storage') NOT NULL,
  first_name VARCHAR(100) NULL,
  last_name VARCHAR(100) NULL,
  name VARCHAR(100) NULL,
  email VARCHAR(100) NOT NULL UNIQUE,
  password VARCHAR(255) NULL,
  age INT NULL,
  gender VARCHAR(20) NULL,
  hashed_id CHAR(64) NOT NULL UNIQUE,
  wallet_address VARCHAR(255) NULL UNIQUE,
  login_nonce VARCHAR(255) NULL,
  approval_status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'approved',
  doctor_medical_id VARCHAR(100) NULL,
  specialty VARCHAR(150) NULL,
  phone VARCHAR(30) NULL,
  bio TEXT NULL,
  doctor_id_card_path VARCHAR(255) NULL,
  doctor_medical_id_photo_path VARCHAR(255) NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================
-- 2) RECORDS
-- =====================================
CREATE TABLE records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL,
  encrypted_data TEXT NOT NULL,
  data_hash CHAR(64) NOT NULL,
  blockchain_tx_hash VARCHAR(255) NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_records_patient
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
);

-- =====================================
-- 3) OTP CODES
-- =====================================
CREATE TABLE otp_codes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  otp_code VARCHAR(6) NOT NULL,
  purpose VARCHAR(50) NOT NULL DEFAULT 'login',
  expires_at DATETIME NOT NULL,
  is_used TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_otp_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_otp_user_purpose_created ON otp_codes(user_id, purpose, created_at);

-- =====================================
-- 4) APPOINTMENTS
-- =====================================
CREATE TABLE appointments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL,
  doctor_id INT NOT NULL,
  appointment_date DATETIME NULL,
  status ENUM('pending','approved','rejected','cancelled','completed') NOT NULL DEFAULT 'pending',
  notes TEXT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_appointments_patient
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_appointments_doctor
    FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_appointments_doctor_status ON appointments(doctor_id, status);
CREATE INDEX idx_appointments_patient_status ON appointments(patient_id, status);

-- =====================================
-- 5) ACCESS REQUESTS
-- =====================================
CREATE TABLE access_requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL,
  doctor_id INT NOT NULL,
  appointment_id INT NULL,
  status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
  blockchain_tx_hash VARCHAR(255) NULL,
  requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  prescription_written_at DATETIME NULL,
  CONSTRAINT fk_access_requests_patient
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_access_requests_doctor
    FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_access_requests_appointment
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
);

CREATE INDEX idx_access_requests_cycle
ON access_requests(patient_id, doctor_id, appointment_id, status);

-- =====================================
-- 6) PRESCRIPTIONS
-- =====================================
CREATE TABLE prescriptions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL,
  doctor_id INT NOT NULL,
  appointment_id INT NULL,
  access_request_id INT NULL,
  medicine_name VARCHAR(255) NOT NULL,
  dosage VARCHAR(255) NOT NULL,
  instructions TEXT NOT NULL,
  dispense_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  dispensed_at DATETIME NULL,
  dispensed_by INT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_prescriptions_patient
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_prescriptions_doctor
    FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_prescriptions_appointment
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
  CONSTRAINT fk_prescriptions_access_request
    FOREIGN KEY (access_request_id) REFERENCES access_requests(id) ON DELETE SET NULL,
  CONSTRAINT fk_prescriptions_dispensed_by
    FOREIGN KEY (dispensed_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_prescriptions_cycle
ON prescriptions(patient_id, doctor_id, appointment_id, access_request_id);

CREATE INDEX idx_prescriptions_dispense_status
ON prescriptions(dispense_status, created_at);

-- =====================================
-- 7) PHARMACY INVENTORY
-- =====================================
CREATE TABLE pharmacy_inventory (
  id INT AUTO_INCREMENT PRIMARY KEY,
  medicine_name VARCHAR(255) NOT NULL,
  category VARCHAR(120) NULL,
  quantity_in_stock INT NOT NULL DEFAULT 0,
  unit VARCHAR(60) NOT NULL DEFAULT 'units',
  low_stock_threshold INT NOT NULL DEFAULT 10,
  supplier_name VARCHAR(255) NULL,
  expiry_date DATE NULL,
  notes TEXT NULL,
  created_by INT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_pharmacy_inventory_medicine_name (medicine_name),
  CONSTRAINT fk_pharmacy_inventory_created_by
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_pharmacy_inventory_low_stock
ON pharmacy_inventory(quantity_in_stock, low_stock_threshold);

-- =====================================
-- 8) PHARMACY STOCK MOVEMENTS
-- =====================================
CREATE TABLE pharmacy_stock_movements (
  id INT AUTO_INCREMENT PRIMARY KEY,
  inventory_id INT NOT NULL,
  action_type ENUM('add','dispense','adjust') NOT NULL,
  quantity_changed INT NOT NULL,
  quantity_after INT NOT NULL,
  note TEXT NULL,
  performed_by INT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_pharmacy_stock_inventory
    FOREIGN KEY (inventory_id) REFERENCES pharmacy_inventory(id) ON DELETE CASCADE,
  CONSTRAINT fk_pharmacy_stock_user
    FOREIGN KEY (performed_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_pharmacy_stock_inventory_created
ON pharmacy_stock_movements(inventory_id, created_at);

-- =====================================
-- 9) MESSAGES
-- =====================================
CREATE TABLE messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL,
  doctor_id INT NOT NULL,
  sender_id INT NOT NULL,
  sender_role ENUM('patient','doctor') NOT NULL,
  message_text TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_messages_patient
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_messages_doctor
    FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_patient_doctor ON messages(patient_id, doctor_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);

-- =====================================
-- 10) AUDIT LOGS
-- =====================================
CREATE TABLE audit_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  action VARCHAR(50) NULL,
  ip_address VARCHAR(45) NULL,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_audit_logs_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- =====================================
-- 11) USER SESSIONS
-- =====================================
CREATE TABLE user_sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_token_hash CHAR(64) NOT NULL,
  user_id INT NOT NULL,
  role VARCHAR(20) NOT NULL,
  user_name VARCHAR(255) NOT NULL,
  hashed_id VARCHAR(255) NOT NULL,
  login_method VARCHAR(20) NOT NULL,
  ip_address VARCHAR(255) NULL,
  user_agent TEXT NULL,
  created_at DATETIME NOT NULL,
  last_seen_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  is_revoked TINYINT(1) NOT NULL DEFAULT 0,
  UNIQUE KEY uq_user_sessions_token_hash (session_token_hash),
  KEY idx_user_sessions_user_id (user_id),
  KEY idx_user_sessions_active (is_revoked, expires_at),
  CONSTRAINT fk_user_sessions_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- =====================================
-- 12) RECORD VERSIONS
-- =====================================
CREATE TABLE record_versions (
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
  CONSTRAINT fk_record_versions_record
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
  CONSTRAINT fk_record_versions_user
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

-- =====================================
-- 13) INTEGRITY NODE STATES
-- =====================================
CREATE TABLE integrity_node_states (
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
  CONSTRAINT fk_integrity_node_states_record
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

-- =====================================
-- 14) INTEGRITY SIMULATIONS
-- =====================================
CREATE TABLE integrity_simulations (
  record_id INT PRIMARY KEY,
  tamper_enabled TINYINT(1) NOT NULL DEFAULT 0,
  tampered_payload LONGTEXT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_integrity_simulations_record
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

-- =====================================
-- 15) RECORD CHANGE REQUESTS
-- =====================================
CREATE TABLE record_change_requests (
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
  CONSTRAINT fk_record_change_requests_record
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
  CONSTRAINT fk_record_change_requests_user
    FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE CASCADE
);

-- =====================================
-- 16) RECORD CHANGE NODE VOTES
-- =====================================
CREATE TABLE record_change_node_votes (
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
  CONSTRAINT fk_record_change_node_votes_request
    FOREIGN KEY (change_request_id) REFERENCES record_change_requests(id) ON DELETE CASCADE,
    CONSTRAINT fk_record_change_node_votes_record
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

-- =====================================
-- SAMPLE USERS
-- =====================================
INSERT INTO users (
  role, first_name, last_name, name, email, password, age, gender, hashed_id, phone
) VALUES
('patient','Ali','Patient','Ali Patient','ali@demo.com','test123',29,'male',SHA2('ALI_NATIONAL_ID', 256),'0790000000'),
('doctor','Sara','Kamal','Dr. Sara','sara@demo.com','test123',40,'female',SHA2('SARA_LICENSE', 256),'0791111111'),
('admin','System','Admin','System Admin','admin@demo.com','test123',NULL,NULL,SHA2('ADMIN_SYSTEM_ID', 256),'0792222222'),
('storage','Mona','Storage','Mona Storage','storage@demo.com','test123',33,'female',SHA2('STORAGE_TEAM_ID', 256),'0793333333');

UPDATE users SET specialty = 'Cardiology', bio = 'Experienced cardiologist focused on preventive heart care and follow-up consultations.', approval_status = 'approved' WHERE email = 'sara@demo.com';
UPDATE users SET bio = 'Storage account for managing medicine inventory and low-stock alerts.', approval_status = 'approved' WHERE email = 'storage@demo.com';

-- IMPORTANT: assign Ganache wallet addresses to roles
UPDATE users SET wallet_address = '0x5d0ef72E30eA187C04f8e764e0cd1C32ADb09BC0' WHERE email = 'admin@demo.com';
UPDATE users SET wallet_address = '0xfd206e976500ac90FdFe402491364c7824328131' WHERE email = 'sara@demo.com';
UPDATE users SET wallet_address = '0xEDb1aE7D192BFD2495f98a3872389CDEb9c41b44' WHERE email = 'ali@demo.com';
UPDATE users SET wallet_address = '0xB2946020d0466Fd80d98143675164ce21334BcCf' WHERE email = 'storage@demo.com';

-- =====================================
-- SAMPLE RECORD + CANONICAL HASH
-- =====================================
SET @ali_snapshot = '{"encrypted_data":"ENCRYPTED_MEDICAL_DATA_PLACEHOLDER","patient_age":29,"patient_email":"ali@demo.com","patient_gender":"male","patient_hashed_id":"';
SET @ali_snapshot = CONCAT(@ali_snapshot, SHA2('ALI_NATIONAL_ID', 256), '","patient_name":"Ali Patient","patient_wallet_address":"","prescriptions":[]}');

INSERT INTO records (
  patient_id, encrypted_data, data_hash, blockchain_tx_hash
) VALUES (
  (SELECT id FROM users WHERE email = 'ali@demo.com'),
  'ENCRYPTED_MEDICAL_DATA_PLACEHOLDER',
  SHA2(@ali_snapshot, 256),
  NULL
);

-- =====================================
-- SAMPLE ACCESS REQUEST
-- =====================================
INSERT INTO access_requests (patient_id, doctor_id, appointment_id, status, blockchain_tx_hash) VALUES (
  (SELECT id FROM users WHERE email = 'ali@demo.com'),
  (SELECT id FROM users WHERE email = 'sara@demo.com'),
  NULL,
  'pending',
  NULL
);

-- =====================================
-- SAMPLE APPOINTMENT REQUEST
-- =====================================
INSERT INTO appointments (patient_id, doctor_id, appointment_date, status, notes) VALUES (
  (SELECT id FROM users WHERE email = 'ali@demo.com'),
  (SELECT id FROM users WHERE email = 'sara@demo.com'),
  NULL,
  'pending',
  'Patient requested an appointment from patient home page.'
);

-- =====================================
-- SAMPLE PHARMACY INVENTORY
-- =====================================
INSERT INTO pharmacy_inventory (
  medicine_name, category, quantity_in_stock, unit, low_stock_threshold,
  supplier_name, expiry_date, notes, created_by
) VALUES
(
  'Paracetamol 500mg',
  'Pain Relief',
  120,
  'tablets',
  20,
  'MedSupply Co.',
  DATE_ADD(CURDATE(), INTERVAL 14 MONTH),
  'Standard fever and pain medicine.',
  (SELECT id FROM users WHERE email = 'storage@demo.com')
),
(
  'Amoxicillin 250mg',
  'Antibiotic',
  8,
  'capsules',
  15,
  'Health Pharma',
  DATE_ADD(CURDATE(), INTERVAL 9 MONTH),
  'Low stock sample for alert testing.',
  (SELECT id FROM users WHERE email = 'storage@demo.com')
),
(
  'Insulin',
  'Hormone',
  0,
  'vials',
  5,
  'Care Medical',
  DATE_ADD(CURDATE(), INTERVAL 6 MONTH),
  'Out of stock sample for alarm state.',
  (SELECT id FROM users WHERE email = 'storage@demo.com')
);

INSERT INTO pharmacy_stock_movements (
  inventory_id, action_type, quantity_changed, quantity_after, note, performed_by
) VALUES
(
  (SELECT id FROM pharmacy_inventory WHERE medicine_name = 'Paracetamol 500mg'),
  'add',
  120,
  120,
  'Initial stock load',
  (SELECT id FROM users WHERE email = 'storage@demo.com')
),
(
  (SELECT id FROM pharmacy_inventory WHERE medicine_name = 'Amoxicillin 250mg'),
  'add',
  8,
  8,
  'Initial stock load',
  (SELECT id FROM users WHERE email = 'storage@demo.com')
),
(
  (SELECT id FROM pharmacy_inventory WHERE medicine_name = 'Insulin'),
  'adjust',
  0,
  0,
  'Initial zero-stock alert sample',
  (SELECT id FROM users WHERE email = 'storage@demo.com')
);

-- =====================================
-- SAMPLE AUDIT LOG
-- =====================================
INSERT INTO audit_logs (user_id, action, ip_address) VALUES (
  (SELECT id FROM users WHERE email = 'ali@demo.com'),
  'LOGIN_SUCCESS',
  '127.0.0.1'
);

-- =====================================
-- SAMPLE OTP
-- =====================================
INSERT INTO otp_codes (user_id, otp_code, purpose, expires_at, is_used) VALUES (
  (SELECT id FROM users WHERE email = 'ali@demo.com'),
  '123456',
  'login',
  DATE_ADD(NOW(), INTERVAL 10 MINUTE),
  0
);

-- =====================================
-- INITIAL TRUSTED RECORD VERSION
-- =====================================
INSERT INTO record_versions (
  record_id, version_no, data_snapshot, data_hash, blockchain_tx_hash, updated_by
) VALUES (
  (SELECT id FROM records WHERE patient_id = (SELECT id FROM users WHERE email = 'ali@demo.com') LIMIT 1),
  1,
  @ali_snapshot,
  SHA2(@ali_snapshot, 256),
  NULL,
  (SELECT id FROM users WHERE email = 'ali@demo.com')
);

-- =====================================
-- SEED 4 INTEGRITY NODES
-- =====================================
INSERT INTO integrity_node_states (
  record_id, node_name, behavior_mode, status, last_seen_hash, last_verification_time, status_note,
  local_version_no, last_blockchain_hash, signature_verified, sync_status, last_broadcast_at
) VALUES
(
  (SELECT id FROM records WHERE patient_id = (SELECT id FROM users WHERE email = 'ali@demo.com') LIMIT 1),
  'Hospital Core Node',
  'normal',
  'pending',
  SHA2(@ali_snapshot, 256),
  NULL,
  'Awaiting first verification run',
  1,
  SHA2(@ali_snapshot, 256),
  0,
  'pending',
  NULL
),
(
  (SELECT id FROM records WHERE patient_id = (SELECT id FROM users WHERE email = 'ali@demo.com') LIMIT 1),
  'Doctor Node',
  'normal',
  'pending',
  SHA2(@ali_snapshot, 256),
  NULL,
  'Awaiting first verification run',
  1,
  SHA2(@ali_snapshot, 256),
  0,
  'pending',
  NULL
),
(
  (SELECT id FROM records WHERE patient_id = (SELECT id FROM users WHERE email = 'ali@demo.com') LIMIT 1),
  'Patient Node',
  'normal',
  'pending',
  SHA2(@ali_snapshot, 256),
  NULL,
  'Awaiting first verification run',
  1,
  SHA2(@ali_snapshot, 256),
  0,
  'pending',
  NULL
),
(
  (SELECT id FROM records WHERE patient_id = (SELECT id FROM users WHERE email = 'ali@demo.com') LIMIT 1),
  'Audit Node',
  'normal',
  'pending',
  SHA2(@ali_snapshot, 256),
  NULL,
  'Awaiting first verification run',
  1,
  SHA2(@ali_snapshot, 256),
  0,
  'pending',
  NULL
);

-- =====================================
-- SEED SIMULATION STATE
-- =====================================
INSERT INTO integrity_simulations (
  record_id, tamper_enabled, tampered_payload, updated_at
) VALUES (
  (SELECT id FROM records WHERE patient_id = (SELECT id FROM users WHERE email = 'ali@demo.com') LIMIT 1),
  0,
  NULL,
  NOW()
);

-- =====================================
-- CHECK DATA
-- =====================================
SELECT * FROM users;
SELECT * FROM records;
SELECT * FROM access_requests;
SELECT * FROM appointments;
SELECT * FROM prescriptions;
SELECT * FROM pharmacy_inventory;
SELECT * FROM pharmacy_stock_movements;
SELECT * FROM messages;
SELECT * FROM audit_logs;
SELECT * FROM otp_codes;
SELECT * FROM user_sessions;
SELECT * FROM record_versions;
SELECT * FROM integrity_node_states;
SELECT * FROM integrity_simulations;
SELECT * FROM record_change_requests;
SELECT * FROM record_change_node_votes;
