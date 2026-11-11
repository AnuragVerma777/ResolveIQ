/**
 * ResolveIQ API Client
 */

const API_BASE = (import.meta.env?.VITE_API_BASE || '/api').replace(/\/+$/, '');

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function uploadDocument(file, disputeId = null, docType = 'other') {
  const formData = new FormData();
  formData.append('file', file);
  if (disputeId) formData.append('dispute_id', disputeId);
  formData.append('doc_type', docType);

  const res = await fetch(`${API_BASE}/documents/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Upload failed with status ${res.status}`);
  }
  return res.json();
}

export async function listDocuments(disputeId = null) {
  const url = disputeId
    ? `${API_BASE}/documents?dispute_id=${encodeURIComponent(disputeId)}`
    : `${API_BASE}/documents`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to list documents');
  return res.json();
}

export async function getDocument(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}`);
  if (!res.ok) throw new Error('Failed to fetch document');
  return res.json();
}

export async function getDocumentText(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/text`);
  if (!res.ok) throw new Error('Failed to fetch document text');
  return res.json();
}

export async function deleteDocument(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete document');
  return res.json();
}

export async function associateDocument(documentId, disputeId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/associate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dispute_id: disputeId }),
  });
  if (!res.ok) throw new Error('Failed to associate document');
  return res.json();
}

export async function classifyDispute(payload) {
  const res = await fetch(`${API_BASE}/disputes/classify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Classification failed (${res.status})`);
  }
  return res.json();
}

export async function getDispute(disputeId) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}`);
  if (!res.ok) throw new Error('Failed to fetch dispute details');
  return res.json();
}

export async function listDisputes() {
  const res = await fetch(`${API_BASE}/disputes`);
  if (!res.ok) throw new Error('Failed to list disputes');
  return res.json();
}


export async function fetchEvidenceMatrix(disputeId, payload = null) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/evidence-matrix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to generate evidence matrix (${res.status})`);
  }
  return res.json();
}

export async function getEvidenceMatrix(disputeId) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/evidence-matrix`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch evidence matrix (${res.status})`);
  }
  return res.json();
}


// =====================================================================
// Resolution Studio API Client Methods
// =====================================================================

export async function generateResolutionResponse(disputeId, instructions = '') {
  const url = `${API_BASE}/disputes/${encodeURIComponent(disputeId)}/resolution/generate?merchant_instructions=${encodeURIComponent(instructions)}`;
  const res = await fetch(url, { method: 'POST' });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Response generation failed (${res.status})`);
  }
  return res.json();
}

export async function getResolutionDetails(disputeId) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/resolution`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch resolution details (${res.status})`);
  }
  return res.json();
}

export async function editResolutionResponse(disputeId, responseId, letterText, notes = '') {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/resolution/${encodeURIComponent(responseId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ official_response_letter: letterText, edit_notes: notes }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to save response edit (${res.status})`);
  }
  return res.json();
}

export async function approveResolutionResponse(disputeId, responseId, approverName) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/resolution/${encodeURIComponent(responseId)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approver_name: approverName, confirmed: true }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Approval failed (${res.status})`);
  }
  return res.json();
}

export async function submitResolutionResponse(disputeId, responseId) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/resolution/${encodeURIComponent(responseId)}/submit`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Submission failed (${res.status})`);
  }
  return res.json();
}

export async function getAuditTrail(disputeId) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/audit-trail`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch audit trail (${res.status})`);
  }
  return res.json();
}

// =====================================================================
// PayPal Sandbox & Adjudication Client Methods
// =====================================================================

export async function fetchPayPalStatus() {
  const res = await fetch(`${API_BASE}/paypal/status`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `PayPal status check failed (${res.status})`);
  }
  return res.json();
}

export async function fetchPayPalDisputes(disputeState = null) {
  const url = disputeState
    ? `${API_BASE}/paypal/disputes?dispute_state=${encodeURIComponent(disputeState)}`
    : `${API_BASE}/paypal/disputes`;
  const res = await fetch(url);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch PayPal disputes (${res.status})`);
  }
  return res.json();
}

export async function fetchPayPalDisputeDetails(disputeId) {
  const res = await fetch(`${API_BASE}/paypal/disputes/${encodeURIComponent(disputeId)}`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch PayPal dispute details (${res.status})`);
  }
  return res.json();
}

export async function fetchPayPalTransactions(startDate = null, endDate = null) {
  const params = new URLSearchParams();
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);
  const query = params.toString() ? `?${params.toString()}` : '';

  const res = await fetch(`${API_BASE}/paypal/transactions${query}`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch transactions (${res.status})`);
  }
  return res.json();
}

export async function submitPayPalEvidence(disputeId, payload) {
  const res = await fetch(`${API_BASE}/paypal/disputes/${encodeURIComponent(disputeId)}/provide-evidence`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Evidence submission failed (${res.status})`);
  }
  return res.json();
}

export async function importPayPalDispute(disputeId) {
  const res = await fetch(`${API_BASE}/paypal/disputes/${encodeURIComponent(disputeId)}/import`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Dispute import failed (${res.status})`);
  }
  return res.json();
}

export async function fetchPreflightCheck(disputeId) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/preflight-check`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Preflight check failed (${res.status})`);
  }
  return res.json();
}

// =====================================================================
// Zapier Automation & Webhook Client Methods
// =====================================================================

export async function fetchAutomationSettings() {
  const res = await fetch(`${API_BASE}/automation/settings`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch automation settings (${res.status})`);
  }
  return res.json();
}

export async function updateAutomationSettings(payload) {
  const res = await fetch(`${API_BASE}/automation/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update automation settings (${res.status})`);
  }
  return res.json();
}

export async function testZapierWebhook(webhookUrl = null) {
  const res = await fetch(`${API_BASE}/automation/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(webhookUrl ? { webhook_url: webhookUrl } : {}),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Test webhook failed (${res.status})`);
  }
  return res.json();
}

export async function fetchWebhookDeliveries(limit = 50) {
  const res = await fetch(`${API_BASE}/automation/deliveries?limit=${limit}`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to fetch delivery history (${res.status})`);
  }
  return res.json();
}

export async function emitAutomationEvent(event, disputeId, extraData = {}) {
  const res = await fetch(`${API_BASE}/automation/emit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event, dispute_id: disputeId, extra_data: extraData }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to emit automation event (${res.status})`);
  }
  return res.json();
}

export function getDocumentPreviewUrl(documentId) {
  return `${API_BASE}/documents/${documentId}/preview`;
}

export function getDocumentDownloadUrl(documentId) {
  return `${API_BASE}/documents/${documentId}/download`;
}

export async function seedSampleEvidence(disputeId) {
  const res = await fetch(`${API_BASE}/disputes/${encodeURIComponent(disputeId)}/seed-sample-evidence`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to seed sample evidence (${res.status})`);
  }
  return res.json();
}

export { API_BASE };



