# ResolveIQ Zapier Integration Guide

ResolveIQ delivers production-grade, event-driven webhooks directly to [Zapier Catch Hooks](https://zapier.com/apps/webhook/integrations). Merchants can easily configure their webhook endpoint, toggle individual events, test connectivity, and trigger automated downstream workflows in Slack, Gmail, Microsoft Teams, Asana, Jira, or CRM platforms.

---

## 1. Supported Automation Events

ResolveIQ provides 6 dedicated business lifecycle events:

| Event Identifier | Display Name | Trigger Condition |
| :--- | :--- | :--- |
| `dispute.created` | Dispute Ingested | Ingested into ResolveIQ from PayPal API or demo database. |
| `dispute.high_priority` | High Priority Claim | Dispute amount exceeds \$500.00 or flagged as urgent. |
| `evidence.missing` | Evidence Missing | Completeness score is deficient or mandatory claims lack proof. |
| `evidence.ready_for_review` | Ready for Review | Evidence matrix completeness score meets approval threshold. |
| `dispute.deadline_approaching` | Deadline Approaching | PayPal adjudication cutoff is within 48 hours. |
| `dispute.submitted` | Dispute Submitted | Approved rebuttal package successfully submitted to PayPal API. |

---

## 2. Security & Data Protection Guarantees

1. **Bearer Secret Protection**:
   - Webhook URLs containing unique tokens (e.g., `https://hooks.zapier.com/hooks/catch/123456/abcdef/`) are masked in all logs, UI displays, and API responses (`https://hooks.zapier.com/hooks/catch/.../ab****`).
   - Webhook URLs are stored securely in SQLite backend configuration and never committed or leaked to browser bundles.
2. **Customer Privacy & Data Sanitization**:
   - Raw document binary payloads (`pdf_bytes`, `file_content`, `binary_data`) and file paths are strictly stripped.
   - Credentials, access tokens, client secrets, card numbers, and CVVs are automatically scrubbed by `sanitize_payload`.
   - Customer email addresses are masked (e.g., `al***@example.com`).
3. **Verification Integrity**:
   - ResolveIQ **never** claims Zapier is connected until a real HTTP POST request to the Catch Hook URL returns a `2xx` status code.
   - Modifying or clearing the webhook URL immediately resets the verification badge to unverified.
4. **Advisory Separation**:
   - Webhooks are strictly **one-way informational notifications**.
   - No external Zap can ever automatically approve or submit a dispute rebuttal to PayPal. Merchant review and explicit approval remain mandatory.

---

## 3. Delivery Reliability & Duplicate Prevention

- **Configurable Timeouts & Retries**:
  - Default timeout: 8.0 seconds (customizable from 2.0s to 30.0s).
  - Transient error retries: Exponential backoff ($1.0s, 2.0s, \dots$) on HTTP `5xx` server errors and network timeouts.
  - Client error fail-fast: HTTP `4xx` responses (e.g., 400 Bad Request, 404 Inactive Zap) fail immediately without retrying.
- **In-Memory Deduplication Window**:
  - Duplicate events for the same `(event_type, dispute_id)` within 30 seconds are suppressed to prevent spamming merchant notification channels.
- **Persistent Delivery History**:
  - Every attempt, status code, latency (ms), timestamp, error message, and sanitized JSON payload is recorded in the SQLite `webhook_deliveries` table.

---

## 4. Webhook Payload Contract

All events follow this standard schema:

```json
{
  "event_id": "c1f7a294-81d3-4a11-8a9d-b4f0e7d56e92",
  "event": "evidence.missing",
  "occurred_at": "2026-11-07T12:00:00.000000+00:00",
  "version": "1",
  "test_mode": false,
  "data": {
    "dispute_id": "PP-D-84920",
    "dispute_amount": 149.99,
    "currency": "USD",
    "dispute_reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    "missing_requirements": [
      "Proof of delivery with carrier tracking",
      "Signed delivery confirmation"
    ],
    "response_deadline": "2026-11-12T23:59:59Z"
  }
}
```

---

## 5. Step-by-Step Guide: Setting Up a Zap

Follow these steps to connect ResolveIQ to Slack, Email, or task management systems:

### Step 1: Create a Catch Hook in Zapier
1. Log in to [Zapier](https://zapier.com) and click **Create Zap**.
2. For the **Trigger**, search for and select **Webhooks by Zapier**.
3. In the **Event** dropdown, select **Catch Hook** and click **Continue**.
4. (Optional) Leave *Pick off a Child Key* blank and click **Continue**.
5. Zapier will display your unique webhook URL:
   `https://hooks.zapier.com/hooks/catch/XXXXXX/YYYYYY/`
6. Click **Copy** to copy the webhook URL.

### Step 2: Configure ResolveIQ
1. In ResolveIQ, navigate to the **Automation** tab.
2. Paste your Catch Hook URL into the **Zapier Catch Hook URL** field.
3. Select which of the 6 events you want to subscribe to (e.g., *High Priority Claim*, *Evidence Missing*, *Deadline Approaching*).
4. Click **Save Configuration**.
5. Click **Send Test Webhook**. ResolveIQ sends an authentic test ping payload (`test_mode: true`) to Zapier.
6. Once the test returns HTTP 200, the status indicator will update to **Zapier Connected & Verified** with a green badge.

### Step 3: Test and Map in Zapier
1. Return to your Zapier window and click **Test trigger**.
2. Zapier will display the test payload from ResolveIQ containing `event: "dispute.created"`, `event_id`, and sample metadata.
3. Click **Continue with selected record**.

### Step 4: Configure Downstream Action
1. For the **Action**, choose your team's workflow tool:
   - **Slack**: Send Channel Message (e.g., `#disputes-alerts`: `🚨 Urgent Dispute {{data.dispute_id}} for {{data.dispute_amount}} {{data.currency}} requires attention!`).
   - **Gmail / Outlook**: Send follow-up task or email notification to finance team.
   - **Asana / Jira**: Create ticket with deadline `{{data.response_deadline}}`.
2. Map the fields from the ResolveIQ webhook payload into your action message.
3. Test the action, name your Zap, and click **Publish**.

---

## 6. API Reference

- `GET /api/automation/settings`: View current masked URL, active events, and verification state.
- `PUT /api/automation/settings`: Update webhook endpoint, toggles, timeout, and retry limit.
- `POST /api/automation/test`: Dispatch test ping to Catch Hook; updates verification status on HTTP 200.
- `GET /api/automation/deliveries?limit=50`: Retrieve chronologically ordered delivery audit records.
- `POST /api/automation/emit`: Trigger an event notification programmatically for an active dispute.
