import pytest

from backend.ai.engine import InvestigationEngine
from backend.ai.schemas import (
    DisputeInvestigation, DisputeReason, DraftDisputeResponse, EvidenceFact,
    ResponseClaim,
)


class FakeGenerator:
    def __init__(self, result):
        self.result = result

    def generate(self, prompt, schema):
        return schema.model_validate(self.result)


def investigation(**updates):
    data = dict(reason=DisputeReason.ITEM_NOT_RECEIVED, reason_confidence=.8,
                reason_basis_evidence_ids=["e1"],
                facts=[dict(evidence_id="e1", fact="Package scan dated May 1", source_document="tracking.txt",
                            source_excerpt="Delivered May 1", confidence=.7)],
                claims=[], contradictions=[], missing_information=[], completeness_score=50,
                score_explanation="One of two requested record types present.")
    data.update(updates)
    return data


def test_rejects_model_invented_excerpt():
    result = investigation(facts=[dict(evidence_id="e1", fact="Delivered", source_document="tracking.txt",
                                      source_excerpt="Delivered May 2", confidence=.9)])
    engine = InvestigationEngine(FakeGenerator(result))
    with pytest.raises(ValueError, match="verbatim"):
        engine.investigate({}, [{"evidence_id": "e1", "name": "tracking.txt", "text": "Delivered May 1"}])


def test_accepts_supported_fact_and_rejects_unknown_claim_ref():
    engine = InvestigationEngine(FakeGenerator(investigation()))
    result = engine.investigate({}, [{"evidence_id": "e1", "name": "tracking.txt", "text": "Delivered May 1"}])
    assert result.facts[0].evidence_id == "e1"
    bad = investigation(claims=[dict(claim="Claim", supporting_evidence_ids=["fake"],
                                     contradicting_evidence_ids=[], missing_information=[], uncertain=False)])
    with pytest.raises(ValueError, match="Unknown claim"):
        InvestigationEngine(FakeGenerator(bad)).investigate({}, [{"evidence_id": "e1", "name": "tracking.txt", "text": "Delivered May 1"}])


def test_response_requires_valid_evidence_reference():
    draft = dict(claims=[dict(text="Item shipped", evidence_ids=["missing"], uncertain=False)],
                 questions_for_merchant=[], merchant_approval_required=True, approved_by_merchant=False)
    engine = InvestigationEngine(FakeGenerator(draft))
    result = DisputeInvestigation.model_validate(investigation())
    with pytest.raises(ValueError, match="unsupported evidence"):
        engine.draft_response(result)


def test_response_cannot_disable_approval():
    with pytest.raises(ValueError, match="mandatory"):
        DraftDisputeResponse(claims=[ResponseClaim(text="Fact", evidence_ids=["e1"])],
                             merchant_approval_required=False)
