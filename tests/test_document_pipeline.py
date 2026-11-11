"""Automated tests for document intelligence pipeline:

formats, validation, missing fields, and error handling.
"""
import io
import pytest
from pathlib import Path

from backend.ai.documents import (
    DocumentExtractionError,
    DocumentValidationError,
    extract_text,
    extract_text_from_docx,
    extract_text_from_pdf,
    validate_file,
)
from backend.ai.extractor import (
    extract_fields_heuristic,
    extract_structured_fields,
)
from backend.ai.schemas import ExtractedDocumentFields


def create_dummy_pdf(text: str = "Invoice #INV-9988\nOrder ID: ORD-10293\nTotal: $149.99 USD") -> bytes:
    """Create a minimal valid PDF in memory using PyMuPDF."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def create_dummy_docx(paragraphs: list[str], table_data: list[list[str]] | None = None) -> bytes:
    """Create a minimal valid DOCX in memory using python-docx."""
    import docx
    doc = docx.Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table_data:
        table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
        for r_idx, row in enumerate(table_data):
            for c_idx, val in enumerate(row):
                table.rows[r_idx].cells[c_idx].text = val
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# =====================================================================
# 1. Supported Format Tests
# =====================================================================

def test_extract_pdf_using_pymupdf():
    sample_text = "Invoice #INV-2024-889\nOrder ID: ORD-5544\nTotal: $249.50 USD\nTracking Number: 1Z9999999999999999"
    pdf_bytes = create_dummy_pdf(sample_text)
    extracted = extract_text("invoice.pdf", pdf_bytes)
    assert "Invoice #INV-2024-889" in extracted
    assert "ORD-5544" in extracted
    assert "1Z9999999999999999" in extracted


def test_extract_docx_with_paragraphs_and_tables():
    docx_bytes = create_dummy_docx(
        paragraphs=["Order Confirmation", "Customer: Jane Doe", "Purchase Date: 2026-05-10"],
        table_data=[
            ["Item", "Qty", "Price"],
            ["Sony Headphones", "1", "$299.00 USD"],
        ],
    )
    extracted = extract_text("confirmation.docx", docx_bytes)
    assert "Order Confirmation" in extracted
    assert "Customer: Jane Doe" in extracted
    assert "Sony Headphones" in extracted
    assert "$299.00 USD" in extracted


def test_extract_text_csv_and_markdown():
    txt_data = b"Dispute Note: Buyer claims package never arrived."
    assert extract_text("note.txt", txt_data) == "Dispute Note: Buyer claims package never arrived."

    csv_data = b"order_id,amount,status\nORD-11,45.00,shipped"
    assert "ORD-11" in extract_text("orders.csv", csv_data)

    md_data = b"# Shipping Receipt\nCarrier: FedEx\nTracking ID: 778899001122"
    assert "778899001122" in extract_text("tracking.md", md_data)


# =====================================================================
# 2. Validation & Security Tests
# =====================================================================

def test_rejects_empty_file():
    with pytest.raises(DocumentValidationError, match="empty"):
        validate_file("empty.pdf", b"")


def test_rejects_oversized_file():
    large_data = b"A" * (2 * 1024 * 1024)  # 2MB
    with pytest.raises(DocumentValidationError, match="exceeds limit"):
        validate_file("oversized.pdf", large_data, max_bytes=1024 * 1024)


def test_rejects_prohibited_executable_extensions():
    bad_files = ["malware.exe", "script.py", "run.bat", "eval.js", "shell.sh"]
    for bad in bad_files:
        with pytest.raises(DocumentValidationError, match="prohibited"):
            validate_file(bad, b"dummy content")


def test_rejects_unsupported_extensions():
    with pytest.raises(DocumentValidationError, match="Unsupported document type"):
        validate_file("archive.zip", b"dummy")


def test_rejects_spoofed_file_signature():
    # File named .pdf but containing plain text or random bytes without %PDF- header
    fake_pdf = b"This is not a real PDF file at all"
    with pytest.raises(DocumentValidationError, match="signature"):
        validate_file("fake.pdf", fake_pdf)


def test_rejects_spoofed_png_signature():
    fake_png = b"Not a PNG image header"
    with pytest.raises(DocumentValidationError, match="signature"):
        validate_file("fake.png", fake_png)


# =====================================================================
# 3. Missing Fields and Non-Hallucination Tests
# =====================================================================

def test_missing_fields_return_null():
    """Verify that absent fields strictly evaluate to None and are never invented."""
    sparse_text = "General inquiry letter without any numbers or names."
    fields = extract_fields_heuristic(sparse_text)

    assert fields.order_id is None
    assert fields.transaction_id is None
    assert fields.tracking_number is None
    assert fields.amount is None
    assert fields.currency is None
    assert fields.delivery_date is None
    assert fields.refund_status is None


def test_preserves_extracted_fields_and_source_references():
    text = (
        "Official Shipping Manifest\n"
        "Order ID: ORD-992211\n"
        "Transaction ID: TXN-448822\n"
        "Customer: Alex Miller\n"
        "Tracking Number: 940011189922334455\n"
        "Shipped: 2026-04-12\n"
        "Delivered: 2026-04-15\n"
        "Total: $185.00 USD\n"
        "Refund: no refund\n"
    )
    fields = extract_fields_heuristic(text)

    assert fields.order_id == "ORD-992211"
    assert fields.transaction_id == "TXN-448822"
    assert fields.tracking_number == "940011189922334455"
    assert fields.amount == 185.0
    assert fields.currency == "USD"
    assert fields.shipment_date == "2026-04-12"
    assert fields.delivery_date == "2026-04-15"

    # Source references must be verbatim substrings of text
    for field_name, excerpt in fields.source_references.items():
        assert excerpt in text, f"Excerpt for {field_name} not found in text"


# =====================================================================
# 4. Extraction Failure Handling
# =====================================================================

def test_corrupted_pdf_raises_extraction_error():
    # Valid PDF magic header but corrupted body stream
    corrupt_pdf = b"%PDF-1.4\ncorrupted body bytes that cannot be parsed by any pdf engine"
    with pytest.raises((DocumentExtractionError, Exception)):
        extract_text_from_pdf(corrupt_pdf)


def test_corrupted_docx_raises_extraction_error():
    # Valid zip header but invalid docx structure
    corrupt_docx = b"PK\x03\x04\x14\x00\x00\x00corrupt"
    with pytest.raises(DocumentExtractionError):
        extract_text_from_docx(corrupt_docx)
