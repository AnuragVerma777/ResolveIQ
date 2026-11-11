import streamlit as st

from backend.integrations.zapier import AutomationEvent

st.set_page_config(page_title="Automation Settings | ResolveIQ", layout="wide")
st.title("Automation Settings")
st.write("Choose which event notifications ResolveIQ may send to the configured backend Zapier hook.")
labels = {
    AutomationEvent.HIGH_PRIORITY: "High priority dispute",
    AutomationEvent.EVIDENCE_MISSING: "Evidence missing",
    AutomationEvent.EVIDENCE_READY_FOR_REVIEW: "Evidence ready for review",
    AutomationEvent.DEADLINE_APPROACHING: "Deadline approaching (3 days or less)",
    AutomationEvent.SUBMITTED: "Dispute submitted (notification only)",
}
current = st.session_state.get("resolveiq_enabled_events", set(AutomationEvent))
selected = set()
for event, label in labels.items():
    if st.checkbox(label, value=event in current, key=f"zap_{event.value}"):
        selected.add(event)
st.session_state["resolveiq_enabled_events"] = selected
st.caption("Merchant preferences apply for this browser session. Configure ZAPIER_WEBHOOK_URL on the backend; the secret URL is not displayed here.")
st.info("Zapier can notify or organize work. It cannot submit dispute responses. Submission always requires a separate merchant action.")
