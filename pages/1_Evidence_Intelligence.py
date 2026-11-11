import hashlib
import os
from datetime import date
import streamlit as st

from backend.ai.classifier import DisputeClassifier
from backend.ai.documents import extract_text
from backend.ai.engine import GeminiGenerator, InvestigationEngine
from backend.ai.extractor import extract_structured_fields
from backend.integrations.zapier import AutomationEvent, service_from_environment

st.set_page_config(page_title="Evidence Intelligence | ResolveIQ", layout="wide")
st.title("Evidence Intelligence & Dispute Investigation")
st.write("Upload merchant records (PDF, DOCX, images, text). AI findings cite source excerpts and remain subject to human review.")

col1, col2 = st.columns(2)
with col1:
    dispute_id = st.text_input("PayPal dispute ID", value="PP-D-88902")
    dispute_reason = st.text_input("Dispute reason", value="MERCHANDISE_OR_SERVICE_NOT_RECEIVED", placeholder="As reported by PayPal")
    claim_text = st.text_area("Claim details", value="I never received my package. It has been two weeks and nothing arrived at my doorstep.", placeholder="Paste the claim text or summary from PayPal")

with col2:
    high_priority = st.checkbox("Mark this dispute high priority")
    deadline = st.date_input("Response deadline (optional)", value=None)
    merchant_context = st.text_area("Merchant internal context", value="Package was shipped via FedEx with tracking #940011189922. Scanned delivered on May 3.")

uploads = st.file_uploader(
    "Merchant records (PDF invoices, DOCX, shipping receipts, tracking, emails, screenshots)",
    accept_multiple_files=True,
    type=["pdf", "docx", "txt", "csv", "md", "png", "jpg", "jpeg", "webp"],
)

if st.button("Analyze evidence & Classify", type="primary", disabled=not (dispute_id and (uploads or claim_text))):
    api_key = os.getenv("GEMINI_API_KEY")
    with st.spinner("Reviewing supplied records and running intelligence pipeline…"):
        docs = []
        structured_docs = []
        if uploads:
            for file in uploads:
                data_bytes = file.getvalue()
                text = extract_text(file.name, data_bytes, gemini_api_key=api_key or None)
                evidence_id = hashlib.sha256((file.name + text).encode()).hexdigest()[:12]
                fields = extract_structured_fields(text, file.name, gemini_api_key=api_key or None)
                docs.append({
                    "evidence_id": evidence_id,
                    "name": file.name,
                    "text": text,
                    "extracted_fields": fields.model_dump(),
                })
        else:
            # Synthetic document from merchant context if no files uploaded
            dummy_text = f"Merchant record: {merchant_context}"
            docs.append({
                "evidence_id": "ctx-1",
                "name": "merchant_notes.txt",
                "text": dummy_text,
                "extracted_fields": {},
            })

        # Run Investigation Engine & Dispute Classifier
        if api_key:
            generator = GeminiGenerator(api_key, os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
        else:
            class OfflineGenerator:
                def generate(self, prompt, schema):
                    raise RuntimeError("Offline mode: GEMINI_API_KEY not configured")
            generator = OfflineGenerator()

        classifier = DisputeClassifier(generator)
        dispute_payload = {
            "dispute_id": dispute_id,
            "dispute_reason": dispute_reason,
            "customer_complaint": claim_text,
            "merchant_context": merchant_context,
        }
        classification = classifier.classify(dispute_payload, docs)
        st.session_state["resolveiq_classification"] = classification.model_dump()

        # Run Day 1 engine if docs have matching excerpts
        try:
            day1_engine = InvestigationEngine(generator)
            inv_result = day1_engine.investigate({"dispute_id": dispute_id, "reason": dispute_reason, "claim": claim_text}, docs)
            st.session_state["resolveiq_investigation"] = inv_result.model_dump()
            st.session_state["resolveiq_engine"] = day1_engine
        except Exception:
            pass

        # Zapier notification
        enabled = st.session_state.get("resolveiq_enabled_events", set())
        hooks = service_from_environment(enabled_events=enabled)
        event_data = {"dispute_id": dispute_id, "category": classification.dispute_category.value}
        if classification.missing_information:
            delivery = hooks.emit(AutomationEvent.EVIDENCE_MISSING, {**event_data, "missing_information": classification.missing_information})
            st.session_state["resolveiq_last_webhook"] = delivery.model_dump()
        else:
            delivery = hooks.emit(AutomationEvent.EVIDENCE_READY_FOR_REVIEW, event_data)
            st.session_state["resolveiq_last_webhook"] = delivery.model_dump()
        if high_priority:
            hooks.emit(AutomationEvent.HIGH_PRIORITY, event_data)
        if deadline and (deadline - date.today()).days <= 3:
            hooks.emit(AutomationEvent.DEADLINE_APPROACHING, {**event_data, "deadline": deadline.isoformat()})
        hooks.close()

# Visual Results Presentation
classification_data = st.session_state.get("resolveiq_classification")
last_webhook = st.session_state.get("resolveiq_last_webhook")

if last_webhook:
    if last_webhook.get("delivered"):
        st.toast(f"Zapier event delivered (HTTP {last_webhook['status_code']})")
    else:
        st.caption(f"Zapier event not delivered: {last_webhook.get('error')}")

if classification_data:
    st.divider()
    st.header("Dispute Adjudication & Intelligence")

    # Metric Row
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Original PayPal Reason", classification_data["original_paypal_reason"])
    with m2:
        st.metric("AI Classified Category", classification_data["dispute_category"].replace("_", " ").title())
    with m3:
        conf = classification_data["confidence"]
        st.metric(f"Confidence ({conf['level']})", f"{conf['score']:.0%}")

    st.info(f"**Classification Rationale:** {classification_data['explanation']}")
    st.caption(f"ℹ️ {classification_data['confidence']['explanation']} — *{classification_data['disclaimer']}*")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Key Facts Extracted")
        for fact in classification_data.get("key_facts", []):
            st.markdown(f"- {fact}")

        if classification_data.get("potential_contradictions"):
            st.warning("**Potential Contradictions:**\n" + "\n".join(f"- {c}" for c in classification_data["potential_contradictions"]))

    with c2:
        st.subheader("Missing Information")
        if classification_data.get("missing_information"):
            for m in classification_data["missing_information"]:
                st.markdown(f"- ❓ {m}")
        else:
            st.success("No critical information missing.")

        st.subheader("Recommended Next Actions")
        for act in classification_data.get("recommended_next_actions", []):
            st.markdown(f"- ➡️ **{act}**")

    if classification_data.get("relevant_evidence"):
        st.subheader("Relevant Evidence Citations")
        for ev in classification_data["relevant_evidence"]:
            with st.expander(f"Evidence: {ev['document_name']} ({ev['evidence_type']})"):
                st.markdown(f"> *“{ev['source_excerpt']}”*")
                if ev.get("relevance_explanation"):
                    st.caption(f"Relevance: {ev['relevance_explanation']}")
