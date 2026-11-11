"""SQLite database layer for documents, disputes, and AI classifications."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


def _get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                dispute_id TEXT,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                doc_type TEXT NOT NULL DEFAULT 'other',
                status TEXT NOT NULL DEFAULT 'PENDING',
                error_message TEXT,
                raw_text TEXT,
                extracted_fields TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_documents_dispute_id ON documents(dispute_id);

            CREATE TABLE IF NOT EXISTS disputes (
                dispute_id TEXT PRIMARY KEY,
                reason TEXT,
                customer_complaint TEXT,
                transaction_id TEXT,
                amount REAL,
                currency TEXT,
                merchant_context TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS classifications (
                id TEXT PRIMARY KEY,
                dispute_id TEXT NOT NULL,
                original_paypal_reason TEXT NOT NULL,
                dispute_category TEXT NOT NULL,
                explanation TEXT NOT NULL,
                confidence_level TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                confidence_explanation TEXT NOT NULL,
                key_facts TEXT NOT NULL,
                relevant_evidence TEXT NOT NULL,
                missing_information TEXT NOT NULL,
                potential_contradictions TEXT NOT NULL,
                recommended_next_actions TEXT NOT NULL,
                raw_response TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_classifications_dispute_id ON classifications(dispute_id);

            CREATE TABLE IF NOT EXISTS evidence_matrices (
                id TEXT PRIMARY KEY,
                dispute_id TEXT NOT NULL,
                matrix_report TEXT NOT NULL,
                completeness_score INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_matrices_dispute_id ON evidence_matrices(dispute_id);

            CREATE TABLE IF NOT EXISTS resolution_responses (
                id TEXT PRIMARY KEY,
                dispute_id TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                subject_line TEXT NOT NULL,
                response_letter TEXT NOT NULL,
                structured_payload TEXT NOT NULL,
                is_approved INTEGER NOT NULL DEFAULT 0,
                approved_by TEXT,
                approved_at TEXT,
                submission_status TEXT NOT NULL DEFAULT 'DRAFT',
                submission_debug_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_responses_dispute_id ON resolution_responses(dispute_id);

            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                dispute_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_dispute_id ON audit_logs(dispute_id);

            CREATE TABLE IF NOT EXISTS automation_settings (
                id TEXT PRIMARY KEY DEFAULT 'default',
                webhook_url TEXT NOT NULL DEFAULT '',
                enabled_events TEXT NOT NULL DEFAULT '["dispute.created","dispute.high_priority","evidence.missing","evidence.ready_for_review","dispute.deadline_approaching","dispute.submitted"]',
                is_verified INTEGER NOT NULL DEFAULT 0,
                last_verified_at TEXT,
                timeout_seconds REAL NOT NULL DEFAULT 8.0,
                max_retries INTEGER NOT NULL DEFAULT 2,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                event_name TEXT NOT NULL,
                dispute_id TEXT,
                payload TEXT NOT NULL,
                target_url_masked TEXT NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0,
                status_code INTEGER,
                error TEXT,
                attempts INTEGER NOT NULL DEFAULT 1,
                response_time_ms REAL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_deliveries_created_at ON webhook_deliveries(created_at DESC);
            """
        )


