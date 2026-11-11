"""Document management and intelligence API endpoints."""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.ai.documents import (
    DocumentExtractionError,
    DocumentValidationError,
    extract_text,
    validate_file,
)
from backend.ai.extractor import extract_structured_fields
from backend.ai.schemas import (
    DocumentMetadata,
    DocumentPreviewResponse,
    DocumentType,
    ExtractedDocumentFields,
    ProcessingStatus,
)
from backend.config import Settings, get_settings
from backend.db import Database
from backend.security import (
    RateLimit,
    get_current_merchant_id,
    sanitize_filename,
    validate_safe_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_db(settings: Settings = Depends(get_settings)) -> Database:
    return Database(settings.db_path)


class AssociateRequest(BaseModel):
    dispute_id: str


@router.post("/upload", response_model=DocumentMetadata, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    dispute_id: str | None = Form(None),
    doc_type: str = Form("other"),
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
    _rate_limit: None = Depends(RateLimit(max_requests=25, window_seconds=60.0, scope="document_upload")),
):
    """Upload and process a merchant document through the intelligence pipeline.

    Validates file type and size, extracts text using PyMuPDF/python-docx/OCR,
    extracts structured commerce fields, sanitizes storage path against traversal,
    and records metadata in database with audit history.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename")

    safe_filename = sanitize_filename(file.filename)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Read content
    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {str(exc)}")

    # Validate file type, signature, and size
    try:
        suffix = validate_file(safe_filename, content, max_bytes=max_bytes)
    except DocumentValidationError as exc:
        if "exceeds limit" in str(exc):
            raise HTTPException(status_code=413, detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))

    # Generate isolated storage path with path traversal protection
    doc_id = uuid4().hex
    stored_name = f"{doc_id}_{safe_filename}"
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = validate_safe_path(upload_dir / stored_name, upload_dir)

    try:
        destination.write_bytes(content)
    except Exception as exc:
        logger.error("Failed to write document to disk: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to persist document to secure storage")

    # Map content type
    content_type = file.content_type or "application/octet-stream"

    # Map doc_type
    try:
        parsed_doc_type = DocumentType(doc_type.lower())
    except ValueError:
        parsed_doc_type = DocumentType.OTHER

    # Step 1: Extract Text
    raw_text: str | None = None
    extraction_error: str | None = None
    proc_status = ProcessingStatus.EXTRACTING

    try:
        raw_text = extract_text(
            safe_filename,
            content,
            gemini_api_key=settings.gemini_api_key or None,
            max_bytes=max_bytes,
        )
    except Exception as exc:
        logger.warning("Text extraction failed for %s: %s", safe_filename, exc)
        extraction_error = f"Extraction error: {str(exc)}"
        proc_status = ProcessingStatus.FAILED

    # Step 2: Extract Structured Fields (if text is present)
    extracted_fields: ExtractedDocumentFields | None = None
    if raw_text and proc_status != ProcessingStatus.FAILED:
        try:
            extracted_fields = extract_structured_fields(
                raw_text,
                safe_filename,
                gemini_api_key=settings.gemini_api_key or None,
                model=settings.gemini_model,
            )
            proc_status = ProcessingStatus.COMPLETED
        except Exception as exc:
            logger.warning("Structured field extraction encountered an issue: %s", exc)
            proc_status = ProcessingStatus.COMPLETED
            extracted_fields = ExtractedDocumentFields(unextracted_reasons=[str(exc)])

    # Record in database
    doc_record = db.save_document({
        "id": doc_id,
        "dispute_id": dispute_id,
        "filename": safe_filename,
        "stored_path": str(destination),
        "file_size": len(content),
        "content_type": content_type,
        "doc_type": parsed_doc_type.value,
        "status": proc_status.value,
        "error_message": extraction_error,
        "raw_text": raw_text,
        "extracted_fields": extracted_fields.model_dump() if extracted_fields else None,
    })

    # Record evidence upload in audit history
    db.log_audit(
        dispute_id=dispute_id or "UNASSOCIATED",
        action="EVIDENCE_UPLOADED",
        actor=merchant_id,
        details={
            "document_id": doc_id,
            "filename": safe_filename,
            "file_size": len(content),
            "doc_type": parsed_doc_type.value,
            "status": proc_status.value,
        },
    )

    return DocumentMetadata(
        id=doc_record["id"],
        dispute_id=doc_record.get("dispute_id"),
        filename=doc_record["filename"],
        file_size=doc_record["file_size"],
        content_type=doc_record["content_type"],
        doc_type=DocumentType(doc_record["doc_type"]),
        status=ProcessingStatus(doc_record["status"]),
        error_message=doc_record.get("error_message"),
        raw_text=doc_record.get("raw_text"),
        extracted_fields=ExtractedDocumentFields.model_validate(doc_record["extracted_fields"])
        if doc_record.get("extracted_fields") else None,
        created_at=doc_record["created_at"],
        updated_at=doc_record["updated_at"],
    )


@router.get("", response_model=list[DocumentMetadata])
def list_documents(
    dispute_id: str | None = Query(None),
    db: Database = Depends(get_db),
):
    """List documents with optional dispute_id filtering."""
    docs = db.list_documents(dispute_id=dispute_id)
    return [
        DocumentMetadata(
            id=d["id"],
            dispute_id=d.get("dispute_id"),
            filename=d["filename"],
            file_size=d["file_size"],
            content_type=d["content_type"],
            doc_type=DocumentType(d.get("doc_type", "other")),
            status=ProcessingStatus(d.get("status", "PENDING")),
            error_message=d.get("error_message"),
            raw_text=d.get("raw_text"),
            extracted_fields=ExtractedDocumentFields.model_validate(d["extracted_fields"])
            if d.get("extracted_fields") else None,
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )
        for d in docs
    ]


@router.get("/{document_id}", response_model=DocumentMetadata)
def get_document(
    document_id: str,
    db: Database = Depends(get_db),
):
    """Retrieve metadata and extracted structured fields for a document."""
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentMetadata(
        id=doc["id"],
        dispute_id=doc.get("dispute_id"),
        filename=doc["filename"],
        file_size=doc["file_size"],
        content_type=doc["content_type"],
        doc_type=DocumentType(doc.get("doc_type", "other")),
        status=ProcessingStatus(doc.get("status", "PENDING")),
        error_message=doc.get("error_message"),
        raw_text=doc.get("raw_text"),
        extracted_fields=ExtractedDocumentFields.model_validate(doc["extracted_fields"])
        if doc.get("extracted_fields") else None,
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.get("/{document_id}/text")
def get_document_text(
    document_id: str,
    db: Database = Depends(get_db),
):
    """Retrieve raw extracted text from a document."""
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    raw_text = doc.get("raw_text") or ""
    return {
        "document_id": document_id,
        "filename": doc["filename"],
        "status": doc["status"],
        "character_count": len(raw_text),
        "text": raw_text,
    }


@router.get("/{document_id}/preview")
def preview_document(
    document_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
):
    """Stream the document for inline browser preview (PDF, images, text) with path traversal security."""
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    stored_path = validate_safe_path(doc["stored_path"], settings.upload_dir)
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Underlying document file not found on disk")
    return FileResponse(
        path=str(stored_path),
        media_type=doc.get("content_type", "application/octet-stream"),
        filename=doc["filename"],
        content_disposition_type="inline",
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
):
    """Download the raw document file securely with path validation."""
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    stored_path = validate_safe_path(doc["stored_path"], settings.upload_dir)
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Underlying document file not found on disk")
    return FileResponse(
        path=str(stored_path),
        media_type=doc.get("content_type", "application/octet-stream"),
        filename=doc["filename"],
        content_disposition_type="attachment",
    )


@router.post("/{document_id}/associate", response_model=DocumentMetadata)
def associate_document(
    document_id: str,
    body: AssociateRequest,
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
):
    """Associate an existing document with a dispute ID."""
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    clean_dispute_id = body.dispute_id.strip()
    updated = db.update_document(document_id, dispute_id=clean_dispute_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update document association")

    db.log_audit(
        dispute_id=clean_dispute_id,
        action="EVIDENCE_ASSOCIATED",
        actor=merchant_id,
        details={"document_id": document_id, "filename": doc["filename"]},
    )

    return DocumentMetadata(
        id=updated["id"],
        dispute_id=updated.get("dispute_id"),
        filename=updated["filename"],
        file_size=updated["file_size"],
        content_type=updated["content_type"],
        doc_type=DocumentType(updated.get("doc_type", "other")),
        status=ProcessingStatus(updated.get("status", "PENDING")),
        error_message=updated.get("error_message"),
        raw_text=updated.get("raw_text"),
        extracted_fields=ExtractedDocumentFields.model_validate(updated["extracted_fields"])
        if updated.get("extracted_fields") else None,
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    merchant_id: str = Depends(get_current_merchant_id),
):
    """Delete a document record and its underlying stored file with path validation."""
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    stored_path = validate_safe_path(doc["stored_path"], settings.upload_dir)
    if stored_path.exists():
        try:
            stored_path.unlink()
        except Exception as exc:
            logger.warning("Could not delete file %s: %s", stored_path, exc)

    db.delete_document(document_id)
    db.log_audit(
        dispute_id=doc.get("dispute_id") or "UNASSOCIATED",
        action="EVIDENCE_DELETED",
        actor=merchant_id,
        details={"document_id": document_id, "filename": doc["filename"]},
    )
    return {"message": "Document deleted successfully", "document_id": document_id}
