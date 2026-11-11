import React, { useState, useEffect } from 'react';
import {
  FileText,
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Send,
  Edit3,
  Save,
  Lock,
  History,
  Check,
  Info,
  ExternalLink,
  RefreshCw,
  Eye,
  UserCheck,
  Clock,
  Layers,
  Zap,
} from 'lucide-react';
import {
  generateResolutionResponse,
  getResolutionDetails,
  editResolutionResponse,
  approveResolutionResponse,
  submitResolutionResponse,
  getAuditTrail,
  listDocuments,
} from '../api';
import { useToast } from '../context/ToastContext';
import DocumentDrawer from './DocumentDrawer';

export default function ResolutionStudio({ activeDisputeId = null }) {
  const { toast, confirmAction } = useToast();
  const [disputeId, setDisputeId] = useState(activeDisputeId || 'PP-D-88902');
  const [merchantInstructions, setMerchantInstructions] = useState('');
  const [draft, setDraft] = useState(null);
  const [editedLetter, setEditedLetter] = useState('');
  const [approverName, setApproverName] = useState('Compliance Lead / Operations Manager');
  const [approvalConfirmed, setApprovalConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [submissionResult, setSubmissionResult] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [versions, setVersions] = useState([]);
  const [activeProvenanceTab, setActiveProvenanceTab] = useState('VERIFIED');

  useEffect(() => {
    if (activeDisputeId && activeDisputeId !== disputeId) {
      setDisputeId(activeDisputeId);
    }
  }, [activeDisputeId]);

  // Load existing resolution details on disputeId change
  const loadResolution = async () => {
    try {
      const data = await getResolutionDetails(disputeId);
      if (data.latest_response) {
        const payload = data.latest_response.structured_payload || {};
        setDraft(payload);
        setEditedLetter(payload.official_response_letter || data.latest_response.response_letter || '');
      }
      setVersions(data.versions || []);
      const [logs, docs] = await Promise.all([
        getAuditTrail(disputeId).catch(() => []),
        listDocuments(disputeId).catch(() => []),
      ]);
      setAuditLogs(logs);
      setDocuments(docs);
    } catch (err) {
      console.error('Error loading resolution data', err);
    }
  };

  useEffect(() => {
    if (disputeId) {
      loadResolution();
    }
  }, [disputeId]);

  const handleInspectCitation = (evidenceRef) => {
    if (!evidenceRef) return;
    const refLower = String(evidenceRef).toLowerCase();
    const match = documents.find((d) => {
      const fname = (d.filename || '').toLowerCase();
      const dtype = (d.doc_type || '').toLowerCase();
      return fname.includes(refLower) || refLower.includes(fname) || dtype.includes(refLower) || refLower.includes(dtype);
    });

    if (match) {
      setSelectedDoc(match);
    } else if (documents.length > 0) {
      setSelectedDoc(documents[0]);
    } else {
      toast.info(`Citation references: "${evidenceRef}". Attach documentary files to inspect full records in viewer.`, 'Citation Reference');
    }
  };

  const handleGenerate = async () => {
    setLoading(true);
    setSubmissionResult(null);
    try {
      const res = await generateResolutionResponse(disputeId, merchantInstructions);
      setDraft(res);
      setEditedLetter(res.official_response_letter);
      await loadResolution();
      toast.success('Generated evidence-backed response draft.', 'Rebuttal Ready');
    } catch (err) {
      toast.error(`Generation failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!draft) return;
    const executeSave = async () => {
      setSavingEdit(true);
      try {
        const updated = await editResolutionResponse(
          disputeId,
          draft.response_id,
          editedLetter,
          'Merchant edited response text'
        );
        setDraft(updated);
        setEditedLetter(updated.official_response_letter);
        setApprovalConfirmed(false);
        await loadResolution();
        toast.info('Response updated and new version saved. Approval has been reset to require re-approval.', 'New Version Saved');
      } catch (err) {
        toast.error(`Edit save failed: ${err.message}`);
      } finally {
        setSavingEdit(false);
      }
    };

    if (isApproved) {
      confirmAction({
        title: 'Revise Approved Response?',
        message: `Saving edits will generate version v${draft.version + 1} and reset current merchant approval. Do you wish to continue?`,
        confirmText: 'Save New Version',
        variant: 'warning',
        onConfirm: executeSave,
      });
    } else {
      executeSave();
    }
  };

  const handleApprove = async () => {
    if (!draft) return;
    if (!approvalConfirmed || !approverName.trim()) {
      toast.warning('Please check the confirmation box and enter your name to approve.');
      return;
    }
    setLoading(true);
    try {
      const approved = await approveResolutionResponse(disputeId, draft.response_id, approverName);
      setDraft(approved);
      await loadResolution();
      toast.success(`Response certified and approved by ${approverName}.`, 'Certified');
    } catch (err) {
      toast.error(`Approval failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!draft) return;
    if (!draft.approved_by_merchant) {
      toast.warning('Merchant approval is mandatory before dispute submission.');
      return;
    }

    const executeSubmit = async () => {
      setSubmitting(true);
      try {
        const res = await submitResolutionResponse(disputeId, draft.response_id);
        setSubmissionResult(res);
        await loadResolution();
        toast.success(
          draft?.submission_debug_id
            ? 'Rebuttal transmitted to PayPal API. Debug receipt captured.'
            : 'Submitted successfully to PayPal Resolution Center.',
          'Submitted'
        );
      } catch (err) {
        toast.error(`Submission failed: ${err.message}`);
      } finally {
        setSubmitting(false);
      }
    };

    confirmAction({
      title: 'Submit Approved Response to PayPal?',
      message: `Transmit merchant-certified rebuttal and harvested carrier records for dispute ${disputeId} to PayPal?`,
      confirmText: 'Confirm PayPal Submission',
      variant: 'primary',
      onConfirm: executeSubmit,
    });
  };

  const isApproved = draft?.approved_by_merchant;
  const isSubmitted = draft?.submission_status === 'SUBMITTED' || submissionResult?.status === 'SUBMITTED';

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-16">
      {/* Top Banner: Workflow Header */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-950/80 border border-emerald-800/60 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-2">
              <ShieldCheck className="w-3.5 h-3.5" />
              AI Resolution Studio · Adjudication Defense
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Official Dispute Response & Evidence Submission
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Generates rigorous, professional dispute rebuttal letters grounded strictly in verified evidence records.
              Requires explicit merchant approval prior to submission.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-mono">Dispute:</span>
            <input
              type="text"
              value={disputeId}
              onChange={(e) => setDisputeId(e.target.value)}
              className="px-3 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500 w-40"
            />
            <button
              onClick={loadResolution}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Workflow Progression Stepper */}
        <div className="mt-6 pt-5 border-t border-slate-800 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 text-center text-[11px] font-mono">
          <div className="p-2 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-400">
            <span className="block font-bold">1. Ingest</span>
            <span className="text-[10px] text-slate-400">PayPal Dispute</span>
          </div>
          <div className="p-2 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-400">
            <span className="block font-bold">2. Classify</span>
            <span className="text-[10px] text-slate-400">AI Category</span>
          </div>
          <div className="p-2 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-400">
            <span className="block font-bold">3. Evidence</span>
            <span className="text-[10px] text-slate-400">PyMuPDF / OCR</span>
          </div>
          <div className="p-2 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-400">
            <span className="block font-bold">4. Matrix</span>
            <span className="text-[10px] text-slate-400">Match Claims</span>
          </div>
          <div className={`p-2 rounded-lg border ${draft ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-400' : 'bg-slate-950/60 border-slate-800 text-slate-400'}`}>
            <span className="block font-bold">5. Rebuttal</span>
            <span className="text-[10px] text-slate-400">Grounded Draft</span>
          </div>
          <div className={`p-2 rounded-lg border ${isApproved ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-400' : 'bg-amber-950/40 border-amber-800/60 text-amber-400'}`}>
            <span className="block font-bold">6. Approval</span>
            <span className="text-[10px] text-slate-400">{isApproved ? 'Approved' : 'Pending Gate'}</span>
          </div>
          <div className={`p-2 rounded-lg border ${isSubmitted ? 'bg-blue-950/40 border-blue-800/60 text-sky-400' : 'bg-slate-950/60 border-slate-800 text-slate-400'}`}>
            <span className="block font-bold">7. Submit</span>
            <span className="text-[10px] text-slate-400">{isSubmitted ? 'Submitted' : 'PayPal Ready'}</span>
          </div>
        </div>
      </div>

      {/* Main Studio Area */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Response Letter Editor & Controls */}
        <div className="lg:col-span-7 space-y-6">
          {/* Generation & Instructions Card */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-sky-400" />
                Response Synthesis Controls
              </h3>
              {draft && (
                <span className="text-xs font-mono text-slate-400">
                  Version: <strong className="text-sky-300">v{draft.version}</strong>
                </span>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">
                Merchant Custom Instructions (Optional)
              </label>
              <input
                type="text"
                value={merchantInstructions}
                onChange={(e) => setMerchantInstructions(e.target.value)}
                placeholder="e.g. Reference warehouse packing video and emphasize signature confirmation..."
                className="w-full px-3.5 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-sans"
              />
            </div>

            <button
              onClick={handleGenerate}
              disabled={loading || !disputeId}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-sky-600 via-blue-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 font-semibold text-white text-xs uppercase tracking-wider shadow-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Synthesizing Verified Response…</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>{draft ? 'Regenerate Grounded Response' : 'Generate Evidence-Backed Response'}</span>
                </>
              )}
            </button>
          </div>

          {/* Response Letter Review & Editable Editor */}
          {draft && (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4 animate-in fade-in duration-300">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <Edit3 className="w-4 h-4 text-sky-400" />
                  <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200">
                    Official Dispute Rebuttal Letter
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-slate-500">
                    {editedLetter.length} chars
                  </span>
                  <button
                    onClick={handleSaveEdit}
                    disabled={savingEdit}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-sky-400 border border-slate-700 flex items-center gap-1.5 transition-all"
                  >
                    <Save className="w-3.5 h-3.5" />
                    <span>{savingEdit ? 'Saving…' : 'Save As New Version'}</span>
                  </button>
                </div>
              </div>

              {/* Subject Line */}
              <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-xs font-mono text-slate-300">
                <span className="text-slate-500 uppercase text-[10px] block">Subject:</span>
                <span className="font-semibold text-sky-300">{draft.subject_line}</span>
              </div>

              {/* Editable Textarea */}
              <div>
                <textarea
                  rows={14}
                  value={editedLetter}
                  onChange={(e) => setEditedLetter(e.target.value)}
                  className="w-full p-4 bg-slate-950 border border-slate-800 rounded-xl text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500 leading-relaxed resize-y"
                  placeholder="Official response letter text..."
                />
              </div>

              {/* Disclaimer */}
              <p className="text-[11px] text-slate-500 italic bg-slate-950/40 p-2.5 rounded-lg border border-slate-900">
                ℹ️ {draft.disclaimer}
              </p>
            </div>
          )}
        </div>

        {/* Right Column: Provenance Segregation, Approval Gate & PayPal Submission */}
        <div className="lg:col-span-5 space-y-6">
          {/* Provenance Segregation Panel */}
          {draft && (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
              <div className="border-b border-slate-800 pb-3">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-emerald-400" />
                  Evidence Provenance & Fact Audit
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Every factual assertion is segregated by source origin.
                </p>
              </div>

              {/* Provenance Tab Switcher */}
              <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800 text-[11px] font-medium">
                <button
                  onClick={() => setActiveProvenanceTab('VERIFIED')}
                  className={`px-2.5 py-1 rounded-lg transition-all ${
                    activeProvenanceTab === 'VERIFIED' ? 'bg-emerald-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Verified Facts ({draft.verified_facts.length})
                </button>
                <button
                  onClick={() => setActiveProvenanceTab('STATEMENTS')}
                  className={`px-2.5 py-1 rounded-lg transition-all ${
                    activeProvenanceTab === 'STATEMENTS' ? 'bg-sky-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Context ({draft.merchant_statements.length})
                </button>
                <button
                  onClick={() => setActiveProvenanceTab('RECOMMENDATIONS')}
                  className={`px-2.5 py-1 rounded-lg transition-all ${
                    activeProvenanceTab === 'RECOMMENDATIONS' ? 'bg-purple-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Legal ({draft.ai_recommendations.length})
                </button>
                <button
                  onClick={() => setActiveProvenanceTab('UNKNOWN')}
                  className={`px-2.5 py-1 rounded-lg transition-all ${
                    activeProvenanceTab === 'UNKNOWN' ? 'bg-amber-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Pending ({draft.unknown_or_missing_info.length})
                </button>
              </div>

              {/* Provenance Content */}
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {activeProvenanceTab === 'VERIFIED' && (
                  <div className="space-y-2">
                    {draft.verified_facts.length === 0 ? (
                      <p className="text-xs text-slate-500 italic">No direct documentary facts extracted.</p>
                    ) : (
                      draft.verified_facts.map((fact, i) => (
                        <div key={i} className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-xs text-emerald-200 flex items-start gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                          <span>{fact}</span>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {activeProvenanceTab === 'STATEMENTS' && (
                  <div className="space-y-2">
                    {draft.merchant_statements.map((stmt, i) => (
                      <div key={i} className="p-3 rounded-lg bg-sky-950/40 border border-sky-800/60 text-xs text-sky-200">
                        {stmt}
                      </div>
                    ))}
                  </div>
                )}

                {activeProvenanceTab === 'RECOMMENDATIONS' && (
                  <div className="space-y-2">
                    {draft.ai_recommendations.map((rec, i) => (
                      <div key={i} className="p-3 rounded-lg bg-purple-950/40 border border-purple-800/60 text-xs text-purple-200">
                        {rec}
                      </div>
                    ))}
                  </div>
                )}

                {activeProvenanceTab === 'UNKNOWN' && (
                  <div className="space-y-2">
                    {draft.unknown_or_missing_info.map((u, i) => (
                      <div key={i} className="p-3 rounded-lg bg-amber-950/40 border border-amber-800/60 text-xs text-amber-200 flex items-start gap-2">
                        <HelpCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                        <span>{u}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Mandatory Approval Gate Card */}
          {draft && (
            <div className={`rounded-2xl p-6 shadow-xl border transition-all ${
              isApproved ? 'bg-emerald-950/30 border-emerald-500/50' : 'bg-slate-900/90 border-slate-800'
            }`}>
              <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                  <UserCheck className="w-4 h-4 text-sky-400" />
                  Mandatory Merchant Approval Gate
                </h3>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase ${
                  isApproved ? 'bg-emerald-950 text-emerald-400 border border-emerald-700' : 'bg-amber-950 text-amber-400 border border-amber-700'
                }`}>
                  {isApproved ? 'Approved' : 'Approval Required'}
                </span>
              </div>

              {!isApproved ? (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">
                      Approving Merchant Representative Name
                    </label>
                    <input
                      type="text"
                      value={approverName}
                      onChange={(e) => setApproverName(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-sky-500"
                      placeholder="e.g. Operations Manager / Full Name"
                    />
                  </div>

                  <label className="flex items-start gap-2.5 cursor-pointer select-none text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={approvalConfirmed}
                      onChange={(e) => setApprovalConfirmed(e.target.checked)}
                      className="mt-0.5 rounded bg-slate-950 border-slate-800 text-sky-600 focus:ring-0"
                    />
                    <span>
                      I have reviewed this response letter and confirmed that all factual claims match our business records.
                    </span>
                  </label>

                  <button
                    onClick={handleApprove}
                    disabled={!approvalConfirmed || !approverName.trim() || loading}
                    className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs uppercase tracking-wider shadow transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    <Check className="w-4 h-4" />
                    <span>Approve Response for Submission</span>
                  </button>
                </div>
              ) : (
                <div className="p-4 rounded-xl bg-emerald-950/50 border border-emerald-800/80 text-xs text-emerald-300 space-y-1">
                  <div className="flex items-center gap-2 font-bold">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Approved by: {draft.approved_by || approverName}</span>
                  </div>
                  <p className="text-[11px] text-emerald-400/80 font-mono">
                    Timestamp: {draft.approved_at || new Date().toISOString()}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Official PayPal Submission Card */}
          {draft && (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                  <Send className="w-4 h-4 text-sky-400" />
                  PayPal Resolution Center Submission
                </h3>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase ${
                  isSubmitted ? 'bg-blue-950 text-sky-400 border border-blue-700' : 'bg-slate-800 text-slate-400'
                }`}>
                  {isSubmitted ? 'Submitted' : 'Pending Action'}
                </span>
              </div>

              {!isSubmitted ? (
                <div className="space-y-3">
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Submits this merchant-approved response directly to PayPal&apos;s Dispute Evidence API.
                    Submission triggers the merchant-configured Zapier notification event.
                  </p>

                  <button
                    onClick={handleSubmit}
                    disabled={!isApproved || submitting}
                    className="w-full py-3 rounded-xl bg-gradient-to-r from-blue-600 via-sky-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs uppercase tracking-wider shadow-lg flex items-center justify-center gap-2 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {submitting ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Submitting to PayPal API…</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        <span>{isApproved ? 'Submit Official Response to PayPal' : 'Locked — Approval Mandatory'}</span>
                      </>
                    )}
                  </button>
                </div>
              ) : (
                <div className="p-4 rounded-xl bg-blue-950/60 border border-blue-800/80 text-xs text-sky-200 space-y-2">
                  <div className="flex items-center gap-2 font-bold text-sky-300">
                    <CheckCircle2 className="w-4 h-4 text-sky-400" />
                    <span>Evidence Successfully Submitted to PayPal</span>
                  </div>
                  <p className="text-[11px] font-mono text-slate-400">
                    Debug ID: {submissionResult?.submission_debug_id || draft?.submission_debug_id || 'PP-SANDBOX-DEBUG-OK'}
                  </p>
                  <p className="text-[11px] text-slate-300">
                    Zapier automation webhook event dispatched for merchant notification.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Audit Trail & Version History Card */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <History className="w-4 h-4 text-slate-400" />
              Dispute Audit Trail ({auditLogs.length} events)
            </h4>
            <div className="space-y-2 max-h-48 overflow-y-auto font-mono text-[11px] pr-1">
              {auditLogs.length === 0 ? (
                <p className="text-slate-500 italic">No audit entries logged yet.</p>
              ) : (
                auditLogs.map((log) => (
                  <div key={log.id} className="p-2 rounded bg-slate-950/60 border border-slate-800/60 flex items-center justify-between text-slate-400">
                    <div>
                      <span className="text-sky-400 font-bold">{log.action}</span>
                      <span className="text-slate-500 ml-1">by {log.actor}</span>
                    </div>
                    <span className="text-[10px] text-slate-600">{new Date(log.timestamp).toLocaleTimeString()}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {selectedDoc && (
        <DocumentDrawer doc={selectedDoc} onClose={() => setSelectedDoc(null)} />
      )}
    </div>
  );
}