class Database:
    def __init__(self, db_path: str = "storage/resolveiq.db"):
        self.db_path = db_path
        init_db(self.db_path)

    def _conn(self) -> sqlite3.Connection:
        return _get_connection(self.db_path)

    # ----------------- Documents -----------------
    def save_document(self, doc: Mapping[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        fields_json = json.dumps(doc.get("extracted_fields") or {}) if isinstance(doc.get("extracted_fields"), (dict, list)) else (doc.get("extracted_fields") or "{}")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (
                    id, dispute_id, filename, stored_path, file_size, content_type,
                    doc_type, status, error_message, raw_text, extracted_fields,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc["id"],
                    doc.get("dispute_id"),
                    doc["filename"],
                    doc["stored_path"],
                    doc["file_size"],
                    doc["content_type"],
                    doc.get("doc_type", "other"),
                    doc.get("status", "PENDING"),
                    doc.get("error_message"),
                    doc.get("raw_text"),
                    fields_json,
                    doc.get("created_at", now),
                    now,
                ),
            )
        return self.get_document(doc["id"])  # type: ignore

    def update_document(self, doc_id: str, **updates: Any) -> dict[str, Any] | None:
        allowed_cols = {
            "dispute_id", "filename", "stored_path", "file_size", "content_type",
            "doc_type", "status", "error_message", "raw_text", "extracted_fields", "updated_at",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_cols}
        if not filtered:
            return self.get_document(doc_id)
        filtered["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "extracted_fields" in filtered and isinstance(filtered["extracted_fields"], (dict, list)):
            filtered["extracted_fields"] = json.dumps(filtered["extracted_fields"])
        cols = ", ".join(f"{k} = ?" for k in filtered.keys())
        values = list(filtered.values()) + [doc_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE documents SET {cols} WHERE id = ?", values)
        return self.get_document(doc_id)

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("extracted_fields"):
                try:
                    data["extracted_fields"] = json.loads(data["extracted_fields"])
                except Exception:
                    pass
            return data

    def list_documents(self, dispute_id: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if dispute_id:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE dispute_id = ? ORDER BY created_at DESC", (dispute_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
            items = []
            for r in rows:
                d = dict(r)
                if d.get("extracted_fields"):
                    try:
                        d["extracted_fields"] = json.loads(d["extracted_fields"])
                    except Exception:
                        pass
                items.append(d)
            return items

    def delete_document(self, doc_id: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cursor.rowcount > 0

    # ----------------- Disputes -----------------
    def save_dispute(self, dispute: Mapping[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO disputes (
                    dispute_id, reason, customer_complaint, transaction_id, amount,
                    currency, merchant_context, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dispute["dispute_id"],
                    dispute.get("reason"),
                    dispute.get("customer_complaint"),
                    dispute.get("transaction_id"),
                    dispute.get("amount"),
                    dispute.get("currency"),
                    dispute.get("merchant_context"),
                    dispute.get("created_at", now),
                ),
            )
        return self.get_dispute(dispute["dispute_id"])  # type: ignore

    def get_dispute(self, dispute_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM disputes WHERE dispute_id = ?", (dispute_id,)).fetchone()
            return dict(row) if row else None

    # ----------------- Classifications -----------------
    def save_classification(self, classification: Mapping[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO classifications (
                    id, dispute_id, original_paypal_reason, dispute_category, explanation,
                    confidence_level, confidence_score, confidence_explanation,
                    key_facts, relevant_evidence, missing_information,
                    potential_contradictions, recommended_next_actions,
                    raw_response, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    classification["id"],
                    classification["dispute_id"],
                    classification["original_paypal_reason"],
                    classification["dispute_category"],
                    classification["explanation"],
                    classification["confidence_level"],
                    classification["confidence_score"],
                    classification["confidence_explanation"],
                    json.dumps(classification.get("key_facts", [])),
                    json.dumps(classification.get("relevant_evidence", [])),
                    json.dumps(classification.get("missing_information", [])),
                    json.dumps(classification.get("potential_contradictions", [])),
                    json.dumps(classification.get("recommended_next_actions", [])),
                    json.dumps(classification.get("raw_response", {})),
                    classification.get("created_at", now),
                ),
            )
        return self.get_classification(classification["id"])  # type: ignore

    def get_classification(self, classification_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM classifications WHERE id = ?", (classification_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            for k in ["key_facts", "relevant_evidence", "missing_information", "potential_contradictions", "recommended_next_actions", "raw_response"]:
                if data.get(k):
                    try:
                        data[k] = json.loads(data[k])
                    except Exception:
                        pass
            return data

    def get_latest_classification(self, dispute_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM classifications WHERE dispute_id = ? ORDER BY created_at DESC LIMIT 1",
                (dispute_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            for k in ["key_facts", "relevant_evidence", "missing_information", "potential_contradictions", "recommended_next_actions", "raw_response"]:
                if data.get(k):
                    try:
                        data[k] = json.loads(data[k])
                    except Exception:
                        pass
            return data

    def list_classifications(self, dispute_id: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if dispute_id:
                rows = conn.execute(
                    "SELECT * FROM classifications WHERE dispute_id = ? ORDER BY created_at DESC", (dispute_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM classifications ORDER BY created_at DESC").fetchall()
            items = []
            for r in rows:
                d = dict(r)
                for k in ["key_facts", "relevant_evidence", "missing_information", "potential_contradictions", "recommended_next_actions", "raw_response"]:
                    if d.get(k):
                        try:
                            d[k] = json.loads(d[k])
                        except Exception:
                            pass
                items.append(d)
            return items

    # ----------------- Evidence Matrices -----------------
    def save_evidence_matrix(self, report: Mapping[str, Any]) -> dict[str, Any]:
        matrix_id = report.get("id") or str(report["dispute_id"]) + "_" + str(int(datetime.now(timezone.utc).timestamp()))
        now = datetime.now(timezone.utc).isoformat()
        score = report.get("completeness_score", {}).get("overall_score", 0) if isinstance(report.get("completeness_score"), dict) else getattr(report.get("completeness_score"), "overall_score", 0)
        report_json = json.dumps(report) if isinstance(report, dict) else report.model_dump_json()

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_matrices (
                    id, dispute_id, matrix_report, completeness_score, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (matrix_id, report["dispute_id"], report_json, score, now),
            )
        return self.get_latest_evidence_matrix(report["dispute_id"])  # type: ignore

    def get_latest_evidence_matrix(self, dispute_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM evidence_matrices WHERE dispute_id = ? ORDER BY created_at DESC LIMIT 1",
                (dispute_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("matrix_report"):
                try:
                    data["matrix_report"] = json.loads(data["matrix_report"])
                except Exception:
                    pass
            return data

    # ----------------- Resolution Responses & Version History -----------------
    def save_response(self, resp: Mapping[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        payload = resp.get("structured_payload")
        if isinstance(payload, (dict, list)):
            payload_json = json.dumps(payload)
        elif hasattr(payload, "model_dump_json"):
            payload_json = payload.model_dump_json()
        elif isinstance(payload, str):
            payload_json = payload
        else:
            payload_json = json.dumps(resp.get("raw_response", {}))

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO resolution_responses (
                    id, dispute_id, version, subject_line, response_letter,
                    structured_payload, is_approved, approved_by, approved_at,
                    submission_status, submission_debug_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resp["id"],
                    resp["dispute_id"],
                    resp.get("version", 1),
                    resp["subject_line"],
                    resp["response_letter"],
                    payload_json,
                    1 if resp.get("is_approved") else 0,
                    resp.get("approved_by"),
                    resp.get("approved_at"),
                    resp.get("submission_status", "DRAFT"),
                    resp.get("submission_debug_id"),
                    resp.get("created_at", now),
                ),
            )
        return self.get_response(resp["id"])  # type: ignore

    def update_response(self, resp_id: str, **updates: Any) -> dict[str, Any] | None:
        allowed_cols = {
            "subject_line", "response_letter", "structured_payload", "is_approved",
            "approved_by", "approved_at", "submission_status", "submission_debug_id",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_cols}
        if not filtered:
            return self.get_response(resp_id)
        if "is_approved" in filtered:
            filtered["is_approved"] = 1 if filtered["is_approved"] else 0
        if "structured_payload" in filtered and isinstance(filtered["structured_payload"], (dict, list)):
            filtered["structured_payload"] = json.dumps(filtered["structured_payload"])
        cols = ", ".join(f"{k} = ?" for k in filtered.keys())
        values = list(filtered.values()) + [resp_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE resolution_responses SET {cols} WHERE id = ?", values)
        return self.get_response(resp_id)

    def get_response(self, resp_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM resolution_responses WHERE id = ?", (resp_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["is_approved"] = bool(data["is_approved"])
            if data.get("structured_payload"):
                try:
                    data["structured_payload"] = json.loads(data["structured_payload"])
                except Exception:
                    pass
            return data

    def get_latest_response(self, dispute_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM resolution_responses WHERE dispute_id = ? ORDER BY version DESC, created_at DESC LIMIT 1",
                (dispute_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["is_approved"] = bool(data["is_approved"])
            if data.get("structured_payload"):
                try:
                    data["structured_payload"] = json.loads(data["structured_payload"])
                except Exception:
                    pass
            return data

    def list_response_versions(self, dispute_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM resolution_responses WHERE dispute_id = ? ORDER BY version DESC",
                (dispute_id,),
            ).fetchall()
            items = []
            for r in rows:
                d = dict(r)
                d["is_approved"] = bool(d["is_approved"])
                if d.get("structured_payload"):
                    try:
                        d["structured_payload"] = json.loads(d["structured_payload"])
                    except Exception:
                        pass
                items.append(d)
            return items

    # ----------------- Audit Trail Logging -----------------
    def log_audit(
        self,
        dispute_id: str,
        action: str,
        actor: str = "system",
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        log_id = f"aud_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        details_json = json.dumps(details or {})

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (id, dispute_id, action, actor, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (log_id, dispute_id, action, actor, details_json, now),
            )
        return {
            "id": log_id,
            "dispute_id": dispute_id,
            "action": action,
            "actor": actor,
            "details": details or {},
            "timestamp": now,
        }

    def list_audit_logs(self, dispute_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs WHERE dispute_id = ? ORDER BY timestamp DESC",
                (dispute_id,),
            ).fetchall()
            items = []
            for r in rows:
                d = dict(r)
                if d.get("details"):
                    try:
                        d["details"] = json.loads(d["details"])
                    except Exception:
                        pass
                items.append(d)
            return items

    # ----------------- Automation & Zapier Webhook Settings -----------------
    def get_automation_settings(self) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM automation_settings WHERE id = 'default'").fetchone()
            if not row:
                now = datetime.now(timezone.utc).isoformat()
                default_events = json.dumps([
                    "dispute.created",
                    "dispute.high_priority",
                    "evidence.missing",
                    "evidence.ready_for_review",
                    "dispute.deadline_approaching",
                    "dispute.submitted",
                ])
                conn.execute(
                    """
                    INSERT INTO automation_settings (
                        id, webhook_url, enabled_events, is_verified, last_verified_at,
                        timeout_seconds, max_retries, updated_at
                    ) VALUES ('default', '', ?, 0, NULL, 8.0, 2, ?)
                    """,
                    (default_events, now),
                )
                row = conn.execute("SELECT * FROM automation_settings WHERE id = 'default'").fetchone()

            data = dict(row)
            data["is_verified"] = bool(data["is_verified"])
            if isinstance(data.get("enabled_events"), str):
                try:
                    data["enabled_events"] = json.loads(data["enabled_events"])
                except Exception:
                    data["enabled_events"] = []
            return data

    def save_automation_settings(self, settings_dict: Mapping[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        current = self.get_automation_settings()

        webhook_url = settings_dict.get("webhook_url", current.get("webhook_url", "")).strip()
        enabled_events = settings_dict.get("enabled_events", current.get("enabled_events", []))
        if isinstance(enabled_events, (list, set)):
            events_json = json.dumps(list(enabled_events))
        else:
            events_json = json.dumps(current.get("enabled_events", []))

        is_verified = 1 if settings_dict.get("is_verified", current.get("is_verified", False)) else 0
        last_verified_at = settings_dict.get("last_verified_at", current.get("last_verified_at"))
        timeout_seconds = float(settings_dict.get("timeout_seconds", current.get("timeout_seconds", 8.0)))
        max_retries = int(settings_dict.get("max_retries", current.get("max_retries", 2)))

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO automation_settings (
                    id, webhook_url, enabled_events, is_verified, last_verified_at,
                    timeout_seconds, max_retries, updated_at
                ) VALUES ('default', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    webhook_url,
                    events_json,
                    is_verified,
                    last_verified_at,
                    timeout_seconds,
                    max_retries,
                    now,
                ),
            )
        return self.get_automation_settings()

    def save_webhook_delivery(self, delivery: Mapping[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        delivery_id = delivery.get("id") or f"del_{uuid4().hex[:12]}"
        payload_str = json.dumps(delivery.get("payload", {})) if isinstance(delivery.get("payload"), (dict, list)) else str(delivery.get("payload", "{}"))

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO webhook_deliveries (
                    id, event_id, event_name, dispute_id, payload,
                    target_url_masked, delivered, status_code, error,
                    attempts, response_time_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    delivery["event_id"],
                    delivery["event_name"],
                    delivery.get("dispute_id"),
                    payload_str,
                    delivery.get("target_url_masked", ""),
                    1 if delivery.get("delivered") else 0,
                    delivery.get("status_code"),
                    delivery.get("error"),
                    delivery.get("attempts", 1),
                    delivery.get("response_time_ms"),
                    delivery.get("created_at", now),
                ),
            )
        return {
            "id": delivery_id,
            "event_id": delivery["event_id"],
            "event_name": delivery["event_name"],
            "dispute_id": delivery.get("dispute_id"),
            "delivered": bool(delivery.get("delivered")),
            "status_code": delivery.get("status_code"),
            "error": delivery.get("error"),
            "attempts": delivery.get("attempts", 1),
            "response_time_ms": delivery.get("response_time_ms"),
            "created_at": now,
        }

    def list_webhook_deliveries(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM webhook_deliveries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            items = []
            for r in rows:
                d = dict(r)
                d["delivered"] = bool(d["delivered"])
                if d.get("payload"):
                    try:
                        d["payload"] = json.loads(d["payload"])
                    except Exception:
                        pass
                items.append(d)
            return items
