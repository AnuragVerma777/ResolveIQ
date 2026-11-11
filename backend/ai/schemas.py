from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator


class DisputeReason(str, Enum):
    UNAUTHORIZED = "unauthorized"
    ITEM_NOT_RECEIVED = "item_not_received"
    NOT_AS_DESCRIBED = "not_as_described"
    CREDIT_NOT_PROCESSED = "credit_not_processed"
    DUPLICATE = "duplicate"
    OTHER = "other"
    UNCERTAIN = "uncertain"


class EvidenceFact(BaseModel):
    evidence_id: str
    fact: str
    source_document: str
    source_excerpt: str
    confidence: float = Field(ge=0, le=1)


class ClaimAssessment(BaseModel):
    claim: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    uncertain: bool = False


class DisputeInvestigation(BaseModel):
    reason: DisputeReason
    reason_confidence: float = Field(ge=0, le=1)
    reason_basis_evidence_ids: list[str] = Field(default_factory=list)
    facts: list[EvidenceFact] = Field(default_factory=list)
    claims: list[ClaimAssessment] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    completeness_score: int = Field(ge=0, le=100)
    score_explanation: str


class ResponseClaim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    uncertain: bool = False


class DraftDisputeResponse(BaseModel):
    claims: list[ResponseClaim] = Field(default_factory=list)
    questions_for_merchant: list[str] = Field(default_factory=list)
    merchant_approval_required: bool = True
    approved_by_merchant: bool = False

    @model_validator(mode="after")
    def enforce_approval_gate(self):
        if not self.merchant_approval_required:
            raise ValueError("Merchant approval is mandatory before submission")
        return self


# =====================================================================
# Document Intelligence Pipeline Schemas
# =====================================================================

class DocumentType(str, Enum):
    INVOICE = "invoice"
    ORDER_CONFIRMATION = "order_confirmation"
    SHIPPING_RECEIPT = "shipping_receipt"
    DELIVERY_CONFIRMATION = "delivery_confirmation"
    TRACKING_DOCUMENT = "tracking_document"
    CUSTOMER_EMAIL = "customer_email"
    REFUND_RECORD = "refund_record"
    SCREENSHOT = "screenshot"
    OTHER = "other"


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExtractedDocumentFields(BaseModel):
    """Structured fields extracted strictly from document text without invention."""
    order_id: str | None = None
    transaction_id: str | None = None
    customer_name: str | None = None
    purchase_date: str | None = None
    product_or_service: str | None = None
    amount: float | None = None
    currency: str | None = None
    tracking_number: str | None = None
    shipment_date: str | None = None
    delivery_date: str | None = None
    refund_status: str | None = None
    source_references: dict[str, str] = Field(
        default_factory=dict,
        description="Maps extracted field name to verbatim supporting text from document",
    )
    unextracted_reasons: list[str] = Field(
        default_factory=list,
        description="Explanations for unavailable or ambiguous fields",
    )


class DocumentMetadata(BaseModel):
    id: str
    dispute_id: str | None = None
    filename: str
    file_size: int
    content_type: str
    doc_type: DocumentType = DocumentType.OTHER
    status: ProcessingStatus = ProcessingStatus.PENDING
    error_message: str | None = None
    raw_text: str | None = None
    extracted_fields: ExtractedDocumentFields | None = None
    created_at: str
    updated_at: str


class DocumentPreviewResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    file_size: int
    doc_type: DocumentType
    status: ProcessingStatus
    raw_text: str | None = None
    extracted_fields: ExtractedDocumentFields | None = None
    preview_url: str


# =====================================================================
# AI Dispute Classification Engine Schemas
# =====================================================================

class DisputeCategory(str, Enum):
    UNAUTHORIZED_TRANSACTION = "unauthorized_transaction"
    ITEM_NOT_RECEIVED = "item_not_received"
    SIGNIFICANTLY_NOT_AS_DESCRIBED = "significantly_not_as_described"
    CREDIT_NOT_PROCESSED = "credit_not_processed"
    DUPLICATE_CHARGE = "duplicate_charge"
    INCORRECT_AMOUNT = "incorrect_amount"
    CANCELED_RECURRING_BILLING = "canceled_recurring_billing"
    OTHER = "other"
    UNCERTAIN = "uncertain"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConfidenceAssessment(BaseModel):
    level: ConfidenceLevel
    score: float = Field(ge=0.0, le=1.0, description="Classification clarity score (0.0 to 1.0). Not win probability.")
    explanation: str = Field(description="Transparent explanation of the confidence level based on facts and data.")


class RelevantEvidence(BaseModel):
    document_id: str | None = None
    document_name: str
    evidence_type: str
    source_excerpt: str
    relevance_explanation: str


class DisputeClassification(BaseModel):
    dispute_id: str
    original_paypal_reason: str
    dispute_category: DisputeCategory
    explanation: str
    key_facts: list[str] = Field(default_factory=list)
    relevant_evidence: list[RelevantEvidence] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    potential_contradictions: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    confidence: ConfidenceAssessment
    disclaimer: str = (
        "Model confidence reflects classification certainty based on available data, not probability of winning a dispute. "
        "No dispute resolution outcome is guaranteed."
    )


