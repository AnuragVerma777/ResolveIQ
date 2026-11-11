"""Automated tests for FastAPI endpoints:

document upload, preview, extraction, dispute association, and AI classification.
"""
import io
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.main import app
from tests.test_document_pipeline import create_dummy_docx, create_dummy_pdf


@pytest.fixture
def client():
    # Use local workspace directory for temp files to avoid Windows Temp PermissionErrors
    temp_dir = Path("test_scratch")
    temp_dir.mkdir(parents=True, exist_ok=True)
    sub_dir = Path(tempfile.mkdtemp(dir=str(temp_dir)))
    test_db = str(sub_dir / "test_resolveiq.db")
    test_uploads = str(sub_dir / "test_uploads")

    def override_settings():
        return Settings(
            db_path=test_db,
            upload_dir=test_uploads,
            max_upload_size_mb=2,
            gemini_api_key="",  # Test deterministic fallback
        )

    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    shutil.rmtree(sub_dir, ignore_errors=True)


def test_health_check_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "2.0.0"
    assert "paypal_client_secret" not in data  # Never expose secrets!


def test_upload_pdf_document_pipeline(client):
    pdf_bytes = create_dummy_pdf("Order ID: ORD-9988\nTotal: $120.00 USD\nTracking Number: 940012345678")
    files = {"file": ("test_invoice.pdf", pdf_bytes, "application/pdf")}
    data = {"dispute_id": "DISP-100", "doc_type": "invoice"}

    response = client.post("/api/documents/upload", files=files, data=data)
    assert response.status_code == 201
    doc = response.json()
    assert doc["filename"] == "test_invoice.pdf"
    assert doc["dispute_id"] == "DISP-100"
    assert doc["doc_type"] == "invoice"
    assert doc["status"] == "COMPLETED"
    assert "ORD-9988" in doc["raw_text"]
    assert doc["extracted_fields"]["order_id"] == "ORD-9988"
    assert doc["extracted_fields"]["amount"] == 120.0
    assert doc["extracted_fields"]["currency"] == "USD"
    assert doc["extracted_fields"]["tracking_number"] == "940012345678"


def test_upload_docx_document_pipeline(client):
    docx_bytes = create_dummy_docx(["Delivery Confirmation", "Order ID: ORD-7711", "Delivered: 2026-04-18"])
    files = {"file": ("delivery.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    data = {"dispute_id": "DISP-100", "doc_type": "delivery_confirmation"}

    response = client.post("/api/documents/upload", files=files, data=data)
    assert response.status_code == 201
    doc = response.json()
    assert doc["status"] == "COMPLETED"
    assert "ORD-7711" in doc["raw_text"]
    assert doc["extracted_fields"]["order_id"] == "ORD-7711"


def test_upload_rejects_executable_extension(client):
    files = {"file": ("malware.exe", b"binary content", "application/octet-stream")}
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 400
    assert "prohibited" in response.json()["detail"].lower()


def test_upload_rejects_oversized_file(client):
    # Test settings limit is 2MB
    huge_data = b"X" * (3 * 1024 * 1024)
    files = {"file": ("big_doc.pdf", huge_data, "application/pdf")}
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code in {400, 413}


def test_document_listing_and_text_retrieval(client):
    # Upload one doc
    pdf_bytes = create_dummy_pdf("Customer: Sarah Connor\nAmount: $75.00 USD")
    files = {"file": ("receipt.pdf", pdf_bytes, "application/pdf")}
    upload_res = client.post("/api/documents/upload", files=files, data={"dispute_id": "DISP-200"})
    doc_id = upload_res.json()["id"]

    # List all documents
    list_res = client.get("/api/documents")
    assert list_res.status_code == 200
    all_docs = list_res.json()
    assert any(d["id"] == doc_id for d in all_docs)

    # Filter by dispute_id
    filter_res = client.get("/api/documents?dispute_id=DISP-200")
    assert filter_res.status_code == 200
    assert len(filter_res.json()) == 1

    # Get text
    text_res = client.get(f"/api/documents/{doc_id}/text")
    assert text_res.status_code == 200
    assert "Sarah Connor" in text_res.json()["text"]

    # Preview and download
    prev_res = client.get(f"/api/documents/{doc_id}/preview")
    assert prev_res.status_code == 200
    assert prev_res.headers["content-disposition"].startswith("inline")

    down_res = client.get(f"/api/documents/{doc_id}/download")
    assert down_res.status_code == 200
    assert down_res.headers["content-disposition"].startswith("attachment")


def test_document_associate_endpoint(client):
    pdf_bytes = create_dummy_pdf("Order ID: ORD-3322")
    files = {"file": ("doc.pdf", pdf_bytes, "application/pdf")}
    upload_res = client.post("/api/documents/upload", files=files)
    doc_id = upload_res.json()["id"]
    assert upload_res.json()["dispute_id"] is None

    # Associate with dispute
    assoc_res = client.post(f"/api/documents/{doc_id}/associate", json={"dispute_id": "DISP-555"})
    assert assoc_res.status_code == 200
    assert assoc_res.json()["dispute_id"] == "DISP-555"

    # Query dispute documents
    disp_docs = client.get("/api/disputes/DISP-555/documents")
    assert disp_docs.status_code == 200
    assert len(disp_docs.json()) == 1


def test_dispute_classification_endpoint(client):
    # Upload an evidence document first
    pdf_bytes = create_dummy_pdf("Tracking Number: 1Z882233\nDelivered: 2026-05-01\nOrder ID: ORD-8888")
    files = {"file": ("tracking.pdf", pdf_bytes, "application/pdf")}
    upload_res = client.post("/api/documents/upload", files=files, data={"dispute_id": "DISP-900"})
    doc_id = upload_res.json()["id"]

    # Classify dispute
    classify_payload = {
        "dispute_id": "DISP-900",
        "dispute_reason": "ITEM_NOT_RECEIVED",
        "customer_complaint": "Buyer states parcel did not arrive at door.",
        "transaction_details": {"transaction_id": "TX-1002", "amount": 89.99, "currency": "USD"},
        "merchant_context": "Merchant confirmed package delivered via UPS.",
        "document_ids": [doc_id],
    }

    res = client.post("/api/disputes/classify", json=classify_payload)
    assert res.status_code == 200
    data = res.json()

    assert data["dispute_id"] == "DISP-900"
    assert data["original_paypal_reason"] == "ITEM_NOT_RECEIVED"
    assert data["dispute_category"] == "item_not_received"
    assert isinstance(data["explanation"], str)
    assert isinstance(data["key_facts"], list)
    assert isinstance(data["recommended_next_actions"], list)
    assert "confidence" in data
    assert "level" in data["confidence"]
    assert "score" in data["confidence"]
    assert "disclaimer" in data
    assert "not probability of winning" in data["disclaimer"].lower()

    # Verify dispute details endpoint returns latest classification
    disp_res = client.get("/api/disputes/DISP-900")
    assert disp_res.status_code == 200
    disp_data = disp_res.json()
    assert disp_data["latest_classification"] is not None
    assert disp_data["latest_classification"]["dispute_category"] == "item_not_received"
    assert disp_data["document_count"] == 1
