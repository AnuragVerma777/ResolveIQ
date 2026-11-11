import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  UploadCloud,
  FileText,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  ExternalLink,
  Layers,
  FileCheck,
  Eye,
  RefreshCw,
} from 'lucide-react';
import ConfidenceMeter from './ConfidenceMeter';
import DocumentDrawer from './DocumentDrawer';
import { classifyDispute, listDocuments, uploadDocument } from '../api';
import { useToast } from '../context/ToastContext';

const DEMO_SCENARIOS = [
  {
    name: '1. Item Not Received (FedEx Delivered)',
    dispute_id: 'PP-DISP-88902',
    dispute_reason: 'MERCHANDISE_OR_SERVICE_NOT_RECEIVED',
    customer_complaint: 'I never received my package. It has been two weeks and nothing arrived at my doorstep.',
    transaction_id: 'TXN-99882244',
    amount: '189.50',
    currency: 'USD',
    merchant_context: 'Package was shipped via FedEx Home Delivery with signature. Tracking shows delivered to porch on May 3.',
    sampleFile: {
      name: 'fedex_delivery_confirmation.txt',
      content: 'FedEx Tracking #940011189922\nStatus: Delivered May 3, 2:15 PM\nDestination: Austin, TX\nSigned: Porch Delivery Confirmed',
      docType: 'delivery_confirmation',
    },
  },
  {
    name: '2. Unauthorized Transaction Claim',
    dispute_id: 'PP-DISP-44011',
    dispute_reason: 'UNAUTHORIZED_PAYMENT',
    customer_complaint: 'I did not recognize this transaction on my card statement. My account was compromised.',
    transaction_id: 'TXN-33441199',
    amount: '450.00',
    currency: 'USD',
    merchant_context: 'Order was placed from verified buyer email, shipped to PayPal seller protection eligible address with matching billing zip.',
    sampleFile: {
      name: 'order_receipt_seller_protection.txt',
      content: 'Order #ORD-44011\nBuyer Email: confirmed_buyer@example.com\nSeller Protection: Eligible\nIP: 198.51.100.42\nBilling Match: Passed',
      docType: 'order_confirmation',
    },
  },
  {
    name: '3. Significantly Not As Described',
    dispute_id: 'PP-DISP-55204',
    dispute_reason: 'SIGNIFICANTLY_NOT_AS_DESCRIBED',
    customer_complaint: 'The smartphone arrived with a cracked screen and deep scratches. The listing said brand new.',
    transaction_id: 'TXN-88771122',
    amount: '699.00',
    currency: 'USD',
    merchant_context: 'Product was factory sealed in original box with tamper evident tape. Warehouse dispatch inspection passed.',
    sampleFile: {
      name: 'warehouse_dispatch_checklist.txt',
      content: 'Dispatch Inspection #DI-8877\nCondition: Factory Sealed\nTamper Seal: Intact\nSerial Number: SN-998234-A',
      docType: 'shipping_receipt',
    },
  },
];