class DisputeClassificationRequest(BaseModel):
    dispute_id: str
    dispute_reason: str
    customer_complaint: str = ""
    transaction_details: dict[str, Any] = Field(default_factory=dict)
    order_information: dict[str, Any] = Field(default_factory=dict)
    merchant_context: str = ""
    document_ids: list[str] = Field(default_factory=list)


# =====================================================================
# Evidence Intelligence Engine & Evidence Matrix Schemas
# =====================================================================

class EvidenceStatus(str, Enum):
    SUPPORTED = "Supported"
    PARTIALLY_SUPPORTED = "Partially supported"
    UNSUPPORTED = "Unsupported"
    CONTRADICTORY = "Contradictory"


class StructuredEvidenceRecord(BaseModel):
    """Structured record converted from extracted documents."""
    evidence_id: str
    document_id: str | None = None
    source_document: str
    doc_type: str = "other"
    key_facts: list[str] = Field(default_factory=list)
    verbatim_excerpt: str = ""
    order_id: str | None = None
    transaction_id: str | None = None
    tracking_number: str | None = None
    amount: float | None = None
    currency: str | None = None
    purchase_date: str | None = None
    delivery_date: str | None = None
    shipment_date: str | None = None
    refund_status: str | None = None
    verified: bool = True


class ConflictWarning(BaseModel):
    """Detected conflict in dates, amounts, order IDs, or tracking numbers."""
    conflict_type: str  # "date_mismatch", "amount_mismatch", "order_id_mismatch", "tracking_mismatch"
    field_name: str
    disputed_value: str
    evidence_value: str
    source_reference: str
    explanation: str


class EvidenceMatrixItem(BaseModel):
    """Single claim-to-evidence evaluation row in the Evidence Matrix."""
    claim: str
    claim_type: str = "customer_assertion"
    supporting_evidence: list[str] = Field(default_factory=list)
    source_documents: list[str] = Field(default_factory=list)
    evidence_relevance_explanation: str
    evidence_status: EvidenceStatus
    missing_information: list[str] = Field(default_factory=list)
    contradiction_warnings: list[str] = Field(default_factory=list)
    unsupported_aspects: list[str] = Field(default_factory=list)
    recommended_merchant_action: str | None = None


class CompletenessScoreBreakdown(BaseModel):
    """Transparent, explainable evidence coverage score."""
    overall_score: int = Field(ge=0, le=100)
    claim_coverage_points: int
    core_evidence_points: int
    data_consistency_points: int
    conflict_deductions: int
    explanation: str
    scoring_rubric: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = (
        "Completeness score is based strictly on documented evidence coverage, "
        "not an invented probability of winning. Missing evidence is not proof that an event did not happen."
    )


class EvidenceMatrixReport(BaseModel):
    """Comprehensive evidence intelligence analysis for a PayPal dispute."""
    dispute_id: str
    matrix_items: list[EvidenceMatrixItem]
    evidence_records: list[StructuredEvidenceRecord]
    conflict_warnings: list[ConflictWarning] = Field(default_factory=list)
    unsupported_factual_claims: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    completeness_score: CompletenessScoreBreakdown
    created_at: str


# =====================================================================
# AI Resolution Studio Schemas
# =====================================================================

class FactSectionType(str, Enum):
    VERIFIED_FACT = "verified_fact"
    MERCHANT_STATEMENT = "merchant_statement"
    AI_RECOMMENDATION = "ai_recommendation"
    UNKNOWN_INFORMATION = "unknown_information"


class CategorizedClaim(BaseModel):
    """Individual assertion in dispute response with clear origin provenance."""
    text: str
    section: FactSectionType
    evidence_ids: list[str] = Field(default_factory=list)
    source_documents: list[str] = Field(default_factory=list)
    uncertain: bool = False


class DisputeResponseDraft(BaseModel):
    """Complete, structured dispute response generated from verified evidence only."""
    response_id: str
    dispute_id: str
    version: int = 1
    subject_line: str
    official_response_letter: str
    categorized_claims: list[CategorizedClaim] = Field(default_factory=list)
    verified_facts: list[str] = Field(default_factory=list)
    merchant_statements: list[str] = Field(default_factory=list)
    ai_recommendations: list[str] = Field(default_factory=list)
    unknown_or_missing_info: list[str] = Field(default_factory=list)
    questions_for_merchant: list[str] = Field(default_factory=list)
    missing_evidence_warnings: list[str] = Field(default_factory=list)
    contradiction_warnings: list[str] = Field(default_factory=list)
    merchant_approval_required: bool = True
    approved_by_merchant: bool = False
    approved_by: str | None = None
    approved_at: str | None = None
    submission_status: str = "DRAFT"
    disclaimer: str = (
        "Every factual claim cites verified evidence records. Model does not guarantee "
        "a successful dispute outcome. Submission always requires explicit merchant approval."
    )

    @model_validator(mode="after")
    def enforce_approval_gate(self):
        if not self.merchant_approval_required:
            raise ValueError("Merchant approval is mandatory before dispute submission")
        return self


class ResponseEditRequest(BaseModel):
    official_response_letter: str
    edit_notes: str | None = None


class ApprovalRequest(BaseModel):
    approver_name: str
    confirmed: bool = True


class AuditLogEntry(BaseModel):
    id: str
    dispute_id: str
    action: str
    actor: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
