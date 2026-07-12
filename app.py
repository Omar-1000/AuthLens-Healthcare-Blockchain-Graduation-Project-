

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, make_response
import mysql.connector
import base64
import secrets
import string
import io
import random
import os
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from urllib import error as urllib_error
from urllib import request as urllib_request

 
from web3 import Web3
from eth_account.messages import encode_defunct
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

# blockchain
from blockchain import (
    store_data_hash_onchain,
    store_identity_hash_onchain,
    store_payload_hash_onchain,
    store_record_onchain,
    get_latest_record_hash,
)


# captcha image
from PIL import Image, ImageDraw, ImageFont, ImageFilter


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("APP_SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_SECURE_COOKIES", "0") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

AUTH_SESSION_COOKIE_KEY = "auth_session_id"
AUTH_IDLE_TIMEOUT = timedelta(minutes=60)
AUTH_ABSOLUTE_TIMEOUT = timedelta(hours=8)
AUTH_SESSION_KEYS = (AUTH_SESSION_COOKIE_KEY, "user_id", "role", "name", "hashed_id")
HF_CHAT_API_URL = os.environ.get("HF_CHAT_API_URL", "https://router.huggingface.co/v1/chat/completions")
HF_CHAT_MODEL = os.environ.get("HF_CHAT_MODEL", "Qwen/Qwen2.5-7B-Instruct")
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
INTEGRITY_NODE_NAMES = (
    "Hospital Core Node",
    "Doctor Node",
    "Patient Node",
    "Audit Node"
)
INTEGRITY_CONSENSUS_THRESHOLD = 70
INTEGRITY_SIGNATURE_NAMESPACE = "doctor-record-change"
DOCTOR_AVATAR_POOLS = {
    "female": [
        "images/doctor_avatars/female_1.jpg",
        "images/doctor_avatars/female_2.jpg"
    ],
    "male": [
        "images/doctor_avatars/male_1.jpg",
        "images/doctor_avatars/male_2.jpg"
    ]
}


# =========================
# MAIL CONFIG
# =========================
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 465
app.config["MAIL_USE_TLS"] = False
app.config["MAIL_USE_SSL"] = True
app.config["MAIL_USERNAME"] = "serverehealth@gmail.com"
app.config["MAIL_PASSWORD"] = "kknd ptcb buyj derl"
app.config["MAIL_DEFAULT_SENDER"] = "serverehealth@gmail.com"


mail = Mail(app)


# =========================
# UPLOAD CONFIG
# =========================
UPLOAD_FOLDER = os.path.join("static", "uploads", "doctor_docs")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================
# DATABASE CONFIG
# =========================
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "HealthCareSystem123@@##"
DB_NAME = "ehealth_auth"
USE_BLOCKCHAIN_FOR_APPROVALS = True
RECORD_ENCRYPTION_SECRET = os.environ.get("RECORD_ENCRYPTION_SECRET", "ehealth-record-encryption-v1")
RECORD_ENCRYPTION_PREFIX = "enc:v1:"


@app.template_filter("mask_hash")
def mask_hash(value, head=6, tail=6, placeholder="Not available"):
    if value is None:
        return placeholder

    text = str(value).strip()
    if not text:
        return placeholder

    if len(text) <= head + tail + 3:
        return text

    return f"{text[:head]}...{text[-tail:]}"


def _derive_record_encryption_key():
    return hashlib.sha256(RECORD_ENCRYPTION_SECRET.encode("utf-8")).digest()


def encrypt_record_payload(plain_text):
    if plain_text is None:
        return ""

    text = str(plain_text)
    if not text:
        return ""
    if text.startswith(RECORD_ENCRYPTION_PREFIX):
        return text

    nonce = get_random_bytes(12)
    cipher = AES.new(_derive_record_encryption_key(), AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(text.encode("utf-8"))
    encoded = base64.b64encode(nonce + tag + ciphertext).decode("ascii")
    return f"{RECORD_ENCRYPTION_PREFIX}{encoded}"


def decrypt_record_payload(payload):
    if payload is None:
        return ""

    text = str(payload)
    if not text.startswith(RECORD_ENCRYPTION_PREFIX):
        return text

    try:
        raw = base64.b64decode(text[len(RECORD_ENCRYPTION_PREFIX):], validate=True)
        nonce = raw[:12]
        tag = raw[12:28]
        ciphertext = raw[28:]
        cipher = AES.new(_derive_record_encryption_key(), AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except Exception:
        return text




def get_db():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )


def ensure_messages_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            doctor_id INT NOT NULL,
            sender_id INT NOT NULL,
            sender_role ENUM('patient','doctor') NOT NULL,
            message_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'messages'
          AND index_name = 'idx_messages_patient_doctor'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_messages_patient_doctor ON messages(patient_id, doctor_id)")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'messages'
          AND index_name = 'idx_messages_created_at'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_messages_created_at ON messages(created_at)")
    db.commit()
    cur.close()
    db.close()


def ensure_appointments_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            doctor_id INT NOT NULL,
            appointment_date DATETIME NULL,
            status ENUM('pending','approved','rejected','cancelled','completed') NOT NULL DEFAULT 'pending',
            notes TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'appointments'
          AND index_name = 'idx_appointments_doctor_status'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_appointments_doctor_status ON appointments(doctor_id, status)")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'appointments'
          AND index_name = 'idx_appointments_patient_status'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_appointments_patient_status ON appointments(patient_id, status)")
    db.commit()
    cur.close()
    db.close()


def ensure_prescriptions_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            doctor_id INT NOT NULL,
            medicine_name VARCHAR(255) NOT NULL,
            dosage VARCHAR(255) NOT NULL,
            instructions TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    db.commit()
    cur.close()
    db.close()


def ensure_pharmacy_tables():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pharmacy_inventory (
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
            CONSTRAINT fk_pharmacy_inventory_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pharmacy_stock_movements (
            id INT AUTO_INCREMENT PRIMARY KEY,
            inventory_id INT NOT NULL,
            action_type ENUM('add','dispense','adjust') NOT NULL,
            quantity_changed INT NOT NULL,
            quantity_after INT NOT NULL,
            note TEXT NULL,
            performed_by INT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_pharmacy_stock_inventory FOREIGN KEY (inventory_id) REFERENCES pharmacy_inventory(id) ON DELETE CASCADE,
            CONSTRAINT fk_pharmacy_stock_user FOREIGN KEY (performed_by) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'pharmacy_inventory'
          AND index_name = 'idx_pharmacy_inventory_low_stock'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_pharmacy_inventory_low_stock ON pharmacy_inventory(quantity_in_stock, low_stock_threshold)")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'pharmacy_stock_movements'
          AND index_name = 'idx_pharmacy_stock_inventory_created'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_pharmacy_stock_inventory_created ON pharmacy_stock_movements(inventory_id, created_at)")
    db.commit()
    cur.close()
    db.close()


def ensure_access_request_cycle_columns():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'access_requests'
          AND column_name = 'appointment_id'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE access_requests ADD COLUMN appointment_id INT NULL AFTER doctor_id")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'access_requests'
          AND column_name = 'prescription_written_at'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE access_requests ADD COLUMN prescription_written_at DATETIME NULL AFTER requested_at")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'prescriptions'
          AND column_name = 'appointment_id'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE prescriptions ADD COLUMN appointment_id INT NULL AFTER doctor_id")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'prescriptions'
          AND column_name = 'access_request_id'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE prescriptions ADD COLUMN access_request_id INT NULL AFTER appointment_id")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'access_requests'
          AND index_name = 'idx_access_requests_cycle'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_access_requests_cycle ON access_requests(patient_id, doctor_id, appointment_id, status)")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'prescriptions'
          AND index_name = 'idx_prescriptions_cycle'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_prescriptions_cycle ON prescriptions(patient_id, doctor_id, appointment_id, access_request_id)")

    db.commit()
    cur.close()
    db.close()


def ensure_prescription_dispense_columns():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'prescriptions'
          AND column_name = 'dispense_status'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE prescriptions ADD COLUMN dispense_status VARCHAR(20) NOT NULL DEFAULT 'pending' AFTER instructions")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'prescriptions'
          AND column_name = 'dispensed_at'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE prescriptions ADD COLUMN dispensed_at DATETIME NULL AFTER dispense_status")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'prescriptions'
          AND column_name = 'dispensed_by'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE prescriptions ADD COLUMN dispensed_by INT NULL AFTER dispensed_at")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = 'prescriptions'
          AND index_name = 'idx_prescriptions_dispense_status'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_prescriptions_dispense_status ON prescriptions(dispense_status, created_at)")
    db.commit()
    cur.close()
    db.close()


def ensure_user_sessions_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
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
            CONSTRAINT fk_user_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    db.commit()
    cur.close()
    db.close()


def ensure_doctor_avatar_column():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'users'
          AND column_name = 'doctor_avatar_path'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE users ADD COLUMN doctor_avatar_path VARCHAR(255) NULL AFTER gender")
        db.commit()
    cur.close()
    db.close()


def ensure_record_versions_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
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
        )
    """)
    db.commit()
    cur.close()
    db.close()


def ensure_integrity_node_states_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS integrity_node_states (
            id INT AUTO_INCREMENT PRIMARY KEY,
            record_id INT NOT NULL,
            node_name VARCHAR(100) NOT NULL,
            behavior_mode ENUM('normal','offline','delayed','compromised') NOT NULL DEFAULT 'normal',
            status ENUM('pending','valid','mismatch','offline','delayed','compromised') NOT NULL DEFAULT 'pending',
            last_seen_hash CHAR(64) NULL,
            last_verification_time DATETIME NULL,
            status_note VARCHAR(255) NULL,
            UNIQUE KEY uq_integrity_node_record_name (record_id, node_name),
            KEY idx_integrity_node_record (record_id),
            CONSTRAINT fk_integrity_node_states_record FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'integrity_node_states'
          AND column_name = 'local_version_no'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE integrity_node_states ADD COLUMN local_version_no INT NULL AFTER status_note")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'integrity_node_states'
          AND column_name = 'last_blockchain_hash'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE integrity_node_states ADD COLUMN last_blockchain_hash CHAR(64) NULL AFTER local_version_no")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'integrity_node_states'
          AND column_name = 'signature_verified'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE integrity_node_states ADD COLUMN signature_verified TINYINT(1) NOT NULL DEFAULT 0 AFTER last_blockchain_hash")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'integrity_node_states'
          AND column_name = 'sync_status'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("""
            ALTER TABLE integrity_node_states
            ADD COLUMN sync_status ENUM('pending','synced','stale','offline','rejected','compromised') NOT NULL DEFAULT 'pending'
            AFTER signature_verified
        """)

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'integrity_node_states'
          AND column_name = 'last_broadcast_at'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE integrity_node_states ADD COLUMN last_broadcast_at DATETIME NULL AFTER sync_status")
    db.commit()
    cur.close()
    db.close()


def ensure_integrity_simulations_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS integrity_simulations (
            record_id INT PRIMARY KEY,
            tamper_enabled TINYINT(1) NOT NULL DEFAULT 0,
            tampered_payload LONGTEXT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_integrity_simulations_record FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    """)
    db.commit()
    cur.close()
    db.close()


def ensure_record_change_requests_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS record_change_requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            record_id INT NOT NULL,
            version_no INT NOT NULL,
            requested_by INT NOT NULL,
            requester_role VARCHAR(20) NOT NULL,
            payload_hash CHAR(64) NOT NULL,
            signer_key_id VARCHAR(120) NOT NULL,
            signature_hash CHAR(64) NOT NULL,
            signature_verified TINYINT(1) NOT NULL DEFAULT 0,
            blockchain_tx_hash VARCHAR(255) NULL,
            request_status ENUM('broadcast','ledger_anchored','rejected') NOT NULL DEFAULT 'broadcast',
            request_note VARCHAR(255) NULL,
            broadcast_at DATETIME NOT NULL,
            ledger_updated_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            KEY idx_record_change_requests_record (record_id, version_no),
            CONSTRAINT fk_record_change_requests_record FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
            CONSTRAINT fk_record_change_requests_user FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'record_change_requests'
          AND column_name = 'proposed_snapshot'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE record_change_requests ADD COLUMN proposed_snapshot LONGTEXT NULL AFTER payload_hash")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'record_change_requests'
          AND column_name = 'approval_threshold'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE record_change_requests ADD COLUMN approval_threshold INT NOT NULL DEFAULT 70 AFTER request_note")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'record_change_requests'
          AND column_name = 'accepted_nodes'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE record_change_requests ADD COLUMN accepted_nodes INT NOT NULL DEFAULT 0 AFTER approval_threshold")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'record_change_requests'
          AND column_name = 'rejected_nodes'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE record_change_requests ADD COLUMN rejected_nodes INT NOT NULL DEFAULT 0 AFTER accepted_nodes")

    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'record_change_requests'
          AND column_name = 'finalized_at'
    """, (DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE record_change_requests ADD COLUMN finalized_at DATETIME NULL AFTER ledger_updated_at")
    db.commit()
    cur.close()
    db.close()


def ensure_record_change_node_votes_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
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
        )
    """)
    db.commit()
    cur.close()
    db.close()


def cleanup_demo_pending_requests():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        DELETE ar
        FROM access_requests ar
        JOIN users p ON p.id = ar.patient_id
        JOIN users d ON d.id = ar.doctor_id
        WHERE p.email = 'ali@demo.com'
          AND d.email = 'sara@demo.com'
          AND ar.status = 'pending'
          AND ar.appointment_id IS NULL
    """)
    cur.execute("""
        DELETE a
        FROM appointments a
        JOIN users p ON p.id = a.patient_id
        JOIN users d ON d.id = a.doctor_id
        WHERE p.email = 'ali@demo.com'
          AND d.email = 'sara@demo.com'
          AND a.status = 'pending'
          AND a.appointment_date IS NULL
          AND (a.notes = 'Patient requested an appointment from patient home page.' OR a.notes IS NULL)
    """)
    cur.execute("""
        DELETE oc
        FROM otp_codes oc
        JOIN users u ON u.id = oc.user_id
        WHERE u.email = 'ali@demo.com'
          AND oc.purpose = 'login'
          AND oc.otp_code = '123456'
    """)
    db.commit()
    cur.close()
    db.close()


def ensure_demo_pending_change_request():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT r.id, r.patient_id, r.encrypted_data, r.data_hash, r.blockchain_tx_hash, r.created_at,
               u.name AS patient_name, u.email AS patient_email, u.age AS patient_age,
               u.gender AS patient_gender, u.hashed_id AS patient_hashed_id,
               u.wallet_address AS patient_wallet_address
        FROM records r
        JOIN users u ON u.id = r.patient_id
        WHERE u.email = 'ali@demo.com'
        ORDER BY r.id DESC
        LIMIT 1
    """)
    record = cur.fetchone()
    cur.execute("""
        SELECT id
        FROM users
        WHERE email = 'sara@demo.com' AND role = 'doctor'
        LIMIT 1
    """)
    doctor_row = cur.fetchone()
    cur.close()
    db.close()

    if not record or not doctor_row:
        return

    if get_pending_record_change_request(record["id"]):
        return

    doctor = get_user_identity(doctor_row["id"])
    if not doctor:
        return

    open_pending_change_request(record, doctor)


