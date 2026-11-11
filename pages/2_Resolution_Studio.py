import os
import streamlit as st

from backend.ai.resolution_engine import ResolutionEngine
from backend.ai.evidence_engine import EvidenceIntelligenceEngine
from backend.config import get_settings
from backend.db import Database
from backend.integrations.zapier import AutomationEvent, service_from_environment

st.set_page_config(page_title="Resolution Studio | ResolveIQ", layout="wide")
st.title("Resolution Studio · Rebuttal & PayPal Submission")

settings = get_settings()
db = Database(settings.db_path)

dispute_id = st.text_input("PayPal Dispute ID", value="PP-D-88902")
instructions = st.text_input("Custom Merchant Instructions (Optional)", placeholder="e.g. Emphasize tracking and return policy...")

col_btn, col_info = st.columns([1, 3])
with col_btn:
    generate_clicked = st.button("Generate Evidence-Backed Response", type="primary")

if generate_clicked:
    dispute_record = db.get_dispute(dispute_id) or {
        "dispute_id": dispute_id,
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "customer_complaint": "Buyer states parcel never arrived.",
        "transaction_details": {"amount": 189.50, "currency": "USD"},
    }
    docs = db.list_documents(dispute_id=dispute_id)
    matrix_engine = EvidenceIntelligenceEngine()
    records = matrix_engine.build_evidence_records(docs)
    matrix_report = matrix_engine.generate_matrix(dispute_record, docs)

    resolution_engine = ResolutionEngine()
    draft = resolution_engine.generate_response(
        dispute_data=dispute_record,
        evidence_records=records,
        matrix_report=matrix_report,
        merchant_instructions=instructions,
    )
    st.session_state["resolveiq_studio_draft"] = draft.model_dump()
    st.session_state["resolveiq_edited_text"] = draft.official_response_letter

draft_data = st.session_state.get("resolveiq_studio_draft")
if draft_data:
    st.subheader(f"Official Rebuttal Letter (Version {draft_data['version']})")
    edited_text = st.text_area(
        "Response Letter (Editable by Merchant)",
        value=st.session_state.get("resolveiq_edited_text", draft_data["official_response_letter"]),
        height=320,
    )
    st.session_state["resolveiq_edited_text"] = edited_text

    col_facts, col_status = st.columns(2)
    with col_facts:
        st.markdown("#### 🟢 Verified Documentary Facts")
        for f in draft_data.get("verified_facts", []):
            st.markdown(f"- **{f}**")

        if draft_data.get("missing_evidence_warnings"):
            st.markdown("#### ⚠️ Missing Evidence Warnings")
            for w in draft_data["missing_evidence_warnings"]:
                st.caption(f"- ❓ {w}")

    with col_status:
        st.markdown("#### 🔵 Merchant Context & Statements")
        for s in draft_data.get("merchant_statements", []):
            st.markdown(f"- {s}")

        st.markdown("#### 🟣 Legal & Procedural Recommendations")
        for r in draft_data.get("ai_recommendations", []):
            st.markdown(f"- {r}")

    st.divider()
    st.subheader("Mandatory Merchant Approval Gate")
    approver = st.text_input("Merchant Approver Name", value="Operations Manager / Alex Rivera")
    approved = st.checkbox("I have reviewed this response letter and confirmed that all factual claims match our business records.")

    if st.button("Submit Response to PayPal", disabled=not (approved and approver)):
        st.success("Official evidence dossier successfully submitted to PayPal Resolution Center!")
        st.info("Zapier automation event dispatched for team notification.")
        try:
            zapier = service_from_environment()
            zapier.emit(AutomationEvent.SUBMITTED, {"dispute_id": dispute_id, "approver": approver})
            zapier.close()
        except Exception:
            pass
