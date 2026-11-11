import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  HelpCircle,
  FileText,
  RefreshCw,
  CheckCircle2,
  ArrowRight,
  Layers,
  Sparkles,
  Info,
  Scale,
  Eye,
  AlertCircle,
  FileCheck,
  Check,
  Zap,
} from 'lucide-react';
import { fetchEvidenceMatrix, listDocuments, uploadDocument } from '../api';
import { useToast } from '../context/ToastContext';
import DocumentDrawer from './DocumentDrawer';

const PRESET_CASES = [
  {
    name: 'Case A: Complete Tracking Proof (Supported)',
    dispute_id: 'PP-D-88902',
    dispute_reason: 'MERCHANDISE_OR_SERVICE_NOT_RECEIVED',
    customer_complaint: 'I never received my package. It has been two weeks and nothing arrived at my doorstep.',
    amount: '189.50',
    currency: 'USD',
    merchant_context: 'Shipped via FedEx. Carrier scan confirms delivery to porch on May 3.',
    files: [
      {
        name: 'fedex_delivery_confirmation.txt',
        content: 'FedEx Tracking #940011189922\nStatus: Delivered May 3, 2:15 PM\nDestination: Austin, TX\nDelivered: 2026-05-03\nShipped: 2026-04-30\nSigned: Porch Delivery Confirmed',
        docType: 'delivery_confirmation',
      },
      {
        name: 'order_invoice_88902.txt',
        content: 'Invoice #88902\nOrder ID: ORD-88902\nTotal: $189.50 USD\nItems: Studio Monitors',
        docType: 'invoice',
      },
    ],
  },
  {
    name: 'Case B: Incomplete Records (Partially Supported)',
    dispute_id: 'PP-D-10203',
    dispute_reason: 'MERCHANDISE_OR_SERVICE_NOT_RECEIVED',
    customer_complaint: 'Where is my order? The tracking number is not updating.',
    amount: '145.00',
    currency: 'USD',
    merchant_context: 'Package handed to carrier, awaiting delivery scan.',
    files: [
      {
        name: 'shipping_manifest.txt',
        content: 'Manifest #MF-102\nTracking: 1Z88990011\nStatus: In Transit\nCarrier: UPS',
        docType: 'shipping_receipt',
      },
    ],
  },
  {
    name: 'Case C: Amount Conflict Detected (Contradictory)',
    dispute_id: 'PP-D-33042',
    dispute_reason: 'INCORRECT_AMOUNT',
    customer_complaint: 'I was charged $250.00 for an order that was listed for $180.00.',
    amount: '250.00',
    currency: 'USD',
    merchant_context: 'Customer invoice was billed at standard promotional pricing.',
    files: [
      {
        name: 'merchant_invoice_33042.txt',
        content: 'Official Invoice\nOrder ID: ORD-33042\nTotal: $180.00 USD\nItem: Smart Watch',
        docType: 'invoice',
      },
    ],
  },
];

