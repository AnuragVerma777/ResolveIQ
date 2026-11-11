"""Automated tests for ResolveIQ AI dispute classification engine.

Tests different dispute scenarios, constraint checks, and malformed AI responses.
"""
import pytest
from backend.ai.classifier import DisputeClassifier
from backend.ai.schemas import (
    ConfidenceAssessment,
    ConfidenceLevel,
    DisputeCategory,
    DisputeClassification,
    RelevantEvidence,
)


class MockGenerator:
    """Mock generator that returns pre-configured Pydantic responses or raises exceptions."""

    def __init__(self, response_or_exc):
        self.response_or_exc = response_or_exc

    def generate(self, prompt: str, schema: type):
        if isinstance(self.response_or_exc, Exception):
            raise self.response_or_exc
        if isinstance(self.response_or_exc, dict):
            return schema.model_validate(self.response_or_exc)
        return self.response_or_exc


# =====================================================================
# 1. Dispute Scenario Tests
# =====================================================================

def test_scenario_item_not_received_with_delivery_evidence():
    """Customer claims non-receipt, but carrier tracking shows delivered."""
    mock_result = {
        "dispute_id": "PP-D-8801",
        "original_paypal_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "dispute_category": DisputeCategory.ITEM_NOT_RECEIVED.value,
        "explanation": "Buyer reports non-receipt, but tracking documents confirm delivery to shipping address.",
        "key_facts": [
            "Order ORD-99 shipped via FedEx on 2026-04-10.",
            "Carrier tracking 778899 confirms delivered on 2026-04-13.",
        ],
        "relevant_evidence": [
            {
                "document_id": "doc-fedex",
                "document_name": "fedex_tracking.pdf",
                "evidence_type": "carrier_delivery_confirmation",
                "source_excerpt": "Delivered April 13 to front door",
                "relevance_explanation": "Proves physical delivery before dispute was initiated.",
            }
        ],
        "missing_information": ["Signature confirmation for high value item"],
        "potential_contradictions": [
            "Customer claims package was never received, but carrier logs indicate successful delivery."
        ],
        "recommended_next_actions": [
            "Submit carrier tracking number and proof of delivery to PayPal dispute portal.",
        ],
        "confidence": {
            "level": "HIGH",
            "score": 0.92,
            "explanation": "High confidence due to verified carrier tracking documentation.",
        },
    }

    engine = DisputeClassifier(MockGenerator(mock_result))
    docs = [{
        "id": "doc-fedex",
        "name": "fedex_tracking.pdf",
        "text": "FedEx Tracking #778899: Delivered April 13 to front door. Signed by resident.",
    }]

    result = engine.classify(
        {
            "dispute_id": "PP-D-8801",
            "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            "customer_complaint": "Where is my package? I never received anything.",
        },
        docs,
    )

    assert result.dispute_category == DisputeCategory.ITEM_NOT_RECEIVED
    assert result.original_paypal_reason == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    assert len(result.relevant_evidence) == 1
    assert "Delivered April 13" in result.relevant_evidence[0].source_excerpt
    assert result.confidence.level == ConfidenceLevel.HIGH
    assert "disclaimer" in result.model_dump()
    assert "not probability of winning" in result.disclaimer.lower()


def test_scenario_unauthorized_transaction():
    """Buyer claims card was used without permission."""
    mock_result = {
        "dispute_id": "PP-D-4412",
        "original_paypal_reason": "UNAUTHORIZED",
        "dispute_category": DisputeCategory.UNAUTHORIZED_TRANSACTION.value,
        "explanation": "Claim indicates account takeover or unauthorized card use.",
        "key_facts": ["Buyer claims payment was unauthorized."],
        "relevant_evidence": [],
        "missing_information": ["Proof of shipping to PayPal confirmed seller protection address"],
        "potential_contradictions": [],
        "recommended_next_actions": ["Provide seller protection proof and buyer IP address log"],
        "confidence": {
            "level": "HIGH",
            "score": 0.88,
            "explanation": "Reason and complaint are consistent with unauthorized transaction classification.",
        },
    }

    engine = DisputeClassifier(MockGenerator(mock_result))
    result = engine.classify({
        "dispute_id": "PP-D-4412",
        "dispute_reason": "UNAUTHORIZED",
        "customer_complaint": "I did not authorize this charge on my PayPal account.",
    })

    assert result.dispute_category == DisputeCategory.UNAUTHORIZED_TRANSACTION
    assert result.original_paypal_reason == "UNAUTHORIZED"