def get_patient_chat_contacts(patient_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT DISTINCT u.id, u.name, u.email,
               MAX(m.created_at) AS last_message_at,
               CASE WHEN EXISTS (
                   SELECT 1
                   FROM user_sessions us
                   WHERE us.user_id = u.id
                     AND us.role = 'doctor'
                     AND us.is_revoked = 0
                     AND us.expires_at > NOW()
                     AND us.last_seen_at >= %s
               ) THEN 1 ELSE 0 END AS is_online
        FROM access_requests ar
        JOIN users u ON u.id = ar.doctor_id
        LEFT JOIN messages m
               ON m.patient_id = ar.patient_id
              AND m.doctor_id = ar.doctor_id
        WHERE ar.patient_id=%s
        GROUP BY u.id, u.name, u.email
        ORDER BY last_message_at DESC, u.name ASC
    """, (datetime.now() - AUTH_IDLE_TIMEOUT, patient_id))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


@app.route("/chat/presence")
def patient_chat_presence():
    if "user_id" not in session:
        return jsonify({"ok": False, "error": "Please sign in again."}), 401
    if session.get("role") != "patient":
        return jsonify({"ok": False, "error": "Only patients can view chat presence."}), 403

    contacts = get_patient_chat_contacts(session["user_id"])
    return jsonify({
        "ok": True,
        "contacts": [
            {
                "id": contact["id"],
                "is_online": bool(contact.get("is_online")),
            }
            for contact in contacts
        ]
    })


def get_doctor_chat_contacts(doctor_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT DISTINCT u.id, u.name, u.email,
               ar.status,
               MAX(m.created_at) AS last_message_at,
               CASE WHEN EXISTS (
                   SELECT 1
                   FROM user_sessions us
                   WHERE us.user_id = u.id
                     AND us.role = 'patient'
                     AND us.is_revoked = 0
                     AND us.expires_at > NOW()
                     AND us.last_seen_at >= %s
               ) THEN 1 ELSE 0 END AS is_online
        FROM access_requests ar
        JOIN users u ON u.id = ar.patient_id
        LEFT JOIN messages m
               ON m.patient_id = ar.patient_id
              AND m.doctor_id = ar.doctor_id
        WHERE ar.doctor_id=%s
        GROUP BY u.id, u.name, u.email, ar.status
        ORDER BY last_message_at DESC, u.name ASC
    """, (datetime.now() - AUTH_IDLE_TIMEOUT, doctor_id))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_doctor_appointment_patients(doctor_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT u.id, u.name, u.email, u.hashed_id,
               MAX(a.appointment_date) AS latest_appointment,
               CASE WHEN EXISTS (
                   SELECT 1
                   FROM user_sessions us
                   WHERE us.user_id = u.id
                     AND us.role = 'patient'
                     AND us.is_revoked = 0
                     AND us.expires_at > NOW()
                     AND us.last_seen_at >= %s
               ) THEN 1 ELSE 0 END AS is_online
        FROM appointments a
        JOIN users u ON u.id = a.patient_id
        WHERE a.doctor_id=%s AND a.status IN ('approved','completed')
        GROUP BY u.id, u.name, u.email, u.hashed_id
        ORDER BY latest_appointment DESC, u.name ASC
    """, (datetime.now() - AUTH_IDLE_TIMEOUT, doctor_id))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


@app.route("/doctor/chat/presence")
def doctor_chat_presence():
    if "user_id" not in session:
        return jsonify({"ok": False, "error": "Please sign in again."}), 401
    if session.get("role") != "doctor":
        return jsonify({"ok": False, "error": "Only doctors can view chat presence."}), 403

    contacts = get_doctor_chat_contacts(session["user_id"])
    return jsonify({
        "ok": True,
        "contacts": [
            {
                "id": contact["id"],
                "is_online": bool(contact.get("is_online")),
            }
            for contact in contacts
        ]
    })


def get_doctor_appointments(doctor_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT a.id, a.patient_id, u.name AS patient_name, u.email AS patient_email,
               a.appointment_date, a.status, a.notes, u.phone AS patient_phone
        FROM appointments a
        JOIN users u ON u.id = a.patient_id
        WHERE a.doctor_id=%s
        ORDER BY
            CASE
                WHEN a.appointment_date IS NULL THEN 1
                ELSE 0
            END,
            a.appointment_date ASC,
            a.created_at DESC
    """, (doctor_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_patient_upcoming_appointments(patient_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT a.id, a.doctor_id, u.name AS doctor_name, u.specialty,
               a.appointment_date, a.status, a.notes, a.created_at
        FROM appointments a
        JOIN users u ON u.id = a.doctor_id
        WHERE a.patient_id=%s
        ORDER BY
            CASE
                WHEN a.appointment_date IS NULL THEN 1
                ELSE 0
            END,
            a.appointment_date ASC,
            a.created_at DESC
    """, (patient_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_prescriptions_for_patient(doctor_id, patient_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, medicine_name, dosage, instructions, dispense_status, dispensed_at, created_at,
               appointment_id, access_request_id
        FROM prescriptions
        WHERE doctor_id=%s AND patient_id=%s
        ORDER BY created_at DESC
    """, (doctor_id, patient_id))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_patient_prescriptions(patient_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT p.id, p.medicine_name, p.dosage, p.instructions, p.dispense_status, p.dispensed_at, p.created_at,
               p.appointment_id, p.access_request_id,
               u.name AS doctor_name
        FROM prescriptions p
        JOIN users u ON u.id = p.doctor_id
        WHERE p.patient_id=%s
        ORDER BY p.created_at DESC
    """, (patient_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_pending_prescriptions_for_storage():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT p.id, p.patient_id, p.doctor_id, p.medicine_name, p.dosage, p.instructions,
               p.dispense_status, p.created_at, patient.name AS patient_name, doctor.name AS doctor_name,
               pi.id AS inventory_id, pi.quantity_in_stock, pi.unit, pi.low_stock_threshold
        FROM prescriptions p
        JOIN users patient ON patient.id = p.patient_id
        JOIN users doctor ON doctor.id = p.doctor_id
        LEFT JOIN pharmacy_inventory pi ON LOWER(pi.medicine_name) = LOWER(p.medicine_name)
        WHERE p.dispense_status = 'pending'
        ORDER BY p.created_at DESC, p.id DESC
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_available_medicine_names():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT medicine_name, quantity_in_stock, unit, low_stock_threshold,
               CASE
                   WHEN quantity_in_stock <= 0 THEN 'out'
                   WHEN quantity_in_stock <= low_stock_threshold THEN 'low'
                   ELSE 'ok'
               END AS stock_status
        FROM pharmacy_inventory
        ORDER BY medicine_name ASC
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_pharmacy_inventory_items():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT pi.id, pi.medicine_name, pi.category, pi.quantity_in_stock, pi.unit,
               pi.low_stock_threshold, pi.supplier_name, pi.expiry_date, pi.notes,
               pi.created_at, pi.updated_at,
               CASE
                   WHEN pi.quantity_in_stock <= 0 THEN 'out'
                   WHEN pi.quantity_in_stock <= pi.low_stock_threshold THEN 'low'
                   ELSE 'ok'
               END AS stock_status
        FROM pharmacy_inventory pi
        ORDER BY
            CASE
                WHEN pi.quantity_in_stock <= 0 THEN 0
                WHEN pi.quantity_in_stock <= pi.low_stock_threshold THEN 1
                ELSE 2
            END,
            pi.medicine_name ASC
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_recent_stock_movements(limit=10):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT psm.id, psm.inventory_id, psm.action_type, psm.quantity_changed, psm.quantity_after,
               psm.note, psm.created_at, pi.medicine_name, u.name AS performed_by_name
        FROM pharmacy_stock_movements psm
        JOIN pharmacy_inventory pi ON pi.id = psm.inventory_id
        LEFT JOIN users u ON u.id = psm.performed_by
        ORDER BY psm.created_at DESC, psm.id DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_pharmacy_inventory_summary(items):
    low_stock_items = [item for item in items if item["stock_status"] == "low"]
    out_of_stock_items = [item for item in items if item["stock_status"] == "out"]
    total_units = sum(max(item.get("quantity_in_stock") or 0, 0) for item in items)
    return {
        "medicine_count": len(items),
        "low_stock_count": len(low_stock_items),
        "out_of_stock_count": len(out_of_stock_items),
        "total_units": total_units,
        "alert_items": out_of_stock_items + low_stock_items
    }


def create_inventory_medicine(form_data, created_by):
    medicine_name = (form_data.get("medicine_name") or "").strip()
    category = (form_data.get("category") or "").strip()
    unit = (form_data.get("unit") or "units").strip() or "units"
    supplier_name = (form_data.get("supplier_name") or "").strip()
    expiry_date = (form_data.get("expiry_date") or "").strip() or None
    notes = (form_data.get("notes") or "").strip() or None
    quantity_in_stock = form_data.get("quantity_in_stock", type=int)
    low_stock_threshold = form_data.get("low_stock_threshold", type=int)

    if not medicine_name:
        return False, "Medicine name is required."
    if quantity_in_stock is None or quantity_in_stock < 0:
        return False, "Starting quantity must be 0 or more."
    if low_stock_threshold is None or low_stock_threshold < 0:
        return False, "Low-stock threshold must be 0 or more."

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id FROM pharmacy_inventory WHERE medicine_name=%s LIMIT 1", (medicine_name,))
    existing_item = cur.fetchone()
    if existing_item:
        cur.close()
        db.close()
        return False, "This medicine already exists in storage."

    cur2 = db.cursor()
    cur2.execute("""
        INSERT INTO pharmacy_inventory (
            medicine_name, category, quantity_in_stock, unit, low_stock_threshold,
            supplier_name, expiry_date, notes, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        medicine_name, category or None, quantity_in_stock, unit, low_stock_threshold,
        supplier_name or None, expiry_date, notes, created_by
    ))
    inventory_id = cur2.lastrowid
    cur2.execute("""
        INSERT INTO pharmacy_stock_movements (
            inventory_id, action_type, quantity_changed, quantity_after, note, performed_by
        )
        VALUES (%s, 'add', %s, %s, %s, %s)
    """, (inventory_id, quantity_in_stock, quantity_in_stock, "Initial medicine registration", created_by))
    db.commit()
    cur2.close()
    cur.close()
    db.close()
    return True, "Medicine added to pharmacy storage."


def apply_stock_movement(form_data, performed_by):
    inventory_id = form_data.get("inventory_id", type=int)
    action_type = (form_data.get("action_type") or "").strip()
    quantity_changed = form_data.get("quantity_changed", type=int)
    note = (form_data.get("note") or "").strip() or None

    if not inventory_id:
        return False, "Please choose a medicine."
    if action_type not in ("add", "dispense", "adjust"):
        return False, "Invalid stock action."
    if quantity_changed is None or quantity_changed < 0:
        return False, "Quantity change must be 0 or more."

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, medicine_name, quantity_in_stock
        FROM pharmacy_inventory
        WHERE id=%s
        LIMIT 1
    """, (inventory_id,))
    item = cur.fetchone()
    if not item:
        cur.close()
        db.close()
        return False, "Medicine not found."

    current_quantity = item["quantity_in_stock"] or 0
    if action_type == "add":
        new_quantity = current_quantity + quantity_changed
    elif action_type == "dispense":
        new_quantity = current_quantity - quantity_changed
    else:
        new_quantity = quantity_changed

    if new_quantity < 0:
        cur.close()
        db.close()
        return False, "This action would make stock negative."

    cur2 = db.cursor()
    cur2.execute("""
        UPDATE pharmacy_inventory
        SET quantity_in_stock=%s
        WHERE id=%s
    """, (new_quantity, inventory_id))
    cur2.execute("""
        INSERT INTO pharmacy_stock_movements (
            inventory_id, action_type, quantity_changed, quantity_after, note, performed_by
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (inventory_id, action_type, quantity_changed, new_quantity, note, performed_by))
    db.commit()
    cur2.close()
    cur.close()
    db.close()
    return True, f"Stock updated for {item['medicine_name']}."


def dispense_prescription_stock(prescription_id, performed_by):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT p.id, p.medicine_name, p.dispense_status,
               pi.id AS inventory_id, pi.quantity_in_stock, pi.low_stock_threshold
        FROM prescriptions p
        LEFT JOIN pharmacy_inventory pi ON LOWER(pi.medicine_name) = LOWER(p.medicine_name)
        WHERE p.id=%s
        LIMIT 1
    """, (prescription_id,))
    prescription = cur.fetchone()
    if not prescription:
        cur.close()
        db.close()
        return False, "Prescription not found."
    if prescription["dispense_status"] == "dispensed":
        cur.close()
        db.close()
        return False, "This prescription has already been dispensed."
    if not prescription["inventory_id"]:
        cur.close()
        db.close()
        return False, "No matching medicine exists in pharmacy inventory."
    if (prescription["quantity_in_stock"] or 0) < 1:
        cur.close()
        db.close()
        return False, "This medicine is out of stock."

    new_quantity = prescription["quantity_in_stock"] - 1
    cur2 = db.cursor()
    cur2.execute("""
        UPDATE pharmacy_inventory
        SET quantity_in_stock=%s
        WHERE id=%s
    """, (new_quantity, prescription["inventory_id"]))
    cur2.execute("""
        INSERT INTO pharmacy_stock_movements (
            inventory_id, action_type, quantity_changed, quantity_after, note, performed_by
        )
        VALUES (%s, 'dispense', %s, %s, %s, %s)
    """, (
        prescription["inventory_id"],
        1,
        new_quantity,
        f"Prescription #{prescription_id} dispensed",
        performed_by
    ))
    cur2.execute("""
        UPDATE prescriptions
        SET dispense_status='dispensed', dispensed_at=%s, dispensed_by=%s
        WHERE id=%s
    """, (datetime.now(), performed_by, prescription_id))
    db.commit()
    cur2.close()
    cur.close()
    db.close()
    return True, f"{prescription['medicine_name']} dispensed successfully."


def doctor_has_approved_appointment(doctor_id, patient_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 1
        FROM appointments
        WHERE doctor_id=%s AND patient_id=%s AND status='approved'
        LIMIT 1
    """, (doctor_id, patient_id))
    allowed = cur.fetchone() is not None
    cur.close()
    db.close()
    return allowed


def doctor_has_medical_access(doctor_id, patient_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 1
        FROM access_requests
        WHERE doctor_id=%s
          AND patient_id=%s
          AND status='approved'
          AND prescription_written_at IS NULL
        LIMIT 1
    """, (doctor_id, patient_id))
    allowed = cur.fetchone() is not None
    cur.close()
    db.close()
    return allowed


def get_doctor_accessible_patients(doctor_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT DISTINCT u.id, u.name, u.email, u.age, u.gender, u.hashed_id
        FROM access_requests ar
        JOIN users u ON u.id = ar.patient_id
        WHERE ar.doctor_id=%s
          AND ar.status='approved'
          AND ar.prescription_written_at IS NULL
        ORDER BY u.name ASC
    """, (doctor_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_latest_booked_appointment(doctor_id, patient_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, appointment_date, status, created_at
        FROM appointments
        WHERE doctor_id=%s
          AND patient_id=%s
          AND status IN ('approved','completed')
        ORDER BY
            CASE WHEN appointment_date IS NULL THEN 1 ELSE 0 END,
            appointment_date DESC,
            created_at DESC
        LIMIT 1
    """, (doctor_id, patient_id))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def get_active_access_request_for_appointment(doctor_id, patient_id, appointment_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, status, requested_at, prescription_written_at
        FROM access_requests
        WHERE doctor_id=%s
          AND patient_id=%s
          AND appointment_id=%s
        ORDER BY requested_at DESC
        LIMIT 1
    """, (doctor_id, patient_id, appointment_id))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def get_patient_private_details(patient_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, name, email, age, gender, hashed_id
        FROM users
        WHERE id=%s AND role='patient'
        LIMIT 1
    """, (patient_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def get_chat_messages(patient_id, doctor_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT sender_id, sender_role, message_text, created_at
        FROM messages
        WHERE patient_id=%s AND doctor_id=%s
        ORDER BY created_at ASC, id ASC
    """, (patient_id, doctor_id))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def generate_hash(record_data):
    return hashlib.sha256((record_data or "").encode("utf-8")).hexdigest()


def safe_store_data_hash_onchain(data_hash, sender_role=None, sender_address=None):
    try:
        return store_data_hash_onchain(data_hash, sender_role=sender_role, sender_address=sender_address)
    except Exception as exc:
        raise RuntimeError(f"On-chain write failed: {exc}") from exc


def safe_store_payload_hash_onchain(payload_hash, sender_role=None, sender_address=None):
    try:
        return store_payload_hash_onchain(payload_hash, sender_role=sender_role, sender_address=sender_address)
    except Exception as exc:
        raise RuntimeError(f"On-chain write failed: {exc}") from exc


def safe_store_identity_hash_onchain(identity_hash, sender_role=None, sender_address=None):
    try:
        return store_identity_hash_onchain(identity_hash, sender_role=sender_role, sender_address=sender_address)
    except Exception as exc:
        raise RuntimeError(f"On-chain write failed: {exc}") from exc


def safe_store_record_hash_onchain(record_hash, sender_role=None, sender_address=None):
    return safe_store_payload_hash_onchain(record_hash, sender_role=sender_role, sender_address=sender_address)


def get_user_accessible_records(user_id, role):
    db = get_db()
    cur = db.cursor(dictionary=True)

    if role == "admin":
        cur.execute("""
            SELECT r.id, r.patient_id, r.encrypted_data, r.data_hash, r.blockchain_tx_hash, r.created_at,
                   u.name AS patient_name, u.email AS patient_email, u.age AS patient_age,
                   u.gender AS patient_gender, u.hashed_id AS patient_hashed_id,
                   u.wallet_address AS patient_wallet_address
            FROM records r
            JOIN users u ON u.id = r.patient_id
            ORDER BY r.created_at DESC, r.id DESC
        """)
    elif role == "patient":
        cur.execute("""
            SELECT r.id, r.patient_id, r.encrypted_data, r.data_hash, r.blockchain_tx_hash, r.created_at,
                   u.name AS patient_name, u.email AS patient_email, u.age AS patient_age,
                   u.gender AS patient_gender, u.hashed_id AS patient_hashed_id,
                   u.wallet_address AS patient_wallet_address
            FROM records r
            JOIN users u ON u.id = r.patient_id
            WHERE r.patient_id=%s
            ORDER BY r.created_at DESC, r.id DESC
        """, (user_id,))
    else:
        cur.execute("""
            SELECT DISTINCT r.id, r.patient_id, r.encrypted_data, r.data_hash, r.blockchain_tx_hash, r.created_at,
                   u.name AS patient_name, u.email AS patient_email, u.age AS patient_age,
                   u.gender AS patient_gender, u.hashed_id AS patient_hashed_id,
                   u.wallet_address AS patient_wallet_address
            FROM records r
            JOIN access_requests ar ON ar.patient_id = r.patient_id
            JOIN users u ON u.id = r.patient_id
            WHERE ar.doctor_id=%s
              AND ar.status='approved'
            ORDER BY r.created_at DESC, r.id DESC
        """, (user_id,))

    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_accessible_record_for_user(record_id, user_id, role):
    records = get_user_accessible_records(user_id, role)
    return next((record for record in records if record["id"] == record_id), None)


def get_accessible_record_for_patient(patient_id, user_id, role):
    records = get_user_accessible_records(user_id, role)
    return next((record for record in records if record["patient_id"] == patient_id), None)


def get_user_identity(user_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, role, name, email, hashed_id, wallet_address
        FROM users
        WHERE id=%s
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def get_latest_record_version(record_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, record_id, version_no, data_snapshot, data_hash, blockchain_tx_hash, updated_by, created_at
        FROM record_versions
        WHERE record_id=%s
        ORDER BY version_no DESC, id DESC
        LIMIT 1
    """, (record_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def get_previous_record_version(record_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, record_id, version_no, data_snapshot, data_hash, blockchain_tx_hash, updated_by, created_at
        FROM record_versions
        WHERE record_id=%s
        ORDER BY version_no DESC, id DESC
        LIMIT 1 OFFSET 1
    """, (record_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def get_record_versions(record_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT rv.id, rv.record_id, rv.version_no, rv.data_snapshot, rv.data_hash,
               rv.blockchain_tx_hash, rv.updated_by, rv.created_at,
               u.name AS updated_by_name
        FROM record_versions rv
        LEFT JOIN users u ON u.id = rv.updated_by
        WHERE rv.record_id=%s
        ORDER BY rv.version_no DESC, rv.id DESC
    """, (record_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_prescription_integrity_entries(patient_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT p.id, p.doctor_id, p.medicine_name, p.dosage, p.instructions,
               p.appointment_id, p.access_request_id, p.created_at,
               u.name AS doctor_name
        FROM prescriptions p
        LEFT JOIN users u ON u.id = p.doctor_id
        WHERE p.patient_id=%s
        ORDER BY p.created_at ASC, p.id ASC
    """, (patient_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_record_change_requests(record_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT rcr.id, rcr.record_id, rcr.version_no, rcr.requested_by, rcr.requester_role,
               rcr.payload_hash, rcr.proposed_snapshot, rcr.signer_key_id, rcr.signature_hash, rcr.signature_verified,
               rcr.blockchain_tx_hash, rcr.request_status, rcr.request_note,
               rcr.approval_threshold, rcr.accepted_nodes, rcr.rejected_nodes,
               rcr.broadcast_at, rcr.ledger_updated_at, rcr.finalized_at, rcr.created_at,
               u.name AS requested_by_name
        FROM record_change_requests rcr
        LEFT JOIN users u ON u.id = rcr.requested_by
        WHERE rcr.record_id=%s
        ORDER BY rcr.version_no DESC, rcr.id DESC
    """, (record_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def get_latest_record_change_request(record_id):
    requests = get_record_change_requests(record_id)
    return requests[0] if requests else None


def get_record_change_request_by_id(change_request_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT rcr.id, rcr.record_id, rcr.version_no, rcr.requested_by, rcr.requester_role,
               rcr.payload_hash, rcr.proposed_snapshot, rcr.signer_key_id, rcr.signature_hash, rcr.signature_verified,
               rcr.blockchain_tx_hash, rcr.request_status, rcr.request_note,
               rcr.approval_threshold, rcr.accepted_nodes, rcr.rejected_nodes,
               rcr.broadcast_at, rcr.ledger_updated_at, rcr.finalized_at, rcr.created_at,
               u.name AS requested_by_name
        FROM record_change_requests rcr
        LEFT JOIN users u ON u.id = rcr.requested_by
        WHERE rcr.id=%s
        LIMIT 1
    """, (change_request_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def get_pending_record_change_request(record_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT rcr.id, rcr.record_id, rcr.version_no, rcr.requested_by, rcr.requester_role,
               rcr.payload_hash, rcr.proposed_snapshot, rcr.signer_key_id, rcr.signature_hash, rcr.signature_verified,
               rcr.blockchain_tx_hash, rcr.request_status, rcr.request_note,
               rcr.approval_threshold, rcr.accepted_nodes, rcr.rejected_nodes,
               rcr.broadcast_at, rcr.ledger_updated_at, rcr.finalized_at, rcr.created_at,
               u.name AS requested_by_name
        FROM record_change_requests rcr
        LEFT JOIN users u ON u.id = rcr.requested_by
        WHERE rcr.record_id=%s
          AND rcr.request_status='broadcast'
        ORDER BY rcr.id DESC
        LIMIT 1
    """, (record_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def ensure_change_request_node_votes(change_request_id, record_id):
    db = get_db()
    cur = db.cursor()
    for node_name in INTEGRITY_NODE_NAMES:
        cur.execute("""
            INSERT INTO record_change_node_votes (
                change_request_id, record_id, node_name, identity_checked, identity_verified, vote_status, reviewed_at, note
            )
            VALUES (%s, %s, %s, 0, 0, 'pending', NULL, 'Awaiting identity verification')
            ON DUPLICATE KEY UPDATE node_name=node_name
        """, (change_request_id, record_id, node_name))
    db.commit()
    cur.close()
    db.close()


def get_change_request_node_votes(change_request_id):
    ensure_change_request_node_votes(change_request_id, get_record_change_request_by_id(change_request_id)["record_id"])
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, change_request_id, record_id, node_name, identity_checked, identity_verified,
               vote_status, reviewed_at, note
        FROM record_change_node_votes
        WHERE change_request_id=%s
        ORDER BY FIELD(node_name, 'Hospital Core Node', 'Doctor Node', 'Patient Node', 'Audit Node'), id ASC
    """, (change_request_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def build_change_request_material(record_id, version_no, payload_hash, actor):
    return json.dumps({
        "namespace": INTEGRITY_SIGNATURE_NAMESPACE,
        "record_id": record_id,
        "version_no": version_no,
        "payload_hash": payload_hash,
        "requested_by": actor["id"],
        "requester_role": actor["role"],
        "hashed_id": actor.get("hashed_id") or ""
    }, sort_keys=True, separators=(",", ":"))


def derive_signing_secret(actor):
    base_secret = app.config["SECRET_KEY"]
    secret_material = f"{base_secret}:{actor['id']}:{actor.get('hashed_id') or ''}:{actor['role']}"
    return hashlib.sha256(secret_material.encode("utf-8")).hexdigest()


def get_signer_key_id(actor):
    public_material = f"{actor['id']}:{actor['role']}:{actor.get('email') or ''}:{actor.get('hashed_id') or ''}"
    return hashlib.sha256(public_material.encode("utf-8")).hexdigest()[:24]


def sign_change_request(record_id, version_no, payload_hash, actor):
    payload = build_change_request_material(record_id, version_no, payload_hash, actor)
    signature_hash = hmac.new(
        derive_signing_secret(actor).encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return {
        "payload": payload,
        "signature_hash": signature_hash,
        "signer_key_id": get_signer_key_id(actor)
    }


def verify_change_request_signature(record_id, version_no, payload_hash, actor, signature_hash):
    expected = sign_change_request(record_id, version_no, payload_hash, actor)
    return hmac.compare_digest(expected["signature_hash"], signature_hash)


def create_record_change_request(record, version_no, payload_hash, blockchain_tx_hash, actor, proposed_snapshot=None, request_status="ledger_anchored", request_note=None):
    signed_request = sign_change_request(record["id"], version_no, payload_hash, actor)
    signature_verified = verify_change_request_signature(
        record["id"], version_no, payload_hash, actor, signed_request["signature_hash"]
    )
    now = datetime.now()
    note = request_note
    if not note:
        if request_status == "broadcast":
            note = "Signed change request is waiting for node identity checks and Accept/Reject votes."
        elif actor["role"] == "doctor":
            note = "Doctor-signed change request broadcast to validator nodes."
        else:
            note = "System-generated integrity sync request."

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO record_change_requests (
            record_id, version_no, requested_by, requester_role, payload_hash, proposed_snapshot,
            signer_key_id, signature_hash, signature_verified, blockchain_tx_hash,
            request_status, request_note, approval_threshold, accepted_nodes, rejected_nodes,
            broadcast_at, ledger_updated_at, finalized_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        record["id"],
        version_no,
        actor["id"],
        actor["role"],
        payload_hash,
        proposed_snapshot,
        signed_request["signer_key_id"],
        signed_request["signature_hash"],
        1 if signature_verified else 0,
        blockchain_tx_hash,
        request_status if signature_verified else "rejected",
        note,
        INTEGRITY_CONSENSUS_THRESHOLD,
        0,
        0,
        now,
        now if signature_verified and request_status == "ledger_anchored" else None,
        now if signature_verified and request_status == "ledger_anchored" else None
    ))
    request_id = cur.lastrowid
    db.commit()
    cur.close()
    db.close()
    ensure_change_request_node_votes(request_id, record["id"])

    signed_request.update({
        "id": request_id,
        "signature_verified": signature_verified,
        "broadcast_at": now,
        "ledger_updated_at": now if signature_verified and request_status == "ledger_anchored" else None,
        "finalized_at": now if signature_verified and request_status == "ledger_anchored" else None,
        "request_status": request_status if signature_verified else "rejected",
        "requested_by_name": actor.get("name"),
        "requested_by": actor["id"],
        "requester_role": actor["role"],
        "payload_hash": payload_hash,
        "proposed_snapshot": proposed_snapshot,
        "blockchain_tx_hash": blockchain_tx_hash,
        "approval_threshold": INTEGRITY_CONSENSUS_THRESHOLD,
        "accepted_nodes": 0,
        "rejected_nodes": 0,
        "request_note": note
    })
    return signed_request


def build_sensitive_record_snapshot(record, encrypted_payload=None):
    prescriptions = []
    for item in get_prescription_integrity_entries(record["patient_id"]):
        prescriptions.append({
            "id": item["id"],
            "doctor_id": item["doctor_id"],
            "doctor_name": item.get("doctor_name") or "",
            "medicine_name": item["medicine_name"],
            "dosage": item["dosage"],
            "instructions": item["instructions"],
            "appointment_id": item["appointment_id"],
            "access_request_id": item["access_request_id"],
            "created_at": item["created_at"].isoformat() if item.get("created_at") else None
        })

    snapshot = {
        "patient_name": record.get("patient_name") or "",
        "patient_email": record.get("patient_email") or "",
        "patient_age": record.get("patient_age"),
        "patient_gender": record.get("patient_gender") or "",
        "patient_hashed_id": record.get("patient_hashed_id") or "",
        "patient_wallet_address": record.get("patient_wallet_address") or "",
        "encrypted_data": decrypt_record_payload(
            encrypted_payload if encrypted_payload is not None else (record.get("encrypted_data") or "")
        ),
        "prescriptions": prescriptions
    }
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"))


def ensure_record_payloads_encrypted():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, encrypted_data
        FROM records
        WHERE encrypted_data IS NOT NULL
          AND encrypted_data <> ''
          AND encrypted_data NOT LIKE %s
    """, (f"{RECORD_ENCRYPTION_PREFIX}%",))
    rows = cur.fetchall()
    cur.close()

    if not rows:
        db.close()
        return 0

    update_cur = db.cursor()
    updated_count = 0
    for row in rows:
        update_cur.execute(
            """
            UPDATE records
            SET encrypted_data=%s
            WHERE id=%s
            """,
            (encrypt_record_payload(row["encrypted_data"]), row["id"])
        )
        updated_count += 1

    db.commit()
    update_cur.close()
    db.close()
    return updated_count


def ensure_record_version_seed(record):
    latest_version = get_latest_record_version(record["id"])
    if latest_version:
        if not get_latest_record_change_request(record["id"]):
            actor = get_user_identity(record["patient_id"]) or {
                "id": record["patient_id"],
                "role": "patient",
                "name": record.get("patient_name"),
                "email": record.get("patient_email"),
                "hashed_id": record.get("patient_hashed_id")
            }
            create_record_change_request(record, latest_version["version_no"], latest_version["data_hash"], latest_version["blockchain_tx_hash"], actor)
        return latest_version

    seed_snapshot = build_sensitive_record_snapshot(record)
    seed_hash = generate_hash(seed_snapshot)

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO record_versions (
            record_id, version_no, data_snapshot, data_hash, blockchain_tx_hash, updated_by
        )
        VALUES (%s, 1, %s, %s, %s, %s)
    """, (
        record["id"],
        seed_snapshot,
        seed_hash,
        record["blockchain_tx_hash"],
        record["patient_id"]
    ))
    cur.execute("""
        UPDATE records
        SET data_hash=%s
        WHERE id=%s
    """, (seed_hash, record["id"]))
    db.commit()
    cur.close()
    db.close()
    actor = get_user_identity(record["patient_id"]) or {
        "id": record["patient_id"],
        "role": "patient",
        "name": record.get("patient_name"),
        "email": record.get("patient_email"),
        "hashed_id": record.get("patient_hashed_id")
    }
    create_record_change_request(record, 1, seed_hash, record["blockchain_tx_hash"], actor)
    return get_latest_record_version(record["id"])


def ensure_simulation_row(record_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO integrity_simulations (record_id, tamper_enabled, tampered_payload, updated_at)
        VALUES (%s, 0, NULL, %s)
        ON DUPLICATE KEY UPDATE updated_at = updated_at
    """, (record_id, datetime.now()))
    db.commit()
    cur.close()
    db.close()


def get_simulation_state(record_id):
    ensure_simulation_row(record_id)
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT record_id, tamper_enabled, tampered_payload, updated_at
        FROM integrity_simulations
        WHERE record_id=%s
        LIMIT 1
    """, (record_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def ensure_integrity_node_rows(record_id, base_hash, base_version_no=1):
    db = get_db()
    cur = db.cursor()
    for node_name in INTEGRITY_NODE_NAMES:
        cur.execute("""
            INSERT INTO integrity_node_states (
                record_id, node_name, behavior_mode, status, last_seen_hash, last_verification_time, status_note,
                local_version_no, last_blockchain_hash, signature_verified, sync_status, last_broadcast_at
            )
            VALUES (%s, %s, 'normal', 'pending', %s, NULL, NULL, %s, %s, 0, 'pending', NULL)
            ON DUPLICATE KEY UPDATE node_name = node_name
        """, (record_id, node_name, base_hash, base_version_no, base_hash))
    db.commit()
    cur.close()
    db.close()


def get_integrity_node_rows(record_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, record_id, node_name, behavior_mode, status, last_seen_hash, last_verification_time, status_note,
               local_version_no, last_blockchain_hash, signature_verified, sync_status, last_broadcast_at
        FROM integrity_node_states
        WHERE record_id=%s
        ORDER BY FIELD(node_name, 'Hospital Core Node', 'Doctor Node', 'Patient Node', 'Audit Node'), id ASC
    """, (record_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return rows


def set_node_behavior(record_id, node_name, behavior_mode):
    if node_name not in INTEGRITY_NODE_NAMES:
        return

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE integrity_node_states
        SET behavior_mode = CASE WHEN behavior_mode=%s THEN 'normal' ELSE %s END
        WHERE record_id=%s AND node_name=%s
    """, (behavior_mode, behavior_mode, record_id, node_name))
    db.commit()
    cur.close()
    db.close()


def clear_integrity_node_behaviors(record_id, new_hash=None):
    db = get_db()
    cur = db.cursor()
    if new_hash:
        cur.execute("""
            UPDATE integrity_node_states
            SET behavior_mode='normal',
                status='pending',
                last_seen_hash=%s,
                last_verification_time=%s,
                status_note='Node synchronized to latest version',
                last_blockchain_hash=%s,
                signature_verified=1,
                sync_status='synced',
                last_broadcast_at=%s
            WHERE record_id=%s
        """, (new_hash, datetime.now(), new_hash, datetime.now(), record_id))
    else:
        cur.execute("""
            UPDATE integrity_node_states
            SET behavior_mode='normal',
                status='pending',
                status_note=NULL,
                sync_status='pending'
            WHERE record_id=%s
        """, (record_id,))
    db.commit()
    cur.close()
    db.close()


def open_pending_change_request(record, actor):
    existing_pending = get_pending_record_change_request(record["id"])
    latest_version = ensure_record_version_seed(record)
    next_version_no = latest_version["version_no"] + 1
    proposed_snapshot = build_sensitive_record_snapshot(record)
    proposed_hash = generate_hash(proposed_snapshot)

    if existing_pending:
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            UPDATE record_change_requests
            SET version_no=%s,
                payload_hash=%s,
                proposed_snapshot=%s,
                signer_key_id=%s,
                signature_hash=%s,
                signature_verified=%s,
                request_note='Signed change request is waiting for node identity checks and Accept/Reject votes.',
                accepted_nodes=0,
                rejected_nodes=0,
                broadcast_at=%s,
                ledger_updated_at=NULL,
                finalized_at=NULL
            WHERE id=%s
        """, (
            next_version_no,
            proposed_hash,
            proposed_snapshot,
            sign_change_request(record["id"], next_version_no, proposed_hash, actor)["signer_key_id"],
            sign_change_request(record["id"], next_version_no, proposed_hash, actor)["signature_hash"],
            1,
            datetime.now(),
            existing_pending["id"]
        ))
        cur.execute("""
            DELETE FROM record_change_node_votes
            WHERE change_request_id=%s
        """, (existing_pending["id"],))
        db.commit()
        cur.close()
        db.close()
        ensure_change_request_node_votes(existing_pending["id"], record["id"])
        return get_record_change_request_by_id(existing_pending["id"])

    change_request = create_record_change_request(
        record,
        next_version_no,
        proposed_hash,
        None,
        actor,
        proposed_snapshot=proposed_snapshot,
        request_status="broadcast"
    )

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE integrity_node_states
        SET status='pending',
            status_note='Awaiting Check Identity and Accept/Reject review for the latest doctor-signed change request.',
            signature_verified=0,
            sync_status='pending',
            last_broadcast_at=%s
        WHERE record_id=%s
    """, (change_request["broadcast_at"], record["id"]))
    db.commit()
    cur.close()
    db.close()
    return get_record_change_request_by_id(change_request["id"])


def node_can_verify_identity(node_name, behavior_mode):
    if node_name not in INTEGRITY_NODE_NAMES:
        return False, "Unknown node."
    if behavior_mode == "offline":
        return False, "Node is offline and cannot verify the doctor identity right now."
    if behavior_mode == "compromised":
        return False, "Compromised node returned an untrusted identity verification result."
    return True, "Doctor identity and signature verified."


def update_change_request_counts(change_request_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT
            SUM(CASE WHEN vote_status='accepted' THEN 1 ELSE 0 END) AS accepted_nodes,
            SUM(CASE WHEN vote_status='rejected' THEN 1 ELSE 0 END) AS rejected_nodes
        FROM record_change_node_votes
        WHERE change_request_id=%s
    """, (change_request_id,))
    counts = cur.fetchone() or {}
    accepted_nodes = counts.get("accepted_nodes") or 0
    rejected_nodes = counts.get("rejected_nodes") or 0
    cur.close()

    cur = db.cursor()
    cur.execute("""
        UPDATE record_change_requests
        SET accepted_nodes=%s,
            rejected_nodes=%s
        WHERE id=%s
    """, (accepted_nodes, rejected_nodes, change_request_id))
    db.commit()
    cur.close()
    db.close()
    return accepted_nodes, rejected_nodes


def finalize_change_request_if_threshold_met(record, change_request):
    total_nodes = len(INTEGRITY_NODE_NAMES)
    accepted_nodes, rejected_nodes = update_change_request_counts(change_request["id"])
    accepted_percentage = round((accepted_nodes / total_nodes) * 100, 2) if total_nodes else 0
    max_possible_percentage = round(((total_nodes - rejected_nodes) / total_nodes) * 100, 2) if total_nodes else 0

    if accepted_percentage >= (change_request.get("approval_threshold") or INTEGRITY_CONSENSUS_THRESHOLD):
        latest_version = ensure_record_version_seed(record)
        requester_identity = get_user_identity(change_request["requested_by"]) or {}
        new_tx_hash = safe_store_data_hash_onchain(
            change_request["payload_hash"],
            sender_role=requester_identity.get("role"),
            sender_address=requester_identity.get("wallet_address")
        )
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO record_versions (
                record_id, version_no, data_snapshot, data_hash, blockchain_tx_hash, updated_by
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            record["id"],
            change_request["version_no"],
            change_request["proposed_snapshot"] or build_sensitive_record_snapshot(record),
            change_request["payload_hash"],
            new_tx_hash,
            change_request["requested_by"]
        ))
        cur.execute("""
            UPDATE records
            SET data_hash=%s,
                blockchain_tx_hash=%s
            WHERE id=%s
        """, (change_request["payload_hash"], new_tx_hash, record["id"]))
        cur.execute("""
            UPDATE integrity_simulations
            SET tamper_enabled=0,
                tampered_payload=NULL,
                updated_at=%s
            WHERE record_id=%s
        """, (datetime.now(), record["id"]))
        cur.execute("""
            UPDATE record_change_requests
            SET request_status='ledger_anchored',
                blockchain_tx_hash=%s,
                ledger_updated_at=%s,
                finalized_at=%s,
                request_note='Consensus threshold reached. Trusted ledger updated and version synchronized.'
            WHERE id=%s
        """, (new_tx_hash, datetime.now(), datetime.now(), change_request["id"]))
        db.commit()
        cur.close()
        db.close()

        anchored_request = get_record_change_request_by_id(change_request["id"])
        broadcast_change_request_to_nodes(record, anchored_request["version_no"], anchored_request["payload_hash"], anchored_request)
        return anchored_request

    if max_possible_percentage < (change_request.get("approval_threshold") or INTEGRITY_CONSENSUS_THRESHOLD):
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            UPDATE record_change_requests
            SET request_status='rejected',
                finalized_at=%s,
                request_note='Consensus threshold can no longer be reached because too many nodes rejected the change.'
            WHERE id=%s
        """, (datetime.now(), change_request["id"]))
        cur.execute("""
            UPDATE integrity_node_states
            SET status='mismatch',
                sync_status='rejected',
                status_note='Node poll rejected the pending doctor update before it reached the trusted ledger.'
            WHERE record_id=%s
              AND node_name IN (
                  SELECT node_name
                  FROM record_change_node_votes
                  WHERE change_request_id=%s AND vote_status='rejected'
              )
        """, (record["id"], change_request["id"]))
        db.commit()
        cur.close()
        db.close()
        return get_record_change_request_by_id(change_request["id"])

    return get_record_change_request_by_id(change_request["id"])


def toggle_record_tamper(record):
    ensure_simulation_row(record["id"])
    simulation = get_simulation_state(record["id"])
    tamper_enabled = bool(simulation["tamper_enabled"])
    tampered_payload = None

    if not tamper_enabled:
        tampered_record_payload = (
            f"{record['encrypted_data']} :: tampered-copy :: {datetime.now().isoformat()} :: "
            f"{secrets.token_hex(6)}"
        )
        tampered_payload = build_sensitive_record_snapshot(record, tampered_record_payload)

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE integrity_simulations
        SET tamper_enabled=%s,
            tampered_payload=%s,
            updated_at=%s
        WHERE record_id=%s
    """, (0 if tamper_enabled else 1, tampered_payload, datetime.now(), record["id"]))
    db.commit()
    cur.close()
    db.close()


def get_simulated_record_payload(record, simulation):
    if simulation and simulation.get("tamper_enabled") and simulation.get("tampered_payload"):
        return simulation["tampered_payload"]
    return build_sensitive_record_snapshot(record)


def verify_against_blockchain(current_hash, blockchain_hash):
    return current_hash == blockchain_hash


def persist_node_verification_results(record_id, node_results):
    db = get_db()
    cur = db.cursor()
    for node in node_results:
        cur.execute("""
            UPDATE integrity_node_states
            SET status=%s,
                last_seen_hash=%s,
                last_verification_time=%s,
                status_note=%s
            WHERE record_id=%s AND node_name=%s
        """, (
            node["status"],
            node["last_seen_hash"],
            node["last_verification_time"],
            node["status_note"],
            record_id,
            node["node_name"]
        ))
    db.commit()
    cur.close()
    db.close()


def broadcast_change_request_to_nodes(record, version_no, ledger_hash, change_request):
    ensure_integrity_node_rows(record["id"], ledger_hash, version_no)
    node_rows = get_integrity_node_rows(record["id"])
    previous_version = get_previous_record_version(record["id"])
    previous_hash = previous_version["data_hash"] if previous_version else ledger_hash
    previous_version_no = previous_version["version_no"] if previous_version else max(version_no - 1, 1)
    now = datetime.now()

    db = get_db()
    cur = db.cursor()
    for node in node_rows:
        behavior_mode = node["behavior_mode"]
        sync_status = "synced"
        status = "pending"
        last_seen_hash = ledger_hash
        local_version_no = version_no
        last_blockchain_hash = ledger_hash
        signature_verified = 1 if change_request["signature_verified"] else 0
        status_note = "Node received the signed update broadcast and synchronized to the new ledger hash."

        if behavior_mode == "offline":
            sync_status = "offline"
            status = "offline"
            last_seen_hash = node.get("last_seen_hash") or previous_hash
            local_version_no = node.get("local_version_no") or previous_version_no
            last_blockchain_hash = node.get("last_blockchain_hash") or previous_hash
            signature_verified = 0
            status_note = "Node was offline during the broadcast and did not receive the newest ledger update."
        elif behavior_mode == "delayed":
            sync_status = "stale"
            status = "delayed"
            last_seen_hash = previous_hash
            local_version_no = previous_version_no
            last_blockchain_hash = previous_hash
            status_note = "Node kept an older local copy and is still waiting to catch up with the new ledger hash."
        elif behavior_mode == "compromised":
            sync_status = "compromised"
            status = "compromised"
            last_seen_hash = generate_hash(f"{ledger_hash}:{node['node_name']}:compromised")
            last_blockchain_hash = ledger_hash
            signature_verified = 0
            status_note = "Compromised node received the broadcast but returned an untrusted acknowledgement."

        cur.execute("""
            UPDATE integrity_node_states
            SET status=%s,
                last_seen_hash=%s,
                last_verification_time=%s,
                status_note=%s,
                local_version_no=%s,
                last_blockchain_hash=%s,
                signature_verified=%s,
                sync_status=%s,
                last_broadcast_at=%s
            WHERE record_id=%s AND node_name=%s
        """, (
            status,
            last_seen_hash,
            now,
            status_note,
            local_version_no,
            last_blockchain_hash,
            signature_verified,
            sync_status,
            change_request["broadcast_at"],
            record["id"],
            node["node_name"]
        ))
    db.commit()
    cur.close()
    db.close()


def simulate_node_states(record, latest_version, current_hash, blockchain_hash):
    ensure_integrity_node_rows(record["id"], latest_version["data_hash"], latest_version["version_no"])
    node_rows = get_integrity_node_rows(record["id"])
    previous_version = get_previous_record_version(record["id"])
    verified_at = datetime.now()
    results = []

    for node in node_rows:
        behavior_mode = node["behavior_mode"]
        last_seen_hash = node.get("last_seen_hash") or current_hash
        status = "valid"
        status_note = "Node verified the live database hash against the blockchain reference."
        sync_status = node.get("sync_status") or "pending"
        local_version_no = node.get("local_version_no") or latest_version["version_no"]
        signature_verified = bool(node.get("signature_verified"))

        if behavior_mode == "offline":
            status = "offline"
            last_seen_hash = node["last_seen_hash"] or latest_version["data_hash"]
            status_note = "Node is currently unavailable and did not cast a vote on the latest signed update."
        elif behavior_mode == "delayed":
            status = "delayed"
            last_seen_hash = node["last_seen_hash"] or (previous_version["data_hash"] if previous_version else latest_version["data_hash"])
            if previous_version:
                status_note = f"Node is still holding version {local_version_no} instead of the newest signed version {latest_version['version_no']}."
            else:
                status_note = "Node is marked delayed, but no older version snapshot exists yet."
        elif behavior_mode == "compromised":
            status = "compromised"
            last_seen_hash = node["last_seen_hash"] or generate_hash(f"{current_hash}-{node['node_name']}-compromised")
            status_note = "Node returned a hostile or untrusted integrity vote after the broadcast."
        elif not verify_against_blockchain(current_hash, blockchain_hash):
            status = "mismatch"
            last_seen_hash = current_hash
            status_note = "Node detected that the current database hash does not match the blockchain reference."
        elif sync_status == "stale":
            status = "delayed"
            status_note = f"Node has not applied the latest ledger-backed version yet and is still serving version {local_version_no}."
        elif sync_status == "rejected":
            status = "mismatch"
            status_note = "Node rejected the signed change request because the signature or payload could not be trusted."

        if status == "valid" and signature_verified:
            status_note = f"{status_note} Doctor signature verified for version {latest_version['version_no']}."

        results.append({
            "node_name": node["node_name"],
            "behavior_mode": behavior_mode,
            "status": status,
            "last_seen_hash": last_seen_hash,
            "last_verification_time": verified_at,
            "status_note": status_note,
            "local_version_no": local_version_no,
            "last_blockchain_hash": node.get("last_blockchain_hash") or blockchain_hash,
            "signature_verified": signature_verified,
            "sync_status": sync_status,
            "last_broadcast_at": node.get("last_broadcast_at")
        })

    persist_node_verification_results(record["id"], results)
    return results


def build_integrity_snapshot(record, user_id):
    latest_version = ensure_record_version_seed(record)
    previous_version = get_previous_record_version(record["id"])
    simulation = get_simulation_state(record["id"])
    ensure_integrity_node_rows(record["id"], latest_version["data_hash"], latest_version["version_no"])
    latest_change_request = get_latest_record_change_request(record["id"])
    pending_change_request = get_pending_record_change_request(record["id"])

    live_payload = get_simulated_record_payload(record, simulation)
    current_db_hash = generate_hash(live_payload)
    blockchain_hash = latest_version["data_hash"] or record["data_hash"]
    blockchain_source = "database mirror"
    latest_writer = get_user_identity(latest_version.get("updated_by")) if latest_version else None
    onchain_wallets = []
    if latest_writer and latest_writer.get("wallet_address"):
        onchain_wallets.append(latest_writer["wallet_address"])
    if record.get("patient_wallet_address") and record["patient_wallet_address"] not in onchain_wallets:
        onchain_wallets.append(record["patient_wallet_address"])

    for wallet_address in onchain_wallets:
        try:
            onchain_hash = get_latest_record_hash(wallet_address)
        except Exception:
            onchain_hash = None
        if onchain_hash:
            blockchain_hash = onchain_hash
            blockchain_source = f"ganache:{wallet_address}"
            break

    node_results = simulate_node_states(record, latest_version, current_db_hash, blockchain_hash)

    vote_map = {}
    if pending_change_request:
        for vote in get_change_request_node_votes(pending_change_request["id"]):
            vote_map[vote["node_name"]] = vote

    for node in node_results:
        vote = vote_map.get(node["node_name"])
        node["identity_checked"] = bool(vote["identity_checked"]) if vote else False
        node["identity_verified"] = bool(vote["identity_verified"]) if vote else False
        node["vote_status"] = vote["vote_status"] if vote else "pending"
        node["reviewed_at"] = vote["reviewed_at"] if vote else None
        node["can_poll"] = bool(pending_change_request and pending_change_request["request_status"] == "broadcast")

    total_nodes = len(node_results)
    valid_nodes = sum(1 for node in node_results if node["status"] == "valid")
    valid_percentage = round((valid_nodes / total_nodes) * 100, 2) if total_nodes else 0
    final_status = "VALID" if valid_percentage >= INTEGRITY_CONSENSUS_THRESHOLD else "COMPROMISED"
    database_change_detected = not verify_against_blockchain(current_db_hash, blockchain_hash)
    database_change_state = "DETECTED" if database_change_detected else "CLEAR"
    database_change_message = (
        "Live database payload changed and no longer matches the trusted ledger hash."
        if database_change_detected
        else "Live database payload still matches the trusted ledger hash."
    )
    old_trusted_hash = previous_version["data_hash"] if previous_version else latest_version["data_hash"]
    approved_new_hash = latest_version["data_hash"] if previous_version else None
    proposed_new_hash = pending_change_request["payload_hash"] if pending_change_request else (
        latest_change_request["payload_hash"] if latest_change_request and latest_change_request["request_status"] == "ledger_anchored" else None
    )

    return {
        "record": record,
        "latest_version": latest_version,
        "previous_version": previous_version,
        "versions": get_record_versions(record["id"]),
        "change_requests": get_record_change_requests(record["id"]),
        "latest_change_request": latest_change_request,
        "pending_change_request": pending_change_request,
        "simulation": simulation,
        "current_payload": live_payload,
        "current_db_hash": current_db_hash,
        "blockchain_hash": blockchain_hash,
        "blockchain_source": blockchain_source,
        "blockchain_tx_hash": latest_version["blockchain_tx_hash"] or record["blockchain_tx_hash"],
        "hash_match": verify_against_blockchain(current_db_hash, blockchain_hash),
        "node_results": node_results,
        "valid_nodes": valid_nodes,
        "total_nodes": total_nodes,
        "valid_percentage": valid_percentage,
        "consensus_threshold": INTEGRITY_CONSENSUS_THRESHOLD,
        "final_status": final_status,
        "tamper_enabled": bool(simulation["tamper_enabled"]) if simulation else False,
        "database_change_detected": database_change_detected,
        "database_change_state": database_change_state,
        "database_change_message": database_change_message,
        "verified_at": datetime.now(),
        "current_version_no": latest_version["version_no"],
        "ledger_status": "SYNCED" if latest_change_request and latest_change_request["request_status"] == "ledger_anchored" else ("POLLING" if pending_change_request else "PENDING"),
        "signature_status": "VERIFIED" if latest_change_request and latest_change_request["signature_verified"] else ("CHECK REQUIRED" if pending_change_request else "UNVERIFIED"),
        "old_trusted_hash": old_trusted_hash,
        "approved_new_hash": approved_new_hash,
        "proposed_new_hash": proposed_new_hash
    }


def create_new_record_version(record, updated_by):
    actor = get_user_identity(updated_by) or {
        "id": updated_by,
        "role": session.get("role", "system"),
        "name": session.get("name", "Unknown User"),
        "email": "",
        "hashed_id": session.get("hashed_id", "")
    }
    ensure_simulation_row(record["id"])
    return open_pending_change_request(record, actor)


ensure_messages_table()
ensure_appointments_table()
ensure_prescriptions_table()
ensure_pharmacy_tables()
ensure_access_request_cycle_columns()
ensure_prescription_dispense_columns()
ensure_user_sessions_table()
ensure_doctor_avatar_column()
ensure_record_versions_table()
ensure_record_payloads_encrypted()
ensure_integrity_node_states_table()
ensure_integrity_simulations_table()
ensure_record_change_requests_table()
ensure_record_change_node_votes_table()
cleanup_demo_pending_requests()
ensure_demo_pending_change_request()




def log_action(user_id, action, ip):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO audit_logs(user_id, action, ip_address) VALUES (%s,%s,%s)",
        (user_id, action, ip)
    )
    db.commit()
    cur.close()
    db.close()




def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


def hash_session_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clear_authenticated_session_state():
    for key in AUTH_SESSION_KEYS:
        session.pop(key, None)


def revoke_auth_session_by_token(token):
    if not token:
        return

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE user_sessions
        SET is_revoked = 1,
            revoked_at = %s
        WHERE session_token_hash = %s
          AND is_revoked = 0
    """, (datetime.now(), hash_session_token(token)))
    db.commit()
    cur.close()
    db.close()


def revoke_current_auth_session():
    revoke_auth_session_by_token(session.get(AUTH_SESSION_COOKIE_KEY))


def create_authenticated_session(user, login_method):
    revoke_current_auth_session()
    clear_authenticated_session_state()

    raw_session_token = secrets.token_urlsafe(32)
    now = datetime.now()

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO user_sessions (
            session_token_hash, user_id, role, user_name, hashed_id,
            login_method, ip_address, user_agent, created_at, last_seen_at,
            expires_at, is_revoked
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
    """, (
        hash_session_token(raw_session_token),
        user["id"],
        user["role"],
        user["name"],
        user["hashed_id"],
        login_method,
        get_client_ip(),
        request.headers.get("User-Agent"),
        now,
        now,
        now + AUTH_ABSOLUTE_TIMEOUT
    ))
    db.commit()
    cur.close()
    db.close()

    session[AUTH_SESSION_COOKIE_KEY] = raw_session_token
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["name"] = user["name"]
    session["hashed_id"] = user["hashed_id"]
    session.permanent = True


def load_authenticated_session():
    raw_session_token = session.get(AUTH_SESSION_COOKIE_KEY)
    if not raw_session_token:
        return False

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT user_id, role, user_name, hashed_id, created_at, last_seen_at, expires_at, is_revoked
        FROM user_sessions
        WHERE session_token_hash = %s
        LIMIT 1
    """, (hash_session_token(raw_session_token),))
    auth_session = cur.fetchone()

    if not auth_session or auth_session["is_revoked"]:
        cur.close()
        db.close()
        clear_authenticated_session_state()
        return False

    now = datetime.now()
    last_seen_at = auth_session["last_seen_at"] or auth_session["created_at"]
    is_idle_expired = (now - last_seen_at) > AUTH_IDLE_TIMEOUT
    is_absolute_expired = now > auth_session["expires_at"]

    if is_idle_expired or is_absolute_expired:
        cur.close()
        db.close()
        revoke_auth_session_by_token(raw_session_token)
        clear_authenticated_session_state()
        return False

    cur2 = db.cursor()
    cur2.execute("""
        UPDATE user_sessions
        SET last_seen_at = %s
        WHERE session_token_hash = %s
          AND is_revoked = 0
    """, (now, hash_session_token(raw_session_token)))
    db.commit()
    cur2.close()
    cur.close()
    db.close()

    session["user_id"] = auth_session["user_id"]
    session["role"] = auth_session["role"]
    session["name"] = auth_session["user_name"]
    session["hashed_id"] = auth_session["hashed_id"]
    session.permanent = True
    return True


@app.before_request
def hydrate_authenticated_user():
    if request.endpoint == "static":
        return

    if AUTH_SESSION_COOKIE_KEY in session:
        load_authenticated_session()


@app.context_processor
def inject_session_timeout():
    return {
        "auth_idle_timeout_seconds": int(AUTH_IDLE_TIMEOUT.total_seconds())
    }




def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS




def save_uploaded_file(file_obj, prefix):
    if not file_obj or file_obj.filename == "":
        return None


    if not allowed_file(file_obj.filename):
        return None


    ext = file_obj.filename.rsplit(".", 1)[1].lower()
    safe_name = secure_filename(f"{prefix}_{secrets.token_hex(8)}.{ext}")
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    file_obj.save(save_path)


    return save_path.replace("\\", "/")


def post_login_redirect():
    if session.get("role") == "admin":
        return url_for("integrity_dashboard")
    if session.get("role") == "storage":
        return url_for("storage_dashboard")
    if session.get("role") == "doctor":
        return url_for("dashboard")
    return url_for("patient_home")


def build_approval_tx_hash(patient_hash_hex):
    if USE_BLOCKCHAIN_FOR_APPROVALS:
        return store_identity_hash_onchain(patient_hash_hex)
    return f"demo-tx-{secrets.token_hex(10)}"


def get_prescription_for_patient(prescription_id, patient_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT p.id, p.patient_id, p.doctor_id, p.appointment_id, p.access_request_id,
               p.medicine_name, p.dosage, p.instructions, p.created_at,
               u.name AS doctor_name, u.email AS doctor_email
        FROM prescriptions p
        JOIN users u ON u.id = p.doctor_id
        WHERE p.id = %s
          AND p.patient_id = %s
        LIMIT 1
    """, (prescription_id, patient_id))
    row = cur.fetchone()
    cur.close()
    db.close()
    return row


def sanitize_chat_history(raw_history):
    safe_history = []
    if not isinstance(raw_history, list):
        return safe_history

    for item in raw_history[-8:]:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        safe_history.append({
            "role": role,
            "content": content[:800]
        })
    return safe_history


def build_prescription_ai_system_prompt(prescription):
    return f"""
You are a lightweight healthcare education assistant inside an e-health patient portal.
You only answer simple, general prescription-related questions.

Prescription context:
- Medicine: {prescription['medicine_name']}
- Dosage: {prescription['dosage']}
- Instructions: {prescription['instructions']}
- Prescribing doctor: {prescription['doctor_name']}

Rules:
- Keep answers very short: 1 to 3 sentences.
- Sound like a normal chat reply, not a report or article.
- Focus on general explanation, common usage information, precautions, side effects, and similar medicines.
- If the question is outside the prescription context, clearly say you are here for consultation purposes only about the prescription and ask the patient to contact their doctor for other topics.
- Do not diagnose, do not change dosage, and do not tell the patient to stop or start medicine without a doctor.
- If the user asks something risky or very specific, tell them to contact their doctor or pharmacist.
- Avoid long explanations, bullet points, or extra background.
- If the answer is unclear, ask one short follow-up question.
""".strip()


def build_ollama_prescription_messages(prescription, question, chat_history):
    messages = [
        {
            "role": "system",
            "content": build_prescription_ai_system_prompt(prescription) + (
                "\nAnswer in a short chat style. Start with a direct yes/no/maybe when possible, "
                "then give one short explanation. Do not use long paragraphs."
            )
        }
    ]

    for item in chat_history[-6:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:1000]})

    messages.append({"role": "user", "content": question})
    return messages


def call_ollama_prescription_reply(prescription, question, chat_history):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": build_ollama_prescription_messages(prescription, question, chat_history),
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    request_obj = urllib_request.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=60) as response:
            raw_response = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Ollama API error: {exc.code} {error_body[:240]}") from exc

    response_data = json.loads(raw_response)
    reply_text = (response_data.get("message") or {}).get("content", "").strip()
    if not reply_text:
        raise RuntimeError("Ollama API returned an empty message")

    return reply_text


def is_prescription_question_in_scope(prescription, question):
    lower_question = (question or "").lower()
    medicine_name = (prescription.get("medicine_name") or "").lower()
    dosage = (prescription.get("dosage") or "").lower()
    instructions = (prescription.get("instructions") or "").lower()

    scope_keywords = [
        medicine_name,
        dosage,
        instructions,
        "prescription",
        "medicine",
        "medication",
        "drug",
        "tablet",
        "capsule",
        "syrup",
        "dose",
        "dosage",
        "instruction",
        "instructions",
        "usage",
        "use",
        "used for",
        "what is this for",
        "purpose",
        "side effect",
        "side effects",
        "similar",
        "alternative",
        "precaution",
        "precautions",
        "warning",
        "warnings",
        "avoid",
        "safe",
        "how do i take",
        "when do i take"
    ]

    natural_medical_phrases = [
        "can i", "should i", "is it okay", "is it ok", "is this safe", "what if i",
        "what happens if", "how do i", "when should i", "when do i", "can i take",
        "can i use", "is it fine", "do i need", "is there", "how long", "how many"
    ]

    if any(phrase in lower_question for phrase in natural_medical_phrases):
        return True

    return any(keyword and keyword in lower_question for keyword in scope_keywords)


def generate_fallback_prescription_reply(prescription, question):
    lower_question = question.lower()
    medicine = prescription["medicine_name"]
    dosage = prescription["dosage"]
    instructions = prescription["instructions"]
    consultation_only_message = (
        "I am here for consultation purposes only about this prescription. "
        "Please ask about side effects, precautions, usage, or similar medicines, "
        "and contact your doctor or pharmacist for anything outside that scope."
    )

    if "hello" in lower_question or "hi" in lower_question or "help" in lower_question:
        return (
            f"I am here for consultation purposes only about your prescription for {medicine}. "
            f"You can ask about side effects, precautions, common usage, or similar medicines."
        )

    if not is_prescription_question_in_scope(prescription, question):
        return consultation_only_message

    if "side effect" in lower_question or "side-effect" in lower_question:
        return (
            f"{medicine} can have side effects that differ from person to person. Common issues to watch for can include "
            f"stomach upset, dizziness, sleepiness, allergy symptoms, or anything new after starting the medicine. "
            f"If you notice severe symptoms, contact your doctor or pharmacist promptly. "
            f"This is general information only and not a replacement for medical advice."
        )

    if "similar" in lower_question or "alternative" in lower_question:
        return (
            f"Medicines similar to {medicine} depend on why it was prescribed, your age, other medicines, and your health history. "
            f"For safety, similar or substitute medicines should be confirmed by the prescribing doctor or a pharmacist. "
            f"I can help explain the purpose of this prescription, but changing medicine should always be reviewed by a professional."
        )

    if "precaution" in lower_question or "warning" in lower_question or "avoid" in lower_question:
        return (
            f"A safe starting point is to take {medicine} exactly as prescribed: {dosage}. Follow these instructions: {instructions}. "
            f"Avoid changing the schedule on your own, and check with your doctor or pharmacist before mixing it with other medicines, supplements, or alcohol. "
            f"This is general information only and not a replacement for medical advice."
        )

    return (
        f"{medicine} is listed in your prescription with dosage '{dosage}'. The current instructions say: {instructions}. "
        f"I can help with simple questions about side effects, general usage, precautions, or similar medicines. "
        f"For anything urgent or personal to your condition, please ask your doctor or pharmacist."
    )

LOCAL_PRESCRIPTION_GUIDANCE = {
    "insulin": {
        "aliases": ["insulin"],
        "topics": {
            "food": {
                "summary": "Insulin timing often depends on meals.",
                "advice": "Keep the meal timing exactly as your doctor prescribed. Do not change meal timing or dose timing on your own if the schedule is unclear."
            },
            "missed_dose": {
                "summary": "Missed insulin doses need extra caution.",
                "advice": "Do not double the next dose unless your doctor specifically told you to."
            },
            "side_effects": {
                "summary": "Watch for symptoms that feel unusual after taking it.",
                "advice": "If you feel faint, shaky, confused, or unwell, contact your doctor promptly."
            },
            "interactions": {
                "summary": "Insulin should be reviewed carefully with other medicines.",
                "advice": "Check with your doctor or pharmacist before mixing it with new medicines, supplements, or alcohol."
            }
        }
    }
}

LOCAL_PRESCRIPTION_TOPIC_KEYWORDS = {
    "food": ["food", "meal", "eat", "eating", "breakfast", "lunch", "dinner", "empty stomach", "after food", "before food", "with food"],
    "side_effects": ["side effect", "side effects", "reaction", "rash", "dizzy", "dizziness", "nausea", "vomit", "swelling", "sleepy", "allergy"],
    "missed_dose": ["missed dose", "miss dose", "forgot", "forget", "skip", "late dose", "double dose"],
    "interactions": ["interact", "interaction", "together", "other medicine", "painkiller", "vitamin", "supplement", "alcohol"],
    "precautions": ["precaution", "warning", "avoid", "careful", "safe", "risk", "drive", "pregnant"],
    "usage": ["how do i take", "how to take", "take it", "when do i take", "when to take", "how often", "timing", "dose", "dosage"],
    "storage": ["store", "storage", "fridge", "refrigerator", "room temperature", "keep it"],
    "purpose": ["what is this for", "used for", "why am i taking", "purpose", "what does it do"]
}

LOCAL_PRESCRIPTION_URGENT_PATTERNS = [
    "chest pain",
    "can't breathe",
    "cannot breathe",
    "shortness of breath",
    "severe swelling",
    "fainting",
    "seizure",
    "overdose",
    "passed out",
    "unconscious"
]


def normalize_prescription_text(value):
    return " ".join(str(value or "").strip().lower().split())


def get_local_prescription_guidance(prescription):
    medicine_name = normalize_prescription_text(prescription.get("medicine_name"))
    for guidance in LOCAL_PRESCRIPTION_GUIDANCE.values():
        aliases = [normalize_prescription_text(alias) for alias in guidance.get("aliases", [])]
        if any(alias and alias in medicine_name for alias in aliases):
            return guidance
    return {}


def classify_prescription_question_topic(prescription, question):
    normalized_question = normalize_prescription_text(question)
    if not normalized_question:
        return "general", 0.0

    scores = {topic: 0 for topic in LOCAL_PRESCRIPTION_TOPIC_KEYWORDS}
    for topic, keywords in LOCAL_PRESCRIPTION_TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized_question:
                scores[topic] += 2 if " " in keyword else 1

    medicine_name = normalize_prescription_text(prescription.get("medicine_name"))
    if medicine_name and medicine_name in normalized_question:
        scores["usage"] += 1

    best_topic = max(scores, key=scores.get) if scores else "general"
    best_score = scores.get(best_topic, 0)
    if best_score <= 0:
        return ("general" if is_prescription_question_in_scope(prescription, question) else "out_of_scope"), 0.25

    confidence = min(0.98, 0.4 + (best_score * 0.12))
    return best_topic, confidence


def build_local_follow_up_questions(topic, prescription):
    medicine = prescription.get("medicine_name") or "this medicine"
    follow_ups_by_topic = {
        "food": [
            f"Can I take {medicine} after breakfast, lunch, or dinner?",
            f"Should {medicine} be taken before food, with food, or after food?",
            f"What if I eat late after taking {medicine}?",
            f"Which drinks or meals should I avoid while using {medicine}?",
            f"If the label says '{medicine}', does the meal timing matter every day?",
            "What should I do if I do not feel like eating after taking it?"
        ],
        "side_effects": [
            f"Which side effects from {medicine} are common and which are urgent?",
            f"How long do side effects of {medicine} usually last?",
            f"Should I take {medicine} with food if it upsets my stomach?",
            "What should I do if a side effect starts getting worse?",
            "How do I know if a symptom is a side effect or something more serious?",
            "When should I contact my doctor about a reaction?"
        ],
        "missed_dose": [
            f"What should I do if I miss a dose of {medicine} by a few hours?",
            f"When is it too late to take a missed dose of {medicine}?",
            "What if I accidentally take the missed dose twice?",
            "How can I organize my schedule so I do not miss another dose?",
            "Should I skip the next dose if the missed one was late?",
            "Can I use an alarm or reminder so I take it on time?"
        ],
        "interactions": [
            f"Can {medicine} be taken with my other prescription medicines?",
            f"Does {medicine} interact with vitamins, supplements, or painkillers?",
            f"Should I space {medicine} apart from other medicines?",
            "What symptoms might suggest a bad interaction?",
            "Is it safe with alcohol, coffee, or herbal products?",
            "Should I check with the pharmacist before combining it with anything new?"
        ],
        "precautions": [
            f"Who needs to be extra careful when taking {medicine}?",
            f"Can I drive or work safely after taking {medicine}?",
            f"What warning signs mean I should contact a doctor while using {medicine}?",
            "Is there anything I should avoid because of my health conditions?",
            "Should I be careful if I am pregnant, breastfeeding, or have another illness?",
            "Are there activities I should avoid right after taking it?"
        ],
        "usage": [
            f"What is the exact best time to take {medicine} each day?",
            f"Can I change when I take {medicine} if I feel better?",
            f"Should I keep taking {medicine} even if my symptoms improve?",
            f"How strictly should I follow the instructions for {medicine}?",
            "If I am confused about the label, which instruction matters most?",
            "Does it matter if I take it at the same time every day?"
        ],
        "storage": [
            f"Should {medicine} be kept in a cool, dry place or in the fridge?",
            "What if the medicine was left out of storage for too long?",
            "Can I keep it in a bathroom cabinet or inside a car?",
            "How do I know if the medicine is no longer safe to use?",
            "Should it stay in the original package after opening?",
            "What should I do if the storage instructions are unclear?"
        ],
        "purpose": [
            f"What is {medicine} usually used for in simple terms?",
            f"How long does {medicine} usually take to start working?",
            f"What should I expect during the first few days of using {medicine}?",
            f"What should I avoid while using {medicine}?",
            "Why would my doctor choose this medicine instead of another one?",
            "What symptom should improve first if it is working?"
        ],
        "general": [
            "What side effects should I watch for first?",
            "Can I take this with food or on an empty stomach?",
            "What if I miss a dose?",
            "Can this interact with other medicines?",
            "What should I avoid while taking it?",
            "When should I contact my doctor?"
        ]
    }
    return follow_ups_by_topic.get(topic, follow_ups_by_topic["general"])


def build_local_prescription_answer_card(topic, prescription, question, guidance, dosage, instructions):
    medicine = prescription.get("medicine_name") or "this medicine"
    doctor_name = prescription.get("doctor_name") or "your doctor"
    guidance_summary = guidance.get("topics", {}).get(topic, {}).get("summary", "")
    guidance_advice = guidance.get("topics", {}).get(topic, {}).get("advice", "")

    topic_cards = {
        "food": {
            "title": f"Meal timing for {medicine}",
            "short_answer": f"Follow the meal timing in your prescription for {medicine} and do not change it on your own.",
            "why_it_matters": guidance_summary or f"The timing of {medicine} can matter around meals, especially if your prescription says: {instructions}.",
            "watch_for": guidance_advice or "If the timing is unclear or you feel unwell after taking it, do not guess. Ask your doctor or pharmacist.",
            "ask_doctor": f"Confirm the exact timing if you miss meals, eat late, or were not told whether {medicine} should be taken before, with, or after food."
        },
        "side_effects": {
            "title": f"Side effects for {medicine}",
            "short_answer": f"Watch for any new or unexpected symptoms after starting {medicine}.",
            "why_it_matters": guidance_summary or f"Your prescription still matters here: {dosage}. Some effects can be mild, but some need medical advice.",
            "watch_for": guidance_advice or "If symptoms are severe, worsening, or different from what you expected, contact your doctor or pharmacist promptly.",
            "ask_doctor": f"Ask your doctor if a symptom feels strong, unusual, or keeps coming back while you are using {medicine}."
        },
        "missed_dose": {
            "title": f"Missed dose guidance for {medicine}",
            "short_answer": f"Do not double the next dose of {medicine} unless your doctor told you to.",
            "why_it_matters": guidance_summary or f"Your prescription says: {dosage}. The safest next step depends on how late the dose was missed.",
            "watch_for": guidance_advice or "If you often miss doses, use a reminder or pill organizer and ask your pharmacist what to do for late doses.",
            "ask_doctor": f"Check with your doctor if you are unsure how late is too late for {medicine}, especially if you missed more than one dose."
        },
        "interactions": {
            "title": f"Interactions with {medicine}",
            "short_answer": f"Do not mix {medicine} with other medicines, vitamins, or alcohol without checking first.",
            "why_it_matters": guidance_summary or f"The combination can change how {medicine} works, especially when your prescription instructions are: {instructions}.",
            "watch_for": guidance_advice or "If you start anything new and notice unexpected symptoms, stop guessing and ask your doctor or pharmacist.",
            "ask_doctor": f"Confirm safety before adding painkillers, supplements, or new prescriptions alongside {medicine}."
        },
        "precautions": {
            "title": f"Precautions for {medicine}",
            "short_answer": f"Take {medicine} exactly as prescribed and avoid changing the dose or timing on your own.",
            "why_it_matters": guidance_summary or f"Precautions matter more if you take other medicines or have other health conditions.",
            "watch_for": guidance_advice or "Be extra careful if you are pregnant, breastfeeding, driving, or managing another illness.",
            "ask_doctor": f"Ask before using {medicine} if you are unsure about your health condition, daily routine, or other medications."
        },
        "usage": {
            "title": f"How to take {medicine}",
            "short_answer": f"Follow the written prescription for {medicine}: {instructions}.",
            "why_it_matters": guidance_summary or f"Using {medicine} at the right time and in the right amount keeps treatment consistent.",
            "watch_for": guidance_advice or "If the timing or number of doses is unclear, confirm it before changing anything.",
            "ask_doctor": f"Ask your doctor if you want to change when you take {medicine} or if the label seems confusing."
        },
        "storage": {
            "title": f"Storage for {medicine}",
            "short_answer": f"Keep {medicine} stored exactly as your doctor or pharmacist advised.",
            "why_it_matters": guidance_summary or "The wrong storage conditions can reduce safety or effectiveness.",
            "watch_for": guidance_advice or "If it was left out of the fridge, in a hot room, or in a wet area, confirm with a pharmacist before using it.",
            "ask_doctor": f"Ask if you are unsure whether {medicine} should stay in a cool, dry place or be refrigerated."
        },
        "purpose": {
            "title": f"Why {medicine} was prescribed",
            "short_answer": f"{medicine} is being used as part of your treatment plan, but the exact reason should be confirmed with {doctor_name}.",
            "why_it_matters": guidance_summary or f"This question is best answered by the doctor who prescribed {medicine}.",
            "watch_for": guidance_advice or "Use the medicine only as directed and do not change it based on general advice alone.",
            "ask_doctor": f"Ask {doctor_name} for the exact goal of the medicine and how you should know it is working."
        },
        "general": {
            "title": f"Guidance for {medicine}",
            "short_answer": f"I can help with simple prescription questions about {medicine}.",
            "why_it_matters": f"Your prescription shows: {dosage}. The written instructions are: {instructions}.",
            "watch_for": "If anything about the medicine feels unclear, do not change it on your own.",
            "ask_doctor": f"Ask your doctor or pharmacist if you want confirmation on timing, dose, food, or safety."
        }
    }

    card = topic_cards.get(topic, topic_cards["general"])
    return {
        "title": card["title"],
        "short_answer": card["short_answer"],
        "why_it_matters": card["why_it_matters"],
        "watch_for": card["watch_for"],
        "ask_doctor": card["ask_doctor"],
        "prescription_note": f"Prescription note: {instructions}",
        "footer_note": f"General information only. For exact personal advice about {medicine}, confirm with {doctor_name}.",
        "topic_tag": topic.replace("_", " ").title()
    }


def build_local_prescription_ai_reply(prescription, question, chat_history):
    del chat_history

    medicine = prescription.get("medicine_name") or "this medicine"
    dosage = prescription.get("dosage") or "the prescribed dosage"
    instructions = prescription.get("instructions") or "follow the prescription instructions"
    normalized_question = normalize_prescription_text(question)
    guidance = get_local_prescription_guidance(prescription)

    if any(pattern in normalized_question for pattern in LOCAL_PRESCRIPTION_URGENT_PATTERNS):
        urgent_card = {
            "title": f"Urgent guidance for {medicine}",
            "short_answer": "This sounds urgent. Seek emergency care right away if symptoms are severe.",
            "why_it_matters": "Severe breathing trouble, fainting, seizure, chest pain, or a severe allergic reaction should not wait.",
            "watch_for": "Do not rely on this helper for urgent symptoms. Contact emergency care or your doctor immediately.",
            "ask_doctor": "Ask your doctor after you are safe if you still need prescription guidance.",
            "prescription_note": f"Prescription note: {instructions}",
            "footer_note": "General information only. This does not replace emergency care.",
            "topic_tag": "Urgent"
        }
        return {
            "topic": "urgent",
            "confidence": 0.99,
            "warning_level": "urgent",
            "reply": (
                f"This sounds urgent. I can only give general prescription guidance about {medicine}. "
                "If you have severe symptoms like chest pain, breathing trouble, fainting, seizure, or a severe allergic reaction, seek emergency care right away."
            ),
            "card": urgent_card,
            "follow_ups": [
                "What side effects should I watch for?",
                "Can this interact with other medicines?",
                "What should I avoid while taking it?"
            ]
        }

    topic, confidence = classify_prescription_question_topic(prescription, question)
    topic_guidance = guidance.get("topics", {}).get(topic, {})
    topic_summary = topic_guidance.get("summary", "")
    doctor_name = prescription.get("doctor_name") or "your doctor"

    reply_templates = {
        "food": f"Yes. {topic_summary or 'If the timing is unclear, ask your doctor or pharmacist before changing it.'}",
        "side_effects": f"Yes. {topic_summary or 'If it feels severe or unusual, contact your doctor promptly.'}",
        "missed_dose": f"No. {topic_summary or 'If you are unsure what to do, ask before taking another dose.'}",
        "interactions": f"Maybe. {topic_summary or 'Check before mixing it with anything new.'}",
        "precautions": f"Yes. {topic_summary or 'Follow the prescription closely and check first if needed.'}",
        "usage": f"Yes. {topic_summary or f'Follow the written instructions: {instructions}.'}",
        "storage": f"Yes. {topic_summary or 'If it was kept in the wrong place, ask before using it.'}",
        "purpose": f"Yes. {topic_summary or f'For the exact reason it was prescribed, check with {doctor_name}.'}",
        "general": f"Yes. {topic_summary or 'Ask me about food timing, side effects, missed doses, interactions, storage, or precautions.'}"
    }

    reply = reply_templates.get(topic, reply_templates["general"])
    reply = " ".join(reply.split())

    if not is_prescription_question_in_scope(prescription, question):
        reply = (
            f"I can help with {medicine} questions. "
            f"Ask me about food timing, side effects, missed doses, interactions, storage, or precautions."
        )

    return {
        "topic": topic,
        "confidence": confidence,
        "warning_level": "normal",
        "reply": reply,
        "card": build_local_prescription_answer_card(topic, prescription, question, guidance, dosage, instructions),
        "follow_ups": build_local_follow_up_questions(topic, prescription)
    }




# =========================
# OTP FUNCTIONS
# =========================
def generate_numeric_otp(length=6):
    return ''.join(secrets.choice(string.digits) for _ in range(length))




def save_otp_to_db(user_id, otp_code, purpose="login", minutes_valid=5):
    expires_at = datetime.now() + timedelta(minutes=minutes_valid)


    db = get_db()
    cur = db.cursor()


    cur.execute("""
        UPDATE otp_codes
        SET is_used = 1
        WHERE user_id = %s AND purpose = %s AND is_used = 0
    """, (user_id, purpose))


    cur.execute("""
        INSERT INTO otp_codes (user_id, otp_code, purpose, expires_at, is_used)
        VALUES (%s, %s, %s, %s, 0)
    """, (user_id, otp_code, purpose, expires_at))


    db.commit()
    cur.close()
    db.close()




def send_otp_email(recipient_email, otp_code):
    msg = Message(
        subject="Your E-Health OTP Verification Code",
        recipients=[recipient_email]
    )
    msg.body = f"""
Your E-Health verification code is: {otp_code}


This code will expire in 5 minutes.
If you did not attempt to log in, please ignore this email.
"""
    mail.send(msg)




def verify_otp_in_db(user_id, otp_input, purpose="login"):
    db = get_db()
    cur = db.cursor(dictionary=True)


    cur.execute("""
        SELECT id, otp_code, expires_at, is_used
        FROM otp_codes
        WHERE user_id = %s AND purpose = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id, purpose))


    row = cur.fetchone()


    if not row:
        cur.close()
        db.close()
        return False, "No OTP found"


    if row["is_used"]:
        cur.close()
        db.close()
        return False, "OTP already used"


    if datetime.now() > row["expires_at"]:
        cur.close()
        db.close()
        return False, "OTP expired"


    if row["otp_code"] != otp_input:
        cur.close()
        db.close()
        return False, "Invalid OTP"


    cur2 = db.cursor()
    cur2.execute("UPDATE otp_codes SET is_used = 1 WHERE id = %s", (row["id"],))
    db.commit()
    cur2.close()


    cur.close()
    db.close()


    return True, "OTP verified"




# =========================
# CAPTCHA FUNCTIONS
# =========================
def generate_captcha(length=5):
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))




def generate_captcha_image(captcha_text):
    width, height = 180, 60
    image = Image.new("RGB", (width, height), (245, 250, 250))
    draw = ImageDraw.Draw(image)


    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()


    for _ in range(8):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(180, 200, 200), width=1)


    for _ in range(120):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        draw.point(
            (x, y),
            fill=(
                random.randint(120, 220),
                random.randint(120, 220),
                random.randint(120, 220)
            )
        )


    x_offset = 18
    for ch in captcha_text:
        y_offset = random.randint(8, 18)
        draw.text((x_offset, y_offset), ch, font=font, fill=(0, 77, 77))
        x_offset += 28


    image = image.filter(ImageFilter.SMOOTH)


    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer




@app.route("/captcha-image")
def captcha_image():
    code = session.get("captcha_code", "ERROR")
    image_buffer = generate_captcha_image(code)
    return send_file(image_buffer, mimetype="image/png")




@app.route("/refresh-captcha", methods=["GET"])
def refresh_captcha():
    session["captcha_code"] = generate_captcha()
    return jsonify({
        "ok": True,
        "captcha_url": url_for("captcha_image") + f"?t={secrets.token_hex(4)}"
    })




# =========================
# BASIC ROUTES
# =========================
@app.route("/")
def home():
    return render_template("index.html")


def build_email_suggestions(email, limit=3):
    email = (email or "").strip().lower()
    local_part, separator, domain = email.partition("@")
    if not separator or not local_part or not domain:
        return []

    candidates = [f"{local_part}{index}@{domain}" for index in range(1, 12)]
    db = get_db()
    cur = db.cursor()
    placeholders = ",".join(["%s"] * len(candidates))
    cur.execute(f"SELECT email FROM users WHERE email IN ({placeholders})", tuple(candidates))
    taken = {row[0].lower() for row in cur.fetchall() if row and row[0]}
    cur.close()
    db.close()

    suggestions = []
    for candidate in candidates:
        if candidate.lower() not in taken:
            suggestions.append(candidate)
        if len(suggestions) >= limit:
            break
    return suggestions


def get_doctor_avatar_pool(gender):
    normalized_gender = (gender or "").strip().lower()
    if normalized_gender in DOCTOR_AVATAR_POOLS:
        return DOCTOR_AVATAR_POOLS[normalized_gender]

    avatar_pool = []
    for paths in DOCTOR_AVATAR_POOLS.values():
        avatar_pool.extend(paths)
    return avatar_pool


def choose_random_doctor_avatar(gender):
    avatar_pool = get_doctor_avatar_pool(gender)
    if not avatar_pool:
        return None
    return random.choice(avatar_pool)


def resolve_doctor_avatar_path(doctor):
    if not doctor:
        return None

    stored_path = (doctor.get("doctor_avatar_path") or "").strip()
    if stored_path:
        return stored_path

    avatar_pool = get_doctor_avatar_pool(doctor.get("gender"))
    if not avatar_pool:
        return None

    doctor_id = int(doctor.get("id") or 0)
    return avatar_pool[doctor_id % len(avatar_pool)]


def get_pending_doctor_accounts():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, name, email, age, gender, specialty, phone, bio,
               hashed_id, wallet_address, doctor_medical_id,
               doctor_id_card_path, doctor_medical_id_photo_path, doctor_avatar_path
        FROM users
        WHERE role='doctor' AND approval_status='pending'
        ORDER BY id DESC
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    for row in rows:
        row["avatar_path"] = resolve_doctor_avatar_path(row)
    return rows




@app.route("/signup", methods=["GET", "POST"])
def signup():
    field_errors = {}
    field_suggestions = {}
    form_data = {
        "first_name": "",
        "last_name": "",
        "email": "",
        "age": "",
        "gender": "",
        "wallet_address": "",
        "role": "",
        "specialty": "",
        "phone": "",
        "bio": ""
    }
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        age = request.form.get("age", "").strip()
        gender = request.form.get("gender", "").strip()
        wallet_address = request.form.get("wallet_address", "").strip()
        role = request.form.get("role", "").strip()
        specialty = request.form.get("specialty", "").strip()
        phone = request.form.get("phone", "").strip()
        bio = request.form.get("bio", "").strip()

        form_data.update({
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "age": age,
            "gender": gender,
            "wallet_address": wallet_address,
            "role": role,
            "specialty": specialty,
            "phone": phone,
            "bio": bio
        })


        if not all([first_name, last_name, email, password, age, gender, wallet_address, role]):
            return render_template("signup.html", error="Please fill in all fields.", form_data=form_data, field_errors=field_errors, field_suggestions=field_suggestions)


        if not Web3.is_address(wallet_address):
            form_data["wallet_address"] = ""
            field_errors["wallet_address"] = "Enter a valid blockchain wallet address."
            return render_template("signup.html", error="Please review the highlighted field and try again.", form_data=form_data, field_errors=field_errors, field_suggestions=field_suggestions)


        wallet_address = Web3.to_checksum_address(wallet_address)


        full_name = f"{first_name} {last_name}"
        hashed_id = Web3.keccak(text=f"{email}-{wallet_address}-{secrets.token_hex(8)}").hex()


        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("""
            SELECT email, wallet_address
            FROM users
            WHERE email=%s OR wallet_address=%s
            LIMIT 1
        """, (email, wallet_address))
        existing_user = cur.fetchone()
        cur.close()
        db.close()


        if existing_user:
            existing_email = (existing_user.get("email") or "").strip().lower()
            existing_wallet = (existing_user.get("wallet_address") or "").strip().lower()
            submitted_email = email.strip().lower()
            submitted_wallet = wallet_address.strip().lower()

            if existing_email == submitted_email:
                form_data["email"] = ""
                field_errors["email"] = "Please try a different email address."
                field_suggestions["email"] = build_email_suggestions(email)
            if existing_wallet == submitted_wallet:
                form_data["wallet_address"] = ""
                field_errors["wallet_address"] = "This wallet address cannot be used. Please choose another one."
            return render_template("signup.html", error="We could not complete registration with the provided account details. Please review the highlighted field and try again.", form_data=form_data, field_errors=field_errors, field_suggestions=field_suggestions)


        if role not in ("patient", "doctor", "storage"):
            field_errors["role"] = "Please choose a valid role."
            return render_template("signup.html", error="Please review the highlighted field and try again.", form_data=form_data, field_errors=field_errors, field_suggestions=field_suggestions)


        if role == "doctor":
            if not specialty or not phone or not bio:
                if not specialty:
                    field_errors["specialty"] = "Specialty is required for doctor accounts."
                if not phone:
                    field_errors["phone"] = "Phone is required for doctor accounts."
                if not bio:
                    field_errors["bio"] = "Doctor bio is required."
                return render_template("signup.html", error="Please complete the required doctor fields.", form_data=form_data, field_errors=field_errors, field_suggestions=field_suggestions)
            session["doctor_signup_data"] = {
                "first_name": first_name,
                "last_name": last_name,
                "name": full_name,
                "email": email,
                "password": password,
                "age": age,
                "gender": gender,
                "wallet_address": wallet_address,
                "role": role,
                "hashed_id": hashed_id,
                "specialty": specialty,
                "phone": phone,
                "bio": bio
            }
            return redirect(url_for("doctor_verification"))


        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO users (
                role, first_name, last_name, name, email, password, age, gender,
                hashed_id, wallet_address, approval_status, phone
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'approved', %s)
        """, (
            role, first_name, last_name, full_name, email, password, age, gender,
            hashed_id, wallet_address, phone or None
        ))
        db.commit()
        cur.close()
        db.close()


        return redirect(url_for(
            "login",
            signup_notice="1",
            signup_notice_title="Account Created",
            signup_notice_message="Your account has been created successfully. You can sign in now."
        ))


    return render_template("signup.html", form_data=form_data, field_errors=field_errors, field_suggestions=field_suggestions)




@app.route("/doctor-verification", methods=["GET", "POST"])
def doctor_verification():
    if "doctor_signup_data" not in session:
        return redirect(url_for("signup"))


    if request.method == "POST":
        medical_id_number = request.form.get("medical_id_number", "").strip()
        id_card_photo = request.files.get("id_card_photo")
        medical_id_photo = request.files.get("medical_id_photo")


        if not medical_id_number or not id_card_photo or not medical_id_photo:
            return render_template("doctor_verification.html", error="Please complete all doctor verification fields.")


        id_card_path = save_uploaded_file(id_card_photo, "doctor_id_card")
        medical_id_photo_path = save_uploaded_file(medical_id_photo, "doctor_medical_id")


        if not id_card_path or not medical_id_photo_path:
            return render_template("doctor_verification.html", error="Only image files are allowed (png, jpg, jpeg, webp).")


        data = session["doctor_signup_data"]
        doctor_avatar_path = choose_random_doctor_avatar(data.get("gender"))


        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO users (
                role, first_name, last_name, name, email, password, age, gender,
                doctor_avatar_path, hashed_id, wallet_address, approval_status,
                doctor_medical_id, doctor_id_card_path, doctor_medical_id_photo_path,
                specialty, phone, bio
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s)
        """, (
            data["role"], data["first_name"], data["last_name"], data["name"], data["email"],
            data["password"], data["age"], data["gender"], doctor_avatar_path, data["hashed_id"],
            data["wallet_address"], medical_id_number, id_card_path, medical_id_photo_path,
            data["specialty"], data["phone"], data["bio"]
        ))
        db.commit()
        cur.close()
        db.close()


        session.pop("doctor_signup_data", None)
        return redirect(url_for(
            "login",
            signup_notice="1",
            signup_notice_title="Doctor Account Submitted",
            signup_notice_message="Your doctor account was created and your verification was submitted for admin review."
        ))


    return render_template("doctor_verification.html")




@app.route("/login", methods=["GET", "POST"])
def login():
    if load_authenticated_session():
        return redirect(post_login_redirect())

    signup_notice = request.args.get("signup_notice") == "1"
    signup_notice_title = request.args.get("signup_notice_title", "").strip()
    signup_notice_message = request.args.get("signup_notice_message", "").strip()

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        captcha_input = request.form.get("captcha_input", "").strip().upper()
        captcha_expected = session.get("captcha_code", "")


        if not captcha_expected or captcha_input != captcha_expected:
            session["captcha_code"] = generate_captcha()
            return render_template(
                "login.html",
                error="Invalid CAPTCHA code",
                signup_notice=signup_notice,
                signup_notice_title=signup_notice_title,
                signup_notice_message=signup_notice_message
            )


        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("""
            SELECT id, role, name, email, hashed_id, approval_status
            FROM users
            WHERE email=%s AND password=%s
        """, (email, password))
        user = cur.fetchone()
        cur.close()
        db.close()


        if not user:
            session["captcha_code"] = generate_captcha()
            return render_template(
                "login.html",
                error="Invalid email or password",
                signup_notice=signup_notice,
                signup_notice_title=signup_notice_title,
                signup_notice_message=signup_notice_message
            )


        if user["role"] == "doctor" and user.get("approval_status") == "pending":
            session["captcha_code"] = generate_captcha()
            return render_template(
                "login.html",
                error="Doctor account is pending admin approval.",
                signup_notice=signup_notice,
                signup_notice_title=signup_notice_title,
                signup_notice_message=signup_notice_message
            )


        otp_code = generate_numeric_otp()
        save_otp_to_db(user["id"], otp_code, purpose="login", minutes_valid=5)


        try:
            send_otp_email(user["email"], otp_code)
        except Exception as e:
            session["captcha_code"] = generate_captcha()
            return render_template("login.html", error=f"Failed to send OTP email: {e}")


        session["pending_user_id"] = user["id"]
        session["pending_role"] = user["role"]
        session["pending_name"] = user["name"]
        session["pending_hashed_id"] = user["hashed_id"]
        session["pending_email"] = user["email"]


        return redirect(url_for("verify_otp"))


    session["captcha_code"] = generate_captcha()
    return render_template(
        "login.html",
        signup_notice=signup_notice,
        signup_notice_title=signup_notice_title,
        signup_notice_message=signup_notice_message
    )




@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if "pending_user_id" not in session:
        return redirect(url_for("login"))


    if request.method == "POST":
        otp_input = request.form.get("otp", "").strip()


        if not otp_input:
            return render_template("verify_otp.html", error="Please enter the OTP code")


        ok, message = verify_otp_in_db(
            session["pending_user_id"],
            otp_input,
            purpose="login"
        )


        if not ok:
            return render_template("verify_otp.html", error=message)


        authenticated_user = {
            "id": session["pending_user_id"],
            "role": session["pending_role"],
            "name": session["pending_name"],
            "hashed_id": session["pending_hashed_id"]
        }

        create_authenticated_session(authenticated_user, "otp")


        session.pop("pending_user_id", None)
        session.pop("pending_role", None)
        session.pop("pending_name", None)
        session.pop("pending_hashed_id", None)
        session.pop("pending_email", None)


        log_action(session["user_id"], "LOGIN_OTP_SUCCESS", get_client_ip())


        return redirect(post_login_redirect())


    return render_template("verify_otp.html")




@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    if "pending_user_id" not in session or "pending_email" not in session:
        return redirect(url_for("login"))


    otp_code = generate_numeric_otp()
    save_otp_to_db(session["pending_user_id"], otp_code, purpose="login", minutes_valid=5)


    try:
        send_otp_email(session["pending_email"], otp_code)
    except Exception as e:
        return render_template("verify_otp.html", error=f"Failed to resend OTP: {e}")


    return render_template("verify_otp.html", success="A new OTP has been sent to your email")




@app.route("/patient-home")
def patient_home():
    if "user_id" not in session:
        return redirect(url_for("login"))


    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT wallet_address, approval_status, role, name, hashed_id
        FROM users
        WHERE id=%s
        LIMIT 1
    """, (session["user_id"],))
    user = cur.fetchone()


    if not user:
        cur.close()
        db.close()
        return redirect(url_for("logout"))

    cur.execute("""
        SELECT id, name, email, specialty, phone, bio, approval_status, gender, doctor_avatar_path
        FROM users
        WHERE role='doctor'
        ORDER BY
            CASE WHEN approval_status='approved' THEN 0 ELSE 1 END,
            name ASC
    """)
    doctors = cur.fetchall()

    cur.execute("""
        SELECT a.id, a.doctor_id, a.status, a.appointment_date, a.notes, a.created_at,
               u.name AS doctor_name, u.specialty
        FROM appointments a
        JOIN users u ON u.id = a.doctor_id
        WHERE a.patient_id=%s
        ORDER BY
            CASE
                WHEN a.appointment_date IS NULL THEN 1
                ELSE 0
            END,
            a.appointment_date ASC,
            a.created_at DESC
    """, (session["user_id"],))
    appointments = cur.fetchall()

    cur.execute("""
        SELECT ar.id, u.name AS doctor_name, u.email AS doctor_email,
               ar.status, ar.blockchain_tx_hash, ar.requested_at,
               ar.prescription_written_at, ar.appointment_id,
               a.appointment_date, a.status AS appointment_status,
               p.id AS prescription_id, p.medicine_name, p.dosage,
               p.instructions, p.created_at AS prescription_created_at
        FROM access_requests ar
        JOIN users u ON u.id = ar.doctor_id
        LEFT JOIN appointments a ON a.id = ar.appointment_id
        LEFT JOIN prescriptions p ON p.access_request_id = ar.id
        WHERE ar.patient_id=%s
        ORDER BY
            COALESCE(a.appointment_date, ar.requested_at) DESC,
            ar.requested_at DESC
    """, (session["user_id"],))
    requests_list = cur.fetchall()

    cur.close()
    db.close()

    upcoming_appointments = [appt for appt in appointments if appt["status"] == "approved" and appt["appointment_date"]]
    pending_appointments = [appt for appt in appointments if appt["status"] == "pending"]
    pending_access_requests = [req for req in requests_list if req["status"] == "pending"]
    access_history = [req for req in requests_list if req["status"] != "pending" or req.get("prescription_id")]

    doctor_booking_states = {}
    def appointment_sort_key(appointment):
        created_at = appointment.get("created_at")
        if hasattr(created_at, "timestamp"):
            created_ts = created_at.timestamp()
        elif isinstance(created_at, str) and created_at:
            try:
                created_ts = datetime.fromisoformat(created_at).timestamp()
            except ValueError:
                created_ts = 0.0
        else:
            created_ts = 0.0
        return (created_ts, appointment.get("id") or 0)

    latest_appointments_by_doctor = {}
    for appointment in appointments:
        doctor_id = appointment.get("doctor_id")
        if not doctor_id:
            continue

        current_latest = latest_appointments_by_doctor.get(doctor_id)
        current_key = appointment_sort_key(current_latest) if current_latest else (-1.0, 0)
        candidate_key = appointment_sort_key(appointment)

        if current_latest is None or candidate_key > current_key:
            latest_appointments_by_doctor[doctor_id] = appointment

    for doctor in doctors:
        latest_appointment = latest_appointments_by_doctor.get(doctor["id"])
        if not latest_appointment:
            doctor_booking_states[doctor["id"]] = "none"
            continue

        appointment_status = (latest_appointment.get("status") or "").lower()
        if appointment_status == "pending":
            doctor_booking_states[doctor["id"]] = "pending"
        elif appointment_status == "approved":
            doctor_booking_states[doctor["id"]] = "approved"
        else:
            doctor_booking_states[doctor["id"]] = "none"

    for doctor in doctors:
        doctor["booking_state"] = doctor_booking_states.get(doctor["id"], "none")
        doctor["avatar_path"] = resolve_doctor_avatar_path(doctor)

    return render_template(
        "patient_home.html",
        name=user["name"],
        role=user["role"],
        hashed_id=user["hashed_id"],
        wallet_address=user["wallet_address"],
        approval_status=user["approval_status"],
        doctors=doctors,
        appointments=appointments,
        upcoming_appointments=upcoming_appointments,
        pending_appointments=pending_appointments,
        requests_list=requests_list,
        pending_access_requests=pending_access_requests,
        access_history=access_history,
        appointment_feedback=request.args.get("appointment_feedback", ""),
        appointment_feedback_type=request.args.get("appointment_feedback_type", "success"),
        appointment_feedback_title=request.args.get("appointment_feedback_title", ""),
        appointment_feedback_badge=request.args.get("appointment_feedback_badge", ""),
        appointment_feedback_seconds=request.args.get("appointment_feedback_seconds", type=int) or 10
    )


@app.route("/patient-home/reveal-sensitive", methods=["POST"])
def patient_home_reveal_sensitive():
    if "user_id" not in session:
        return jsonify({"ok": False, "error": "Please sign in again."}), 401
    if session.get("role") != "patient":
        return jsonify({"ok": False, "error": "Only patients can access this action."}), 403

    data = request.get_json(silent=True) or {}
    field = (data.get("field") or "").strip()
    password = data.get("password") or ""

    allowed_fields = {
        "hashed_id": "hashed_id",
        "wallet_address": "wallet_address"
    }

    if field not in allowed_fields:
        return jsonify({"ok": False, "error": "Unsupported sensitive field."}), 400

    if not password:
        return jsonify({"ok": False, "error": "Password is required."}), 400

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT password, hashed_id, wallet_address
        FROM users
        WHERE id=%s
        LIMIT 1
    """, (session["user_id"],))
    user = cur.fetchone()
    cur.close()
    db.close()

    if not user:
        return jsonify({"ok": False, "error": "Account not found."}), 404

    stored_password = user.get("password") or ""
    password_is_valid = False

    if stored_password.startswith(("pbkdf2:", "scrypt:")):
        password_is_valid = check_password_hash(stored_password, password)
    else:
        password_is_valid = hmac.compare_digest(stored_password, password)

    if not password_is_valid:
        return jsonify({"ok": False, "error": "Incorrect password."}), 403

    log_action(session["user_id"], f"PATIENT_REVEALED_{field.upper()}", get_client_ip())
    return jsonify({
        "ok": True,
        "field": field,
        "value": user.get(allowed_fields[field]) or ""
    })


@app.route("/patient-profile", methods=["GET", "POST"])
def patient_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "patient":
        return redirect(url_for("dashboard"))

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, name, email, age, gender, phone, hashed_id, wallet_address, approval_status, password
        FROM users
        WHERE id=%s AND role='patient'
        LIMIT 1
    """, (session["user_id"],))
    user = cur.fetchone()
    cur.close()
    db.close()

    if not user:
        return redirect(url_for("logout"))

    if request.method == "GET":
        return render_template("patient_profile_auth.html")

    password = (request.form.get("password") or "").strip()
    if not password:
        return render_template("patient_profile_auth.html", error="Please enter your password.")

    stored_password = user.get("password") or ""
    password_is_valid = False

    if stored_password.startswith(("pbkdf2:", "scrypt:")):
        password_is_valid = check_password_hash(stored_password, password)
    else:
        password_is_valid = hmac.compare_digest(stored_password, password)

    if not password_is_valid:
        return render_template("patient_profile_auth.html", error="Incorrect password.")

    return render_template("patient_profile.html", user=user)


@app.route("/storage-dashboard")
def storage_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "storage":
        return redirect(post_login_redirect())

    inventory_items = get_pharmacy_inventory_items()
    inventory_summary = get_pharmacy_inventory_summary(inventory_items)
    recent_movements = get_recent_stock_movements()
    pending_prescriptions = get_pending_prescriptions_for_storage()
    return render_template(
        "storage_dashboard.html",
        name=session["name"],
        hashed_id=session["hashed_id"],
        inventory_items=inventory_items,
        inventory_summary=inventory_summary,
        low_stock_items=inventory_summary["alert_items"],
        recent_movements=recent_movements,
        pending_prescriptions=pending_prescriptions,
        inventory_error=request.args.get("error", ""),
        inventory_success=request.args.get("success", "")
    )


@app.route("/storage/inventory/add", methods=["POST"])
def storage_add_inventory():
    if session.get("role") != "storage":
        return redirect(post_login_redirect())

    ok, message = create_inventory_medicine(request.form, session["user_id"])
    if ok:
        log_action(session["user_id"], "STORAGE_ADDED_MEDICINE", get_client_ip())
        return redirect(url_for("storage_dashboard", success=message))
    return redirect(url_for("storage_dashboard", error=message))


@app.route("/storage/inventory/update", methods=["POST"])
def storage_update_inventory():
    if session.get("role") != "storage":
        return redirect(post_login_redirect())

    ok, message = apply_stock_movement(request.form, session["user_id"])
    if ok:
        log_action(session["user_id"], "STORAGE_UPDATED_MEDICINE_STOCK", get_client_ip())
        return redirect(url_for("storage_dashboard", success=message))
    return redirect(url_for("storage_dashboard", error=message))


@app.route("/storage/prescriptions/dispense/<int:prescription_id>", methods=["POST"])
def storage_dispense_prescription(prescription_id):
    if session.get("role") != "storage":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Please sign in again."}), 401
        return redirect(post_login_redirect())

    ok, message = dispense_prescription_stock(prescription_id, session["user_id"])
    if ok:
        log_action(session["user_id"], "STORAGE_DISPENSED_PRESCRIPTION", get_client_ip())
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": True, "message": message})
        return redirect(url_for("storage_dashboard", success=message))
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": False, "message": message}), 400
    return redirect(url_for("storage_dashboard", error=message))




# =========================
# WALLET LOGIN
# =========================
@app.route("/wallet-login", methods=["GET"])
def wallet_login_page():
    return render_template("wallet_login.html")


@app.route("/patient/prescription-ai", methods=["POST"])
def patient_prescription_ai():
    if session.get("role") != "patient" or "user_id" not in session:
        return jsonify({"ok": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    prescription_id = data.get("prescription_id")
    question = (data.get("message") or "").strip()
    chat_history = sanitize_chat_history(data.get("history"))

    try:
        prescription_id = int(prescription_id)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid prescription selection"}), 400

    if not question:
        return jsonify({"ok": False, "error": "Please enter a question"}), 400

    prescription = get_prescription_for_patient(prescription_id, session["user_id"])
    if not prescription:
        return jsonify({"ok": False, "error": "Prescription not found"}), 404

    try:
        reply_text = call_ollama_prescription_reply(prescription, question, chat_history)
    except Exception as exc:
        app.logger.warning("Ollama prescription chat failed: %s", exc)
        return jsonify({"ok": False, "error": "The prescription chat could not answer right now."}), 502

    log_action(session["user_id"], "ASK_PRESCRIPTION_AI", get_client_ip())

    return jsonify({
        "ok": True,
        "reply": reply_text,
        "topic": "openai",
        "confidence": 1,
        "warning_level": "normal",
        "follow_ups": [],
        "disclaimer": "General information only. This does not replace your doctor or pharmacist.",
        "source": "ollama"
    })


def require_integrity_access(record_id):
    if "user_id" not in session:
        return None
    if session.get("role") == "admin":
        return get_accessible_record_for_user(record_id, session["user_id"], "admin")
    return get_accessible_record_for_user(record_id, session["user_id"], session.get("role"))


def make_no_cache_response(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/integrity-dashboard")
def integrity_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") not in ("admin", "doctor", "patient"):
        return redirect(post_login_redirect())

    accessible_records = get_user_accessible_records(session["user_id"], session.get("role"))
    selected_record_id = request.args.get("record_id", type=int)
    selected_record = None
    snapshot = None

    if accessible_records:
        if selected_record_id:
            selected_record = next((record for record in accessible_records if record["id"] == selected_record_id), None)
        if not selected_record:
            selected_record = accessible_records[0]
        snapshot = build_integrity_snapshot(selected_record, session["user_id"])

    response = make_response(render_template(
        "integrity_dashboard.html",
        accessible_records=accessible_records,
        selected_record=selected_record,
        snapshot=snapshot,
        node_names=INTEGRITY_NODE_NAMES,
        role=session.get("role"),
        name=session.get("name"),
        hashed_id=session.get("hashed_id")
    ))
    return make_no_cache_response(response)


@app.route("/admin/doctor-review", methods=["GET", "POST"])
def admin_doctor_review():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(post_login_redirect())

    if request.method == "GET":
        return render_template(
            "admin_doctor_review.html",
            verified=False,
            pending_doctors=[],
            error="",
            success=""
        )

    password = (request.form.get("password") or "").strip()
    if not password:
        return render_template(
            "admin_doctor_review.html",
            verified=False,
            pending_doctors=[],
            error="Please enter your password to continue.",
            success=""
        )

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, password
        FROM users
        WHERE id=%s AND role='admin'
        LIMIT 1
    """, (session["user_id"],))
    admin_user = cur.fetchone()
    cur.close()
    db.close()

    if not admin_user:
        return redirect(url_for("logout"))

    stored_password = admin_user.get("password") or ""
    password_is_valid = False
    if stored_password.startswith(("pbkdf2:", "scrypt:")):
        password_is_valid = check_password_hash(stored_password, password)
    else:
        password_is_valid = hmac.compare_digest(stored_password, password)

    if not password_is_valid:
        return render_template(
            "admin_doctor_review.html",
            verified=False,
            pending_doctors=[],
            error="Incorrect password.",
            success=""
        )

    return render_template(
        "admin_doctor_review.html",
        verified=True,
        pending_doctors=get_pending_doctor_accounts(),
        error="",
        success=""
    )


@app.route("/admin/doctor-review/<int:doctor_id>/approve", methods=["POST"])
def admin_approve_doctor(doctor_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(post_login_redirect())

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE users
        SET approval_status='approved'
        WHERE id=%s AND role='doctor' AND approval_status='pending'
    """, (doctor_id,))
    changed = cur.rowcount
    db.commit()
    cur.close()
    db.close()

    if changed:
        log_action(session["user_id"], "APPROVE_DOCTOR_ACCOUNT", get_client_ip())
        success = "Doctor account approved successfully."
        error = ""
    else:
        success = ""
        error = "That doctor account could not be approved."

    return render_template(
        "admin_doctor_review.html",
        verified=True,
        pending_doctors=get_pending_doctor_accounts(),
        error=error,
        success=success
    )


@app.route("/verify_integrity/<int:record_id>")
def verify_integrity(record_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") not in ("admin", "doctor", "patient"):
        return redirect(post_login_redirect())

    record = require_integrity_access(record_id)
    if not record:
        return redirect(url_for("integrity_dashboard"))

    if session.get("role") == "admin":
        return redirect(url_for("integrity_dashboard", record_id=record_id) + "#node-network")

    snapshot = build_integrity_snapshot(record, session["user_id"])
    response = make_response(render_template(
        "verify_record.html",
        record=record,
        snapshot=snapshot,
        role=session.get("role"),
        name=session.get("name"),
        hashed_id=session.get("hashed_id")
    ))
    return make_no_cache_response(response)


@app.route("/record-history/<int:record_id>")
def record_history(record_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") not in ("admin", "doctor", "patient"):
        return redirect(post_login_redirect())

    record = require_integrity_access(record_id)
    if not record:
        return redirect(url_for("integrity_dashboard"))

    if session.get("role") == "admin":
        return redirect(url_for("integrity_dashboard", record_id=record_id) + "#reference-hashes")

    latest_version = ensure_record_version_seed(record)
    response = make_response(render_template(
        "record_history.html",
        record=record,
        versions=get_record_versions(record_id),
        change_requests=get_record_change_requests(record_id),
        latest_version=latest_version,
        role=session.get("role"),
        name=session.get("name"),
        hashed_id=session.get("hashed_id")
    ))
    return make_no_cache_response(response)


@app.route("/simulate/node_down", methods=["POST"])
def simulate_node_down():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(post_login_redirect())

    record_id = request.form.get("record_id", type=int)
    node_name = (request.form.get("node_name") or "").strip()
    record = require_integrity_access(record_id) if record_id else None
    if not record:
        return redirect(url_for("integrity_dashboard"))

    latest_version = ensure_record_version_seed(record)
    ensure_integrity_node_rows(record_id, latest_version["data_hash"], latest_version["version_no"])
    set_node_behavior(record_id, node_name, "offline")
    log_action(session["user_id"], "SIMULATE_NODE_DOWN", get_client_ip())
    return redirect(url_for("verify_integrity", record_id=record_id))


@app.route("/simulate/delay", methods=["POST"])
def simulate_delay():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(post_login_redirect())

    record_id = request.form.get("record_id", type=int)
    node_name = (request.form.get("node_name") or "").strip()
    record = require_integrity_access(record_id) if record_id else None
    if not record:
        return redirect(url_for("integrity_dashboard"))

    latest_version = ensure_record_version_seed(record)
    ensure_integrity_node_rows(record_id, latest_version["data_hash"], latest_version["version_no"])
    set_node_behavior(record_id, node_name, "delayed")
    log_action(session["user_id"], "SIMULATE_NODE_DELAY", get_client_ip())
    return redirect(url_for("verify_integrity", record_id=record_id))


@app.route("/simulate/attack", methods=["POST"])
def simulate_attack():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(post_login_redirect())

    record_id = request.form.get("record_id", type=int)
    node_name = (request.form.get("node_name") or "").strip()
    record = require_integrity_access(record_id) if record_id else None
    if not record:
        return redirect(url_for("integrity_dashboard"))

    latest_version = ensure_record_version_seed(record)
    ensure_integrity_node_rows(record_id, latest_version["data_hash"], latest_version["version_no"])
    set_node_behavior(record_id, node_name, "compromised")
    log_action(session["user_id"], "SIMULATE_ATTACK_NODE", get_client_ip())
    return redirect(url_for("verify_integrity", record_id=record_id))


@app.route("/simulate/tamper", methods=["POST"])
def simulate_tamper():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(post_login_redirect())

    record_id = request.form.get("record_id", type=int)
    record = require_integrity_access(record_id) if record_id else None
    if not record:
        return redirect(url_for("integrity_dashboard"))

    ensure_record_version_seed(record)
    toggle_record_tamper(record)
    log_action(session["user_id"], "SIMULATE_DB_TAMPER", get_client_ip())
    return redirect(url_for("verify_integrity", record_id=record_id))


@app.route("/record-version/create", methods=["POST"])
def create_record_version():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "doctor":
        return redirect(url_for("integrity_dashboard"))

    record_id = request.form.get("record_id", type=int)
    record = require_integrity_access(record_id) if record_id else None
    if not record:
        return redirect(url_for("integrity_dashboard"))

    create_new_record_version(record, session["user_id"])
    log_action(session["user_id"], "BROADCAST_SIGNED_RECORD_UPDATE", get_client_ip())
    return redirect(url_for("verify_integrity", record_id=record_id))


@app.route("/change-request/check-identity", methods=["POST"])
def check_change_request_identity():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(post_login_redirect())

    change_request_id = request.form.get("change_request_id", type=int)
    node_name = (request.form.get("node_name") or "").strip()
    change_request = get_record_change_request_by_id(change_request_id) if change_request_id else None
    record = require_integrity_access(change_request["record_id"]) if change_request else None
    if not change_request or not record or change_request["request_status"] != "broadcast":
        return redirect(url_for("integrity_dashboard"))

    node_row = next((node for node in get_integrity_node_rows(record["id"]) if node["node_name"] == node_name), None)
    if not node_row:
        return redirect(url_for("verify_integrity", record_id=record["id"]))

    verified, note = node_can_verify_identity(node_name, node_row["behavior_mode"])
    now = datetime.now()

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE record_change_node_votes
        SET identity_checked=1,
            identity_verified=%s,
            reviewed_at=%s,
            note=%s
        WHERE change_request_id=%s AND node_name=%s
    """, (1 if verified else 0, now, note, change_request_id, node_name))
    cur.execute("""
        UPDATE integrity_node_states
        SET signature_verified=%s,
            sync_status=%s,
            status_note=%s,
            last_verification_time=%s
        WHERE record_id=%s AND node_name=%s
    """, (
        1 if verified else 0,
        "pending" if verified else ("offline" if node_row["behavior_mode"] == "offline" else "compromised"),
        note,
        now,
        record["id"],
        node_name
    ))
    db.commit()
    cur.close()
    db.close()

    log_action(session["user_id"], "CHECK_CHANGE_REQUEST_IDENTITY", get_client_ip())
    return redirect(url_for("integrity_dashboard", record_id=record["id"]) + "#node-network")


@app.route("/change-request/vote", methods=["POST"])
def vote_on_change_request():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(post_login_redirect())

    change_request_id = request.form.get("change_request_id", type=int)
    node_name = (request.form.get("node_name") or "").strip()
    vote_value = (request.form.get("vote") or "").strip().lower()
    if vote_value not in ("accepted", "rejected"):
        return redirect(url_for("integrity_dashboard"))

    change_request = get_record_change_request_by_id(change_request_id) if change_request_id else None
    record = require_integrity_access(change_request["record_id"]) if change_request else None
    if not change_request or not record or change_request["request_status"] != "broadcast":
        return redirect(url_for("integrity_dashboard"))

    vote_row = next((vote for vote in get_change_request_node_votes(change_request_id) if vote["node_name"] == node_name), None)
    node_row = next((node for node in get_integrity_node_rows(record["id"]) if node["node_name"] == node_name), None)
    if not vote_row or not node_row:
        return redirect(url_for("verify_integrity", record_id=record["id"]))
    if not vote_row["identity_checked"] or not vote_row["identity_verified"]:
        return redirect(url_for("verify_integrity", record_id=record["id"]))

    now = datetime.now()
    note = "Node accepted the signed doctor change request." if vote_value == "accepted" else "Node rejected the signed doctor change request."
    sync_status = "pending" if vote_value == "accepted" else "rejected"
    status = "pending" if vote_value == "accepted" else "mismatch"

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE record_change_node_votes
        SET vote_status=%s,
            reviewed_at=%s,
            note=%s
        WHERE change_request_id=%s AND node_name=%s
    """, (vote_value, now, note, change_request_id, node_name))
    cur.execute("""
        UPDATE integrity_node_states
        SET status=%s,
            sync_status=%s,
            status_note=%s,
            last_verification_time=%s
        WHERE record_id=%s AND node_name=%s
    """, (status, sync_status, note, now, record["id"], node_name))
    db.commit()
    cur.close()
    db.close()

    updated_request = finalize_change_request_if_threshold_met(record, change_request)
    log_action(session["user_id"], "CHANGE_REQUEST_NODE_VOTE", get_client_ip())
    return redirect(url_for("integrity_dashboard", record_id=updated_request["record_id"]) + "#node-network")




@app.route("/wallet-login/nonce", methods=["POST"])
def wallet_login_nonce():
    data = request.get_json(silent=True) or {}
    wallet = (data.get("wallet_address") or "").strip()


    if not wallet:
        return jsonify({"ok": False, "error": "Missing wallet_address"}), 400


    if not Web3.is_address(wallet):
        return jsonify({"ok": False, "error": "Invalid wallet address"}), 400


    wallet = Web3.to_checksum_address(wallet)


    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id FROM users WHERE wallet_address=%s", (wallet,))
    user = cur.fetchone()


    if not user:
        cur.close()
        db.close()
        return jsonify({"ok": False, "error": "Wallet not registered in system"}), 404


    nonce = secrets.token_hex(16)
    challenge = f"E-Health Login Nonce: {nonce}"


    cur2 = db.cursor()
    cur2.execute("UPDATE users SET login_nonce=%s WHERE wallet_address=%s", (challenge, wallet))
    db.commit()


    cur2.close()
    cur.close()
    db.close()


    return jsonify({"ok": True, "challenge": challenge})




@app.route("/wallet-login/verify", methods=["POST"])
def wallet_login_verify():
    data = request.get_json(silent=True) or {}
    wallet = (data.get("wallet_address") or "").strip()
    signature = (data.get("signature") or "").strip()


    if not wallet or not signature:
        return jsonify({"ok": False, "error": "Missing wallet_address or signature"}), 400


    if not Web3.is_address(wallet):
        return jsonify({"ok": False, "error": "Invalid wallet address"}), 400


    wallet = Web3.to_checksum_address(wallet)


    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, role, name, email, hashed_id, wallet_address, login_nonce, approval_status
        FROM users
        WHERE wallet_address=%s
        LIMIT 1
    """, (wallet,))
    user = cur.fetchone()


    if not user or not user.get("login_nonce"):
        cur.close()
        db.close()
        return jsonify({"ok": False, "error": "No active login challenge for this wallet"}), 400


    if user["role"] == "doctor" and user.get("approval_status") == "pending":
        cur.close()
        db.close()
        return jsonify({"ok": False, "error": "Doctor account is pending admin approval"}), 403


    challenge = user["login_nonce"]


    try:
        msg = encode_defunct(text=challenge)
        recovered = Web3().eth.account.recover_message(msg, signature=signature)
        recovered = Web3.to_checksum_address(recovered)
    except Exception as e:
        cur.close()
        db.close()
        return jsonify({"ok": False, "error": f"Signature parse/verify failed: {e}"}), 400


    if recovered != wallet:
        cur.close()
        db.close()
        return jsonify({"ok": False, "error": "Signature does not match wallet address"}), 401


    cur2 = db.cursor()
    cur2.execute("UPDATE users SET login_nonce=NULL WHERE id=%s", (user["id"],))
    db.commit()
    cur2.close()


    cur.close()
    db.close()


    create_authenticated_session(user, "wallet")


    log_action(user["id"], "WALLET_LOGIN_SUCCESS", get_client_ip())


    return jsonify({"ok": True, "redirect": post_login_redirect()})




# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") == "admin":
        return redirect(url_for("integrity_dashboard"))
    if session.get("role") == "storage":
        return redirect(url_for("storage_dashboard"))

    db = get_db()
    cur = db.cursor(dictionary=True)


    if session["role"] == "patient":
        cur.execute("""
            SELECT id, data_hash, blockchain_tx_hash, created_at
            FROM records
            WHERE patient_id=%s
            ORDER BY created_at DESC
        """, (session["user_id"],))
        records = cur.fetchall()


        cur.execute("""
            SELECT ar.id, u.name AS doctor_name, u.email AS doctor_email,
                   ar.status, ar.blockchain_tx_hash, ar.requested_at,
                   ar.prescription_written_at, ar.appointment_id,
                   a.appointment_date,
                   p.id AS prescription_id, p.medicine_name, p.created_at AS prescription_created_at
            FROM access_requests ar
            JOIN users u ON u.id = ar.doctor_id
            LEFT JOIN appointments a ON a.id = ar.appointment_id
            LEFT JOIN prescriptions p ON p.access_request_id = ar.id
            WHERE ar.patient_id=%s
            ORDER BY ar.requested_at DESC
        """, (session["user_id"],))
        requests_list = cur.fetchall()


        cur.close()
        db.close()

        chat_contacts = get_patient_chat_contacts(session["user_id"])
        appointments = get_patient_upcoming_appointments(session["user_id"])
        prescriptions = get_patient_prescriptions(session["user_id"])
        selected_chat_id = request.args.get("doctor_id", type=int)
        if not selected_chat_id and chat_contacts:
            selected_chat_id = chat_contacts[0]["id"]

        selected_contact = None
        chat_messages = []
        if selected_chat_id:
            selected_contact = next((contact for contact in chat_contacts if contact["id"] == selected_chat_id), None)
            if selected_contact:
                chat_messages = get_chat_messages(session["user_id"], selected_chat_id)


        return render_template(
            "patient_dashboard.html",
            name=session["name"],
            hashed_id=session["hashed_id"],
            records=records,
            requests_list=requests_list,
            appointments=appointments,
            prescriptions=prescriptions,
            chat_contacts=chat_contacts,
            selected_contact=selected_contact,
            selected_chat_id=selected_chat_id,
            chat_messages=chat_messages
        )


    cur.execute("""
        SELECT r.id, r.data_hash, r.blockchain_tx_hash, r.created_at, u.name AS patient_name
        FROM records r
        JOIN access_requests ar ON ar.patient_id = r.patient_id
        JOIN users u ON u.id = r.patient_id
        WHERE ar.doctor_id=%s
          AND ar.status='approved'
          AND ar.prescription_written_at IS NULL
        ORDER BY r.created_at DESC
    """, (session["user_id"],))
    records = cur.fetchall()


    cur.close()
    db.close()

    appointment_patients = get_doctor_appointment_patients(session["user_id"])
    appointments = get_doctor_appointments(session["user_id"])
    pending_appointment_requests = [appt for appt in appointments if appt["status"] == "pending"]
    scheduled_appointments = [appt for appt in appointments if appt["status"] == "approved"]
    accessible_patients = get_doctor_accessible_patients(session["user_id"])
    available_medicines = get_available_medicine_names()
    chat_contacts = get_doctor_chat_contacts(session["user_id"])
    selected_chat_id = request.args.get("patient_id", type=int)
    if not selected_chat_id and appointment_patients:
        selected_chat_id = appointment_patients[0]["id"]
    if not selected_chat_id and chat_contacts:
        selected_chat_id = chat_contacts[0]["id"]

    selected_contact = None
    chat_messages = []
    if selected_chat_id:
        selected_contact = next((contact for contact in appointment_patients if contact["id"] == selected_chat_id), None)
        if not selected_contact:
            selected_contact = next((contact for contact in chat_contacts if contact["id"] == selected_chat_id), None)
        if selected_contact:
            chat_messages = get_chat_messages(selected_chat_id, session["user_id"])

    selected_medical_patient = None
    prescriptions = []
    selected_prescription_stage = "idle"
    selected_prescription_status_label = "Ready to save"
    selected_prescription_status_note = "Once you save a prescription, it will be approved by the node chain and then written to the trusted ledger."
    if selected_chat_id and doctor_has_medical_access(session["user_id"], selected_chat_id):
        selected_medical_patient = get_patient_private_details(selected_chat_id)
        prescriptions = get_prescriptions_for_patient(session["user_id"], selected_chat_id)
        selected_access_request = None
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("""
            SELECT id, status, prescription_written_at, appointment_id
            FROM access_requests
            WHERE doctor_id=%s AND patient_id=%s
            ORDER BY requested_at DESC, id DESC
            LIMIT 1
        """, (session["user_id"], selected_chat_id))
        selected_access_request = cur.fetchone()
        cur.close()
        db.close()

        selected_record = get_accessible_record_for_patient(selected_chat_id, session["user_id"], "doctor")
        selected_snapshot = build_integrity_snapshot(selected_record, session["user_id"]) if selected_record else None

        if selected_access_request and selected_access_request.get("prescription_written_at"):
            pending_change = selected_snapshot.get("pending_change_request") if selected_snapshot else None
            latest_change = selected_snapshot.get("latest_change_request") if selected_snapshot else None
            if pending_change and pending_change.get("request_status") == "broadcast":
                selected_prescription_stage = "waiting_chain"
                selected_prescription_status_label = "Approved - waiting for the chain to approve"
                selected_prescription_status_note = "The prescription is written and waiting for the admin node chain to approve it and push it to Ganache."
            elif latest_change and latest_change.get("request_status") == "ledger_anchored":
                selected_prescription_stage = "complete"
                selected_prescription_status_label = "Complete"
                selected_prescription_status_note = "The prescription has been approved by the chain and stored in the trusted ledger."
            elif latest_change and latest_change.get("request_status") == "rejected":
                selected_prescription_stage = "rejected"
                selected_prescription_status_label = "Rejected"
                selected_prescription_status_note = "The chain rejected this update. Revise the prescription and submit a fresh version."
            else:
                selected_prescription_stage = "waiting_chain"
                selected_prescription_status_label = "Approved - waiting for the chain to approve"
                selected_prescription_status_note = "The prescription has been saved and is waiting for the admin node chain to finalize it on Ganache."
        else:
            selected_prescription_stage = "idle"
            selected_prescription_status_label = "Ready to save"
            selected_prescription_status_note = "Save a prescription to start the approval flow. The chain stage will appear here after that."


    return render_template(
        "dashboard_doctor.html",
        name=session["name"],
        hashed_id=session["hashed_id"],
        records=records,
        appointment_patients=appointment_patients,
        accessible_patients=accessible_patients,
        appointments=appointments,
        pending_appointment_requests=pending_appointment_requests,
        scheduled_appointments=scheduled_appointments,
        chat_contacts=chat_contacts,
        selected_contact=selected_contact,
        selected_medical_patient=selected_medical_patient,
        selected_chat_id=selected_chat_id,
        chat_messages=chat_messages,
        prescriptions=prescriptions,
        available_medicines=available_medicines,
        selected_prescription_stage=selected_prescription_stage,
        selected_prescription_status_label=selected_prescription_status_label,
        selected_prescription_status_note=selected_prescription_status_note,
        doctor_feedback=request.args.get("doctor_feedback", ""),
        doctor_feedback_type=request.args.get("doctor_feedback_type", "success"),
        doctor_feedback_title=request.args.get("doctor_feedback_title", ""),
        doctor_feedback_badge=request.args.get("doctor_feedback_badge", ""),
        doctor_feedback_seconds=request.args.get("doctor_feedback_seconds", type=int) or 5
    )




# =========================
# DOCTOR / PATIENT ACTIONS
# =========================
@app.route("/doctor/request/<int:patient_id>", methods=["POST"])
def doctor_request(patient_id):
    if session.get("role") != "doctor":
        return redirect(url_for("dashboard"))

    latest_appointment = get_latest_booked_appointment(session["user_id"], patient_id)
    if not latest_appointment:
        return redirect(url_for("dashboard"))

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, status, prescription_written_at
        FROM access_requests
        WHERE patient_id=%s AND doctor_id=%s AND appointment_id=%s
        ORDER BY requested_at DESC
        LIMIT 1
    """, (patient_id, session["user_id"], latest_appointment["id"]))
    existing_request = cur.fetchone()

    if existing_request and existing_request["status"] == "pending" and not existing_request["prescription_written_at"]:
        cur.close()
        db.close()
        return redirect(url_for("dashboard", patient_id=patient_id))

    if existing_request and existing_request["status"] == "approved" and not existing_request["prescription_written_at"]:
        cur.close()
        db.close()
        return redirect(url_for("dashboard", patient_id=patient_id))

    cur2 = db.cursor()
    if existing_request and existing_request["status"] == "rejected" and not existing_request["prescription_written_at"]:
        cur2.execute("""
            UPDATE access_requests
            SET status='pending',
                blockchain_tx_hash=NULL,
                requested_at=CURRENT_TIMESTAMP,
                prescription_written_at=NULL
            WHERE id=%s
        """, (existing_request["id"],))
    else:
        cur2.execute(
            "INSERT INTO access_requests(patient_id, doctor_id, appointment_id, status) VALUES (%s,%s,%s,'pending')",
            (patient_id, session["user_id"], latest_appointment["id"])
        )
    db.commit()
    cur2.close()
    cur.close()
    db.close()


    log_action(session["user_id"], "REQUEST_ACCESS", get_client_ip())
    return redirect(url_for(
        "dashboard",
        patient_id=patient_id,
        doctor_feedback="Request sent successfully.",
        doctor_feedback_type="success",
        doctor_feedback_title="Medical Access Requested",
        doctor_feedback_badge="Sent",
        doctor_feedback_seconds=5
    ))


@app.route("/patient/request-appointment/<int:doctor_id>", methods=["POST"])
def patient_request_appointment(doctor_id):
    if session.get("role") != "patient":
        return redirect(url_for("dashboard"))

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, approval_status
        FROM users
        WHERE id=%s AND role='doctor'
        LIMIT 1
    """, (doctor_id,))
    doctor = cur.fetchone()

    if not doctor:
        cur.close()
        db.close()
        return redirect(url_for(
            "patient_home",
            appointment_feedback="Doctor not found.",
            appointment_feedback_type="error"
        ))

    if doctor["approval_status"] != "approved":
        cur.close()
        db.close()
        return redirect(url_for(
            "patient_home",
            appointment_feedback="This doctor is not available for appointments yet.",
            appointment_feedback_type="error"
        ))

    cur.execute("""
        SELECT id
        FROM appointments
        WHERE patient_id=%s AND doctor_id=%s AND status='pending'
        LIMIT 1
    """, (session["user_id"], doctor_id))
    existing_request = cur.fetchone()

    if not existing_request:
        cur2 = db.cursor()
        cur2.execute("""
            INSERT INTO appointments (patient_id, doctor_id, appointment_date, status)
            VALUES (%s, %s, NULL, 'pending')
        """, (session["user_id"], doctor_id))
        db.commit()
        cur2.close()
        log_action(session["user_id"], "REQUEST_APPOINTMENT", get_client_ip())
        feedback_message = "Appointment request sent successfully."
        feedback_type = "success"
    else:
        feedback_message = "You already have a pending request with this doctor."
        feedback_type = "error"

    cur.close()
    db.close()
    return redirect(url_for(
        "patient_home",
        appointment_feedback=feedback_message,
        appointment_feedback_type=feedback_type
    ))


@app.route("/doctor/appointments/approve/<int:appointment_id>", methods=["POST"])
def doctor_approve_appointment(appointment_id):
    if session.get("role") != "doctor":
        return redirect(url_for("dashboard"))

    appointment_date = request.form.get("appointment_date", "").strip()
    notes = request.form.get("notes", "").strip()

    if not appointment_date:
        return redirect(url_for("dashboard"))

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE appointments
        SET status='approved', appointment_date=%s, notes=%s
        WHERE id=%s AND doctor_id=%s AND status='pending'
    """, (appointment_date, notes or None, appointment_id, session["user_id"]))
    db.commit()
    cur.close()
    db.close()

    log_action(session["user_id"], "APPROVE_APPOINTMENT", get_client_ip())
    return redirect(url_for("dashboard"))


@app.route("/doctor/appointments/reject/<int:appointment_id>", methods=["POST"])
def doctor_reject_appointment(appointment_id):
    if session.get("role") != "doctor":
        return redirect(url_for("dashboard"))

    patient_id = request.form.get("patient_id", type=int)
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE appointments
        SET status='rejected'
        WHERE id=%s AND doctor_id=%s AND status='pending'
    """, (appointment_id, session["user_id"]))
    db.commit()
    cur.close()
    db.close()

    log_action(session["user_id"], "REJECT_APPOINTMENT", get_client_ip())
    return redirect(url_for(
        "dashboard",
        patient_id=patient_id,
        doctor_feedback="Appointment request rejected.",
        doctor_feedback_type="error",
        doctor_feedback_title="Appointment Rejected",
        doctor_feedback_badge="Updated",
        doctor_feedback_seconds=5
    ))


@app.route("/doctor/prescribe", methods=["POST"])
def doctor_prescribe():
    if session.get("role") != "doctor":
        return redirect(url_for("dashboard"))

    patient_id = request.form.get("patient_id", type=int)
    medicine_name = request.form.get("medicine_name", "").strip()
    dosage = request.form.get("dosage", "").strip()
    instructions = request.form.get("instructions", "").strip()

    if not patient_id or not medicine_name or not dosage or not instructions:
        return redirect(url_for("dashboard", patient_id=patient_id))

    if not doctor_has_medical_access(session["user_id"], patient_id):
        return redirect(url_for("dashboard", patient_id=patient_id))

    inventory_names = {
        (item.get("medicine_name") or "").strip().lower()
        for item in get_available_medicine_names()
    }
    if medicine_name.lower() not in inventory_names:
        return redirect(url_for("dashboard", patient_id=patient_id))

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, appointment_id
        FROM access_requests
        WHERE doctor_id=%s
          AND patient_id=%s
          AND status='approved'
          AND prescription_written_at IS NULL
        ORDER BY requested_at DESC
        LIMIT 1
    """, (session["user_id"], patient_id))
    active_request = cur.fetchone()

    if not active_request:
        cur.close()
        db.close()
        return redirect(url_for("dashboard", patient_id=patient_id))

    appointment_id = active_request["appointment_id"]
    if not appointment_id:
        cur.execute("""
            SELECT id
            FROM appointments
            WHERE doctor_id=%s
              AND patient_id=%s
              AND status='approved'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """, (session["user_id"], patient_id))
        fallback_appointment = cur.fetchone()
        if fallback_appointment:
            appointment_id = fallback_appointment["id"]

    cur2 = db.cursor()
    cur2.execute("""
        INSERT INTO prescriptions (patient_id, doctor_id, appointment_id, access_request_id, medicine_name, dosage, instructions)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        patient_id,
        session["user_id"],
        appointment_id,
        active_request["id"],
        medicine_name,
        dosage,
        instructions
    ))
    cur2.execute("""
        UPDATE access_requests
        SET prescription_written_at=CURRENT_TIMESTAMP,
            appointment_id=COALESCE(appointment_id, %s)
        WHERE id=%s
    """, (appointment_id, active_request["id"]))
    if appointment_id:
        cur2.execute("""
            UPDATE appointments
            SET status='completed'
            WHERE id=%s AND doctor_id=%s AND patient_id=%s
        """, (appointment_id, session["user_id"], patient_id))
    db.commit()
    cur2.close()
    cur.close()
    db.close()

    record = get_accessible_record_for_patient(patient_id, session["user_id"], "doctor")
    if record:
        create_new_record_version(record, session["user_id"])

    log_action(session["user_id"], "WRITE_PRESCRIPTION", get_client_ip())
    return redirect(url_for(
        "dashboard",
        patient_id=patient_id,
        doctor_feedback="Prescription saved successfully.",
        doctor_feedback_type="success",
        doctor_feedback_title="Prescription Written",
        doctor_feedback_badge="Saved",
        doctor_feedback_seconds=5
    ))