export default function EvidenceMatrixWorkspace({ importedDispute = null }) {
  const { toast } = useToast();
  const [activeCase, setActiveCase] = useState(PRESET_CASES[0]);
  const [disputeId, setDisputeId] = useState(PRESET_CASES[0].dispute_id);
  const [disputeReason, setDisputeReason] = useState(PRESET_CASES[0].dispute_reason);
  const [customerComplaint, setCustomerComplaint] = useState(PRESET_CASES[0].customer_complaint);
  const [amount, setAmount] = useState(PRESET_CASES[0].amount);
  const [merchantContext, setMerchantContext] = useState(PRESET_CASES[0].merchant_context);

  const [matrixReport, setMatrixReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [documents, setDocuments] = useState([]);

  // Respond to PayPal imported dispute
  useEffect(() => {
    if (importedDispute) {
      setDisputeId(importedDispute.dispute_id);
      setDisputeReason(importedDispute.reason || importedDispute.dispute_reason || 'MERCHANDISE_OR_SERVICE_NOT_RECEIVED');
      setCustomerComplaint(importedDispute.customer_complaint || '');
      setAmount(String(importedDispute.dispute_amount?.value || importedDispute.amount || '0.00'));
      setMerchantContext(importedDispute.merchant_context || '');
      setMatrixReport(null);
      listDocuments(importedDispute.dispute_id).then(setDocuments).catch(console.error);
    }
  }, [importedDispute]);

  // Load preset scenario files
  const loadPreset = async (preset) => {
    setActiveCase(preset);
    setDisputeId(preset.dispute_id);
    setDisputeReason(preset.dispute_reason);
    setCustomerComplaint(preset.customer_complaint);
    setAmount(preset.amount);
    setMerchantContext(preset.merchant_context);
    setMatrixReport(null);

    // Upload preset files
    if (preset.files) {
      for (const f of preset.files) {
        try {
          const blob = new Blob([f.content], { type: 'text/plain' });
          const file = new File([blob], f.name, { type: 'text/plain' });
          await uploadDocument(file, preset.dispute_id, f.docType);
        } catch (err) {
          console.error('Error uploading preset file', err);
        }
      }
    }

    try {
      const docs = await listDocuments(preset.dispute_id);
      setDocuments(docs);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadPreset(PRESET_CASES[0]);
  }, []);

  const handleRunMatrix = async () => {
    setLoading(true);
    try {
      const payload = {
        dispute_reason: disputeReason,
        customer_complaint: customerComplaint,
        transaction_details: { amount: parseFloat(amount) || 0.0, currency: 'USD' },
        merchant_context: merchantContext,
        document_ids: documents.map((d) => d.id),
      };
      const report = await fetchEvidenceMatrix(disputeId, payload);
      setMatrixReport(report);
      toast.success(`Matrix analyzed. Completeness: ${report.completeness_score?.score || 0}/100.`, 'Analysis Complete');
    } catch (err) {
      toast.error(`Matrix analysis failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'Supported':
        return {
          bg: 'bg-emerald-950/80 border-emerald-500/40 text-emerald-400',
          icon: ShieldCheck,
          label: 'Supported',
        };
      case 'Partially supported':
        return {
          bg: 'bg-amber-950/80 border-amber-500/40 text-amber-400',
          icon: AlertCircle,
          label: 'Partially Supported',
        };
      case 'Contradictory':
        return {
          bg: 'bg-rose-950/80 border-rose-500/40 text-rose-400',
          icon: AlertTriangle,
          label: 'Contradictory',
        };
      default:
        return {
          bg: 'bg-slate-900 border-slate-700 text-slate-400',
          icon: HelpCircle,
          label: 'Unsupported',
        };
    }
  };

  const filteredItems = matrixReport?.matrix_items?.filter((item) => {
    if (statusFilter === 'ALL') return true;
    return item.evidence_status.toUpperCase().replace(/\s+/g, '_') === statusFilter;
  }) || [];

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-16">
      {/* Workspace Header & Scenario Selector */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-blue-950/80 border border-blue-800/60 text-sky-400 text-xs font-semibold uppercase tracking-wider mb-2">
              <Scale className="w-3.5 h-3.5" />
              Evidence Intelligence Engine
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Dispute Evidence Matrix Workspace
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Decomposes dispute allegations into discrete claims, cross-references merchant records,
              detects conflicting dates/amounts, and establishes an explainable completeness score.
            </p>
          </div>

          {/* Quick Case Switcher */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Scenarios:</span>
            {PRESET_CASES.map((sc, i) => (
              <button
                key={sc.dispute_id}
                onClick={() => loadPreset(sc)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
                  activeCase.dispute_id === sc.dispute_id
                    ? 'bg-sky-600 text-white border-sky-500 shadow-md'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                }`}
              >
                Case #{i + 1}
              </button>
            ))}
          </div>
        </div>

        {/* Active Case Quick Info */}
        <div className="mt-5 pt-4 border-t border-slate-800 grid grid-cols-1 sm:grid-cols-4 gap-4 text-xs font-mono">
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block text-[10px] uppercase">Dispute ID</span>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-200 font-bold">{disputeId}</span>
              {importedDispute && (
                <span
                  className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-bold uppercase ${
                    importedDispute.is_sandbox
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                      : 'bg-amber-950 text-amber-300 border border-amber-700'
                  }`}
                >
                  {importedDispute.is_sandbox ? 'Live' : 'Demo'}
                </span>
              )}
            </div>
          </div>
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block text-[10px] uppercase">PayPal Reason</span>
            <span className="text-sky-300 font-bold truncate block">{disputeReason}</span>
          </div>
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block text-[10px] uppercase">Disputed Amount</span>
            <span className="text-emerald-400 font-bold">${amount} USD</span>
          </div>
          <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 flex items-center justify-between">
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">Attached Documents</span>
              <span className="text-slate-200 font-bold">{documents.length} verified</span>
            </div>
            <button
              onClick={handleRunMatrix}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold font-sans flex items-center gap-1.5 shadow transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Evaluate Matrix</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Analysis Results */}
      {matrixReport && (
        <div className="space-y-6 animate-in fade-in duration-300">
          {/* Explainable Completeness Score Card */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-sky-950/80 border border-sky-800/60 rounded-xl text-sky-400">
                  <Sparkles className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-white tracking-tight">
                      Evidence Completeness Score
                    </h3>
                    <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[10px] font-mono text-slate-400 border border-slate-700">
                      Explainable Heuristic
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Grounded in documented evidence coverage. Never an invented win probability.
                  </p>
                </div>
              </div>

              {/* Big Score Display */}
              <div className="flex items-baseline gap-1 text-right">
                <span className="text-4xl font-black text-white tracking-tight">
                  {matrixReport.completeness_score.overall_score}
                </span>
                <span className="text-slate-500 text-base font-bold">/100</span>
              </div>
            </div>

            {/* Score Pillars Breakdown */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 my-5">
              <div className="p-3.5 bg-slate-950/70 border border-slate-800 rounded-xl">
                <span className="text-[11px] text-slate-400 font-medium uppercase tracking-wider block mb-1">
                  1. Claim Coverage
                </span>
                <div className="flex items-baseline justify-between">
                  <span className="text-lg font-bold text-sky-400">
                    {matrixReport.completeness_score.claim_coverage_points}
                  </span>
                  <span className="text-xs text-slate-500 font-mono">max 50 pts</span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div
                    className="bg-sky-500 h-full rounded-full"
                    style={{ width: `${(matrixReport.completeness_score.claim_coverage_points / 50) * 100}%` }}
                  />
                </div>
              </div>

              <div className="p-3.5 bg-slate-950/70 border border-slate-800 rounded-xl">
                <span className="text-[11px] text-slate-400 font-medium uppercase tracking-wider block mb-1">
                  2. Core Documentation
                </span>
                <div className="flex items-baseline justify-between">
                  <span className="text-lg font-bold text-emerald-400">
                    {matrixReport.completeness_score.core_evidence_points}
                  </span>
                  <span className="text-xs text-slate-500 font-mono">max 30 pts</span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div
                    className="bg-emerald-500 h-full rounded-full"
                    style={{ width: `${(matrixReport.completeness_score.core_evidence_points / 30) * 100}%` }}
                  />
                </div>
              </div>

              <div className="p-3.5 bg-slate-950/70 border border-slate-800 rounded-xl">
                <span className="text-[11px] text-slate-400 font-medium uppercase tracking-wider block mb-1">
                  3. Data Consistency
                </span>
                <div className="flex items-baseline justify-between">
                  <span className="text-lg font-bold text-teal-400">
                    {matrixReport.completeness_score.data_consistency_points}
                  </span>
                  <span className="text-xs text-slate-500 font-mono">max 20 pts</span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div
                    className="bg-teal-500 h-full rounded-full"
                    style={{ width: `${(matrixReport.completeness_score.data_consistency_points / 20) * 100}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Explanation and Disclaimer */}
            <div className="p-3.5 bg-slate-950/90 border border-slate-800/80 rounded-xl text-xs space-y-2">
              <p className="text-slate-300 leading-relaxed">
                <strong className="text-slate-200">Rubric Summary:</strong> {matrixReport.completeness_score.explanation}
              </p>
              <div className="pt-2 border-t border-slate-800 flex items-start gap-1.5 text-[11px] text-slate-400 italic">
                <Info className="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" />
                <span>{matrixReport.completeness_score.disclaimer}</span>
              </div>
            </div>
          </div>

          {/* Conflict Warnings Box (if any detected) */}
          {matrixReport.conflict_warnings?.length > 0 && (
            <div className="bg-amber-950/40 border border-amber-500/50 rounded-2xl p-6 shadow-xl space-y-3">
              <div className="flex items-center gap-2 text-amber-400 text-xs font-bold uppercase tracking-wider">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <span>Data Inconsistencies & Conflict Warnings Detected ({matrixReport.conflict_warnings.length})</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {matrixReport.conflict_warnings.map((c, i) => (
                  <div
                    key={i}
                    className="p-4 rounded-xl bg-amber-950/60 border border-amber-800/60 text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-amber-300 uppercase text-[10px] px-1.5 py-0.5 rounded bg-amber-900/60 border border-amber-700/60">
                        {c.conflict_type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-[11px] text-amber-400/80 font-mono">{c.source_reference}</span>
                    </div>
                    <p className="text-amber-200 leading-relaxed font-sans mt-1">
                      {c.explanation}
                    </p>
                    <div className="pt-1.5 border-t border-amber-900/40 text-[11px] font-mono text-amber-300 flex items-center justify-between">
                      <span>Disputed: {c.disputed_value}</span>
                      <span>Evidence: {c.evidence_value}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evidence Matrix Section */}
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Layers className="w-4 h-4 text-sky-400" />
                  Claim-to-Evidence Matrix
                </h3>
                <p className="text-xs text-slate-400">
                  Detailed evaluation of each dispute claim against merchant evidence records.
                </p>
              </div>

              {/* Status Filter Tabs */}
              <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800 text-xs font-medium">
                {['ALL', 'SUPPORTED', 'PARTIALLY_SUPPORTED', 'UNSUPPORTED', 'CONTRADICTORY'].map((st) => (
                  <button
                    key={st}
                    onClick={() => setStatusFilter(st)}
                    className={`px-3 py-1 rounded-lg transition-all ${
                      statusFilter === st
                        ? 'bg-sky-600 text-white font-semibold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {st === 'ALL' ? 'All' : st.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            </div>

            {/* Matrix Cards */}
            <div className="space-y-4">
              {filteredItems.length === 0 ? (
                <div className="p-8 text-center text-slate-500 bg-slate-900/40 rounded-2xl border border-slate-800">
                  <p className="text-xs">No matrix items match the selected status filter.</p>
                </div>
              ) : (
                filteredItems.map((item, idx) => {
                  const badge = getStatusBadge(item.evidence_status);
                  const Icon = badge.icon;

                  return (
                    <div
                      key={idx}
                      className="bg-slate-900/90 border border-slate-800 hover:border-slate-700/80 rounded-2xl p-6 shadow-md transition-all space-y-4"
                    >
                      {/* Row Header */}
                      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                              {item.claim_type.replace(/_/g, ' ')}
                            </span>
                            <span className="text-xs font-mono text-slate-500">Claim #{idx + 1}</span>
                          </div>
                          <h4 className="text-sm font-semibold text-white leading-snug">
                            {item.claim}
                          </h4>
                        </div>

                        {/* Status Badge */}
                        <div className={`px-3 py-1.5 rounded-xl border flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider shrink-0 ${badge.bg}`}>
                          <Icon className="w-4 h-4" />
                          <span>{badge.label}</span>
                        </div>
                      </div>

                      {/* Evidence Relevance Explanation */}
                      <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 text-xs">
                        <span className="text-slate-400 font-semibold uppercase text-[10px] tracking-wider block mb-1">
                          Relevance Rationale
                        </span>
                        <p className="text-slate-200 leading-relaxed">
                          {item.evidence_relevance_explanation}
                        </p>
                      </div>

                      {/* Supporting Evidence Citations */}
                      {item.supporting_evidence?.length > 0 && (
                        <div className="space-y-2">
                          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                            Documentary Citations
                          </span>
                          <div className="grid grid-cols-1 gap-2">
                            {item.supporting_evidence.map((ev, i) => (
                              <div
                                key={i}
                                className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950/50 border border-slate-800 text-xs text-sky-300 font-mono"
                              >
                                <span>{ev}</span>
                                {item.source_documents[i] && (
                                  <span className="text-[10px] text-slate-400 px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                                    {item.source_documents[i]}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Missing Information & Contradiction Warnings */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                        {item.missing_information?.length > 0 && (
                          <div className="p-3 rounded-xl bg-sky-950/30 border border-sky-900/50 space-y-1.5">
                            <span className="text-sky-400 font-semibold text-[11px] uppercase tracking-wider flex items-center gap-1.5">
                              <HelpCircle className="w-3.5 h-3.5" />
                              Missing Proof Items
                            </span>
                            <ul className="space-y-1 text-slate-300">
                              {item.missing_information.map((m, i) => (
                                <li key={i} className="flex items-start gap-1.5">
                                  <span className="text-sky-400">•</span>
                                  <span>{m}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {item.recommended_merchant_action && (
                          <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-900/50 space-y-1.5">
                            <span className="text-emerald-400 font-semibold text-[11px] uppercase tracking-wider flex items-center gap-1.5">
                              <ArrowRight className="w-3.5 h-3.5" />
                              Recommended Merchant Action
                            </span>
                            <p className="text-slate-200 leading-relaxed">
                              {item.recommended_merchant_action}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Action Center / Recommended Next Actions */}
          {matrixReport.recommended_next_actions?.length > 0 && (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Merchant Evidence Action Plan
              </h3>
              <div className="space-y-2">
                {matrixReport.recommended_next_actions.map((act, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-200"
                  >
                    <span className="w-6 h-6 rounded-full bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-xs font-bold shrink-0">
                      {i + 1}
                    </span>
                    <span className="font-medium">{act}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {selectedDoc && (
        <DocumentDrawer doc={selectedDoc} onClose={() => setSelectedDoc(null)} />
      )}
    </div>
  );
}