def test_scenario_significantly_not_as_described():
    """Customer claims received goods were damaged / different."""
    mock_result = {
        "dispute_id": "PP-D-5503",
        "original_paypal_reason": "SIGNIFICANTLY_NOT_AS_DESCRIBED",
        "dispute_category": DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED.value,
        "explanation": "Buyer states the received item was broken on arrival.",
        "key_facts": ["Item arrived with broken glass."],
        "relevant_evidence": [],
        "missing_information": ["Photographs of damaged packaging from buyer"],
        "potential_contradictions": ["Merchant packaging checklist recorded item in mint condition"],
        "recommended_next_actions": ["Request buyer photos and offer return shipping label or replacement"],
        "confidence": {
            "level": "HIGH",
            "score": 0.85,
            "explanation": "Clear claim of merchandise defect or damage.",
        },
    }

    engine = DisputeClassifier(MockGenerator(mock_result))
    result = engine.classify({
        "dispute_id": "PP-D-5503",
        "dispute_reason": "SIGNIFICANTLY_NOT_AS_DESCRIBED",
        "customer_complaint": "The screen arrived cracked and unusable.",
    })

    assert result.dispute_category == DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED
    assert "cracked" in result.key_facts[0] or len(result.recommended_next_actions) > 0


# =====================================================================
# 2. Malformed AI Response and Robust Fallback Tests
# =====================================================================

def test_handles_malformed_ai_json_response():
    """Verify that when AI generator throws an error, engine falls back safely."""
    engine = DisputeClassifier(MockGenerator(RuntimeError("Malformed JSON response from model")))
    result = engine.classify({
        "dispute_id": "PP-D-9999",
        "dispute_reason": "Item Not Received",
        "customer_complaint": "I never got the order!",
    })

    assert isinstance(result, DisputeClassification)
    assert result.dispute_id == "PP-D-9999"
    assert result.original_paypal_reason == "Item Not Received"
    assert result.dispute_category == DisputeCategory.ITEM_NOT_RECEIVED
    assert len(result.missing_information) > 0
    assert len(result.recommended_next_actions) > 0
    assert "not probability of winning" in result.disclaimer.lower()


def test_handles_incomplete_ai_response_without_crashing():
    """Verify handling when AI returns unexpected schema."""
    engine = DisputeClassifier(MockGenerator(ValueError("Validation failed: missing field 'explanation'")))
    result = engine.classify({
        "dispute_id": "PP-D-7777",
        "dispute_reason": "UNAUTHORIZED_PAYMENT",
        "customer_complaint": "Someone hacked my account",
    })

    assert isinstance(result, DisputeClassification)
    assert result.dispute_category == DisputeCategory.UNAUTHORIZED_TRANSACTION
    assert result.confidence.level in {ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM}


def test_confidence_is_never_confused_with_win_probability():
    """Verify that disclaimer explicitly prevents confusing confidence with win probability."""
    engine = DisputeClassifier(MockGenerator(RuntimeError("offline")))
    result = engine.classify({
        "dispute_id": "PP-D-3333",
        "dispute_reason": "DUPLICATE_TRANSACTION",
        "customer_complaint": "I was charged twice.",
    })

    assert "not probability of winning" in result.disclaimer.lower()
    assert "not probability of winning" in result.confidence.explanation.lower() or "completeness" in result.confidence.explanation.lower()


def test_preserves_original_paypal_dispute_reason():
    """Verify that original reason is kept unchanged even if classification changes category."""
    raw_paypal_reason = "PAYPAL_CUSTOM_CODE_12345"
    engine = DisputeClassifier(MockGenerator(RuntimeError("offline")))
    result = engine.classify({
        "dispute_id": "PP-D-1111",
        "dispute_reason": raw_paypal_reason,
        "customer_complaint": "Random dispute message",
    })

    assert result.original_paypal_reason == raw_paypal_reason