export default function DisputeInvestigation() {
  const { toast } = useToast();
  const [disputeId, setDisputeId] = useState('PP-DISP-88902');
  const [disputeReason, setDisputeReason] = useState('MERCHANDISE_OR_SERVICE_NOT_RECEIVED');
  const [customerComplaint, setCustomerComplaint] = useState(
    'I never received my package. It has been two weeks and nothing arrived at my doorstep.'
  );
  const [transactionId, setTransactionId] = useState('TXN-99882244');
  const [amount, setAmount] = useState('189.50');
  const [currency, setCurrency] = useState('USD');
  const [merchantContext, setMerchantContext] = useState(
    'Package was shipped via FedEx Home Delivery with signature. Tracking shows delivered to porch on May 3.'
  );

  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [classifying, setClassifying] = useState(false);
  const [classificationResult, setClassificationResult] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);

  // Load documents for current dispute
  const refreshDocuments = async () => {
    try {
      const docs = await listDocuments(disputeId);
      setDocuments(docs);
    } catch (err) {
      console.error('Failed to load documents', err);
    }
  };

  useEffect(() => {
    if (disputeId) {
      refreshDocuments();
    }
  }, [disputeId]);

  const loadScenario = async (scenario) => {
    setDisputeId(scenario.dispute_id);
    setDisputeReason(scenario.dispute_reason);
    setCustomerComplaint(scenario.customer_complaint);
    setTransactionId(scenario.transaction_id);
    setAmount(scenario.amount);
    setCurrency(scenario.currency);
    setMerchantContext(scenario.merchant_context);
    setClassificationResult(null);

    // Auto-create sample file for instant demonstration
    if (scenario.sampleFile) {
      try {
        const blob = new Blob([scenario.sampleFile.content], { type: 'text/plain' });
        const file = new File([blob], scenario.sampleFile.name, { type: 'text/plain' });
        await uploadDocument(file, scenario.dispute_id, scenario.sampleFile.docType);
        const docs = await listDocuments(scenario.dispute_id);
        setDocuments(docs);
      } catch (err) {
        console.error('Failed to load scenario file', err);
      }
    }
  };

  const handleFileUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    setUploading(true);
    setUploadError(null);

    try {
      for (const file of files) {
        await uploadDocument(file, disputeId, 'other');
      }
      await refreshDocuments();
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleClassify = async () => {
    if (!disputeId) return;
    setClassifying(true);
    setClassificationResult(null);

    try {
      const payload = {
        dispute_id: disputeId,
        dispute_reason: disputeReason,
        customer_complaint: customerComplaint,
        transaction_details: {
          transaction_id: transactionId,
          amount: parseFloat(amount) || 0.0,
          currency: currency,
        },
        merchant_context: merchantContext,
        document_ids: documents.map((d) => d.id),
      };

      const result = await classifyDispute(payload);
      setClassificationResult(result);
      toast.success(`Classification complete: ${result.category} (${Math.round((result.confidence_score || 0.9) * 100)}%)`, 'Classified');
    } catch (err) {
      toast.error(`Classification error: ${err.message}`);
    } finally {
      setClassifying(false);
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      {/* Top Banner / Scenarios */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-sky-950/80 border border-sky-800/60 text-sky-400 text-xs font-semibold uppercase tracking-wider mb-2">
              <Sparkles className="w-3.5 h-3.5" />
              Gemini Dispute Adjudication Engine
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              AI Dispute Investigation & Classification
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Cross-analyzes PayPal dispute claims against uploaded invoices, carrier tracking scans,
              and merchant records. Structured evidence-grounded findings with strict anti-hallucination gates.
            </p>
          </div>

          {/* Quick Scenario Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 font-medium mr-1">Load Demo Case:</span>
            {DEMO_SCENARIOS.map((sc, idx) => (
              <button
                key={sc.dispute_id}
                onClick={() => loadScenario(sc)}
                className="px-3 py-1.5 rounded-lg bg-slate-800/90 hover:bg-slate-700 text-xs font-medium text-slate-200 border border-slate-700/80 transition-all hover:scale-[1.02]"
              >
                Case #{idx + 1}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Dispute Dossier & Evidence Upload */}
        <div className="lg:col-span-5 space-y-6">
          {/* Dispute Input Card */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2 border-b border-slate-800 pb-3">
              <Layers className="w-4 h-4 text-sky-400" />
              Dispute Dossier
            </h3>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  PayPal Dispute ID
                </label>
                <input
                  type="text"
                  value={disputeId}
                  onChange={(e) => setDisputeId(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
                  placeholder="e.g. PP-D-12345"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Transaction ID
                </label>
                <input
                  type="text"
                  value={transactionId}
                  onChange={(e) => setTransactionId(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
                  placeholder="e.g. TXN-998822"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">
                PayPal Reported Reason
              </label>
              <input
                type="text"
                value={disputeReason}
                onChange={(e) => setDisputeReason(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
                placeholder="As reported by PayPal API"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Disputed Amount
                </label>
                <input
                  type="text"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Currency
                </label>
                <input
                  type="text"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">
                Customer Complaint / Claim Text
              </label>
              <textarea
                rows={3}
                value={customerComplaint}
                onChange={(e) => setCustomerComplaint(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-sky-500 resize-none leading-relaxed"
                placeholder="Verbatim buyer statement from PayPal dispute claim..."
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">
                Merchant-Provided Context
              </label>
              <textarea
                rows={2}
                value={merchantContext}
                onChange={(e) => setMerchantContext(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-sky-500 resize-none leading-relaxed"
                placeholder="Internal notes, carrier confirmation, warehouse audit..."
              />
            </div>
          </div>

          {/* Evidence Documents Card */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <FileCheck className="w-4 h-4 text-emerald-400" />
                Evidence Documents ({documents.length})
              </h3>
              <button
                onClick={refreshDocuments}
                title="Refresh documents"
                className="text-slate-400 hover:text-slate-200 p-1"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Upload Dropzone */}
            <div className="relative border-2 border-dashed border-slate-800 hover:border-slate-700 bg-slate-950/60 rounded-xl p-5 text-center transition-all">
              <input
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.csv,.md,.png,.jpg,.jpeg,.webp"
                onChange={handleFileUpload}
                disabled={uploading}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              <UploadCloud className="w-7 h-7 text-sky-400 mx-auto mb-2" />
              <p className="text-xs font-semibold text-slate-200">
                {uploading ? 'Processing & extracting text...' : 'Upload Evidence Documents'}
              </p>
              <p className="text-[11px] text-slate-500 mt-1">
                PDF invoices, DOCX, carrier scans, emails, screenshots (max 15MB)
              </p>
            </div>

            {uploadError && (
              <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800/80 text-rose-300 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            {/* Document list */}
            <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
              {documents.length === 0 ? (
                <p className="text-xs text-slate-500 italic text-center py-4">
                  No evidence files attached to this dispute yet.
                </p>
              ) : (
                documents.map((d) => (
                  <div
                    key={d.id}
                    className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 hover:border-slate-700 transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <FileText className="w-4 h-4 text-sky-400 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-slate-200 truncate" title={d.filename}>
                          {d.filename}
                        </p>
                        <div className="flex items-center gap-1.5 text-[10px] text-slate-500 font-mono">
                          <span className="capitalize">{d.doc_type || 'doc'}</span>
                          <span>•</span>
                          <span>{(d.file_size / 1024).toFixed(1)} KB</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                        d.status === 'COMPLETED' ? 'bg-emerald-950 text-emerald-400' :
                        d.status === 'FAILED' ? 'bg-rose-950 text-rose-400' :
                        'bg-amber-950 text-amber-400'
                      }`}>
                        {d.status}
                      </span>
                      <button
                        onClick={() => setSelectedDoc(d)}
                        className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
                        title="View document intelligence"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Run Classification Button */}
            <button
              onClick={handleClassify}
              disabled={classifying || !disputeId}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-sky-600 via-sky-500 to-blue-600 hover:from-sky-500 hover:to-blue-500 font-semibold text-white text-xs uppercase tracking-wider shadow-lg shadow-sky-950/50 flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.01]"
            >
              {classifying ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Synthesizing Dispute Intelligence…</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Classify & Investigate Dispute</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right Column: Visual Adjudication Results */}
        <div className="lg:col-span-7 space-y-6">
          {!classificationResult ? (
            <div className="h-full min-h-[480px] flex flex-col items-center justify-center p-12 rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 text-center text-slate-500">
              <Sparkles className="w-12 h-12 text-slate-700 mb-4 animate-pulse" />
              <h4 className="text-sm font-semibold text-slate-300 mb-1">
                Investigation Engine Ready
              </h4>
              <p className="text-xs text-slate-500 max-w-md">
                Select a demo scenario or enter dispute details and click &ldquo;Classify & Investigate Dispute&rdquo; to generate structured adjudicative findings.
              </p>
            </div>
          ) : (
            <div className="space-y-6 animate-in fade-in duration-300">
              {/* Classification Category & Comparison Card */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Category Adjudication
                  </span>
                  <span className="text-xs font-mono text-slate-500">
                    Dispute ID: {classificationResult.dispute_id}
                  </span>
                </div>

                {/* Side-by-side comparison */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
                    <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block mb-1">
                      Original PayPal Reason
                    </span>
                    <div className="text-sm font-mono font-bold text-slate-300 truncate">
                      {classificationResult.original_paypal_reason}
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-gradient-to-br from-sky-950/80 to-blue-950/80 border border-sky-800/60 shadow-inner">
                    <span className="text-[11px] font-medium text-sky-400 uppercase tracking-wider block mb-1">
                      AI Classified Category
                    </span>
                    <div className="text-base font-bold text-white capitalize flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-sky-400" />
                      {classificationResult.dispute_category.replace(/_/g, ' ')}
                    </div>
                  </div>
                </div>

                {/* Classification Explanation */}
                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800/80">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                    Classification Rationale
                  </span>
                  <p className="text-xs text-slate-200 leading-relaxed">
                    {classificationResult.explanation}
                  </p>
                </div>
              </div>

              {/* Confidence Gauge Card */}
              <ConfidenceMeter
                confidence={classificationResult.confidence}
                disclaimer={classificationResult.disclaimer}
              />

              {/* Key Facts Extracted */}
              {classificationResult.key_facts?.length > 0 && (
                <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    Key Verified Facts ({classificationResult.key_facts.length})
                  </h4>
                  <div className="space-y-2">
                    {classificationResult.key_facts.map((fact, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-2.5 p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs text-slate-300 leading-relaxed"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                        <span>{fact}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Relevant Evidence Items */}
              {classificationResult.relevant_evidence?.length > 0 && (
                <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-sky-400" />
                    Relevant Evidence Citations
                  </h4>
                  <div className="space-y-3">
                    {classificationResult.relevant_evidence.map((ev, i) => (
                      <div
                        key={i}
                        className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-sky-400" />
                            {ev.document_name}
                          </span>
                          <span className="px-2 py-0.5 rounded bg-slate-800 text-[10px] font-mono text-slate-400 uppercase">
                            {ev.evidence_type}
                          </span>
                        </div>
                        <blockquote className="border-l-2 border-sky-500 pl-3 py-0.5 text-xs text-sky-200/90 font-mono italic bg-sky-950/20 rounded-r">
                          &ldquo;{ev.source_excerpt}&rdquo;
                        </blockquote>
                        {ev.relevance_explanation && (
                          <p className="text-[11px] text-slate-400">
                            <strong className="text-slate-300">Relevance:</strong> {ev.relevance_explanation}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Potential Contradictions Alert */}
              {classificationResult.potential_contradictions?.length > 0 && (
                <div className="bg-amber-950/40 border border-amber-500/40 rounded-2xl p-6 shadow-lg space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                    Potential Contradictions Identified
                  </h4>
                  <div className="space-y-2">
                    {classificationResult.potential_contradictions.map((c, i) => (
                      <div
                        key={i}
                        className="p-3 rounded-lg bg-amber-950/60 border border-amber-800/60 text-xs text-amber-200 leading-relaxed"
                      >
                        {c}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Missing Information Checklist */}
              {classificationResult.missing_information?.length > 0 && (
                <div className="bg-sky-950/30 border border-sky-800/40 rounded-2xl p-6 shadow-md space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-sky-400 flex items-center gap-2">
                    <HelpCircle className="w-4 h-4 text-sky-400" />
                    Missing Evidence Required
                  </h4>
                  <ul className="space-y-2">
                    {classificationResult.missing_information.map((item, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-xs text-slate-300 leading-relaxed"
                      >
                        <span className="text-sky-400 font-mono font-bold">•</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Recommended Next Actions */}
              {classificationResult.recommended_next_actions?.length > 0 && (
                <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                    <ArrowRight className="w-4 h-4 text-emerald-400" />
                    Recommended Next Actions
                  </h4>
                  <div className="space-y-2">
                    {classificationResult.recommended_next_actions.map((act, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-3 p-3 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-200"
                      >
                        <span className="w-5 h-5 rounded-full bg-slate-800 text-slate-300 flex items-center justify-center text-[10px] font-bold shrink-0">
                          {i + 1}
                        </span>
                        <span>{act}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Slide-out Document Drawer */}
      {selectedDoc && (
        <DocumentDrawer doc={selectedDoc} onClose={() => setSelectedDoc(null)} />
      )}
    </div>
  );
}