@app.route("/patient/approve/<int:req_id>", methods=["POST"])
def patient_approve(req_id):
    if session.get("role") != "patient":
        return redirect(url_for("dashboard"))


    db = get_db()
    cur = db.cursor(dictionary=True)


    cur.execute("""
        SELECT ar.id,
               p.hashed_id AS patient_hash
        FROM access_requests ar
        JOIN users p ON p.id = ar.patient_id
        WHERE ar.id=%s AND ar.patient_id=%s
        LIMIT 1
    """, (req_id, session["user_id"]))


    row = cur.fetchone()
    if not row:
        cur.close()
        db.close()
        return "Invalid request or not allowed", 400


    patient_hash_hex = row["patient_hash"]


    try:
        tx_hash = build_approval_tx_hash(patient_hash_hex)
    except Exception as e:
        cur.close()
        db.close()
        return f"Blockchain error: {e}", 500


    cur2 = db.cursor()
    cur2.execute("""
        UPDATE access_requests
        SET status='approved', blockchain_tx_hash=%s
        WHERE id=%s AND patient_id=%s
    """, (tx_hash, req_id, session["user_id"]))


    db.commit()
    cur2.close()
    cur.close()
    db.close()


    log_action(session["user_id"], "APPROVE_ACCESS_ONCHAIN", get_client_ip())
    return redirect(url_for(
        "patient_home",
        appointment_feedback="Access is granted.",
        appointment_feedback_type="success",
        appointment_feedback_title="Medical Access Approved",
        appointment_feedback_badge="Access granted",
        appointment_feedback_seconds=5
    ))


@app.route("/patient/decline/<int:req_id>", methods=["POST"])
def patient_decline(req_id):
    if session.get("role") != "patient":
        return redirect(url_for("dashboard"))

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE access_requests
        SET status='rejected'
        WHERE id=%s AND patient_id=%s AND status='pending'
    """, (req_id, session["user_id"]))
    db.commit()
    cur.close()
    db.close()

    log_action(session["user_id"], "DECLINE_ACCESS_REQUEST", get_client_ip())
    return redirect(url_for(
        "patient_home",
        appointment_feedback="Request rejected successfully.",
        appointment_feedback_type="error",
        appointment_feedback_title="Access Request Rejected",
        appointment_feedback_badge="Rejected",
        appointment_feedback_seconds=5
    ))


@app.route("/chat/send", methods=["POST"])
def send_chat_message():
    if "user_id" not in session:
        return redirect(url_for("login"))

    is_fetch_request = request.headers.get("X-Requested-With") == "fetch"
    message_text = request.form.get("message_text", "").strip()
    if not message_text:
        if is_fetch_request:
            return jsonify({"ok": False, "error": "Message cannot be empty."}), 400
        return redirect(url_for("dashboard"))

    db = get_db()
    cur = db.cursor(dictionary=True)

    if session.get("role") == "patient":
        doctor_id = request.form.get("doctor_id", type=int)
        if not doctor_id:
            cur.close()
            db.close()
            if is_fetch_request:
                return jsonify({"ok": False, "error": "Select a doctor first."}), 400
            return redirect(url_for("dashboard"))

        cur.execute("""
            SELECT 1
            FROM access_requests
            WHERE patient_id=%s AND doctor_id=%s
            LIMIT 1
        """, (session["user_id"], doctor_id))
        allowed = cur.fetchone()
        if not allowed:
            cur.close()
            db.close()
            if is_fetch_request:
                return jsonify({"ok": False, "error": "That doctor is not linked to your account."}), 403
            return redirect(url_for("dashboard"))

        cur2 = db.cursor()
        cur2.execute("""
            INSERT INTO messages (patient_id, doctor_id, sender_id, sender_role, message_text)
            VALUES (%s, %s, %s, 'patient', %s)
        """, (session["user_id"], doctor_id, session["user_id"], message_text))
        db.commit()
        cur2.close()
        cur.close()
        db.close()
        log_action(session["user_id"], "PATIENT_SENT_MESSAGE", get_client_ip())
        if is_fetch_request:
            return jsonify({
                "ok": True,
                "message_text": message_text,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
        return redirect(url_for("dashboard", doctor_id=doctor_id) + "#chat-panel")

    patient_id = request.form.get("patient_id", type=int)
    if not patient_id:
        cur.close()
        db.close()
        if is_fetch_request:
            return jsonify({"ok": False, "error": "Select a patient first."}), 400
        return redirect(url_for("dashboard"))

    cur.execute("""
        SELECT 1
        FROM (
            SELECT patient_id, doctor_id FROM access_requests
            UNION
            SELECT patient_id, doctor_id FROM appointments
        ) rel
        WHERE patient_id=%s AND doctor_id=%s
        LIMIT 1
    """, (patient_id, session["user_id"]))
    allowed = cur.fetchone()
    if not allowed:
        cur.close()
        db.close()
        if is_fetch_request:
            return jsonify({"ok": False, "error": "You do not have access to that patient."}), 403
        return redirect(url_for("dashboard"))

    cur2 = db.cursor()
    cur2.execute("""
        INSERT INTO messages (patient_id, doctor_id, sender_id, sender_role, message_text)
        VALUES (%s, %s, %s, 'doctor', %s)
    """, (patient_id, session["user_id"], session["user_id"], message_text))
    db.commit()
    cur2.close()
    cur.close()
    db.close()
    log_action(session["user_id"], "DOCTOR_SENT_MESSAGE", get_client_ip())
    if is_fetch_request:
        return jsonify({
            "ok": True,
            "message_text": message_text,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
    return redirect(url_for("dashboard", patient_id=patient_id) + "#chat-panel")




@app.route("/logout")
def logout():
    if "user_id" in session:
        log_action(session["user_id"], "LOGOUT", get_client_ip())
    revoke_current_auth_session()
    session.clear()
    return redirect(url_for("home"))




if __name__ == "__main__":
    app.run(debug=True)
