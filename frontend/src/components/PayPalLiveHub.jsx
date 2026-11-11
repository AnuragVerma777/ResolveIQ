import React, { useState, useEffect } from 'react';
import {
  CreditCard,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  ArrowRight,
  Clock,
  Send,
  Search,
  FileCheck,
  Info,
  Calendar,
  DollarSign,
  User,
  Package,
  Check,
  Sparkles,
} from 'lucide-react';
import {
  fetchPayPalStatus,
  fetchPayPalDisputes,
  fetchPayPalTransactions,
  submitPayPalEvidence,
  importPayPalDispute,
} from '../api';
import { useToast } from '../context/ToastContext';

export default function PayPalLiveHub({ onSelectDispute }) {
  const { toast } = useToast();
  const [statusInfo, setStatusInfo] = useState(null);
  const [disputes, setDisputes] = useState([]);
  const [disputeSource, setDisputeSource] = useState('demo');
  const [isSandboxData, setIsSandboxData] = useState(false);
  const [disputeNotice, setDisputeNotice] = useState('');
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [filterState, setFilterState] = useState('ALL');
  const [activeSubTab, setActiveSubTab] = useState('disputes'); // 'disputes' | 'transactions' | 'setup'

  // Direct Evidence Submission Modal State
  const [submittingDispute, setSubmittingDispute] = useState(null);
  const [evidenceType, setEvidenceType] = useState('PROOF_OF_FULFILLMENT');
  const [carrierName, setCarrierName] = useState('FEDEX');
  const [trackingNumber, setTrackingNumber] = useState('');
  const [submissionNotes, setSubmissionNotes] = useState('');
  const [submissionLoading, setSubmissionLoading] = useState(false);
  const [submissionSuccess, setSubmissionSuccess] = useState(null);
  const [submissionError, setSubmissionError] = useState(null);

  // Load Status and Disputes
  const loadData = async () => {
    setRefreshing(true);
    setSubmissionError(null);
    try {
      const [st, dispData, txData] = await Promise.all([
        fetchPayPalStatus().catch((err) => ({
          connected: false,
          configured: false,
          mode: 'error',
          message: err.message,
          base_url: 'https://api-m.sandbox.paypal.com',
        })),
        fetchPayPalDisputes(filterState === 'ALL' ? null : filterState).catch((err) => ({
          source: 'demo',
          is_sandbox: false,
          items: [],
          notice: `Could not reach PayPal: ${err.message}`,
        })),
        fetchPayPalTransactions().catch(() => ({ transaction_details: [] })),
      ]);

      setStatusInfo(st);
      setDisputes(dispData.items || []);
      setDisputeSource(dispData.source || 'demo');
      setIsSandboxData(Boolean(dispData.is_sandbox));
      setDisputeNotice(dispData.notice || '');
      setTransactions(txData.transaction_details || []);
    } catch (err) {
      console.error('Error fetching PayPal data', err);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [filterState]);

  // Handle Import & Open in Workspace
  const handleOpenInWorkspace = async (dispute) => {
    try {
      await importPayPalDispute(dispute.dispute_id);
      toast.success(`Imported dispute ${dispute.dispute_id} into Investigation Workspace.`, 'Dispute Loaded');
      if (onSelectDispute) {
        onSelectDispute(dispute);
      }
    } catch (err) {
      toast.error(`Failed to import dispute into workspace: ${err.message}`);
    }
  };

  // Handle Direct Evidence Submission to PayPal
  const handleSubmitEvidence = async (e) => {
    e.preventDefault();
    if (!submittingDispute) return;
    setSubmissionLoading(true);
    setSubmissionError(null);
    setSubmissionSuccess(null);

    try {
      const payload = {
        evidence_type: evidenceType,
        carrier_name: carrierName,
        tracking_number: trackingNumber,
        notes: submissionNotes || `Proof of fulfillment submitted for dispute ${submittingDispute.dispute_id}`,
      };
      const res = await submitPayPalEvidence(submittingDispute.dispute_id, payload);
      setSubmissionSuccess(res);
      await loadData();
    } catch (err) {
      setSubmissionError(err.message);
    } finally {
      setSubmissionLoading(false);
    }
  };

  const isLiveConnected = statusInfo?.connected && statusInfo?.mode === 'sandbox';

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-16">
      {/* Top Banner: PayPal Sandbox Connection & Status */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="p-2 rounded-xl bg-blue-600/20 text-sky-400 border border-sky-500/30">
                <CreditCard className="w-5 h-5" />
              </span>
              <span className="text-xs font-mono font-bold uppercase tracking-widest text-sky-400">
                PayPal Resolution Center · Live Gateway
              </span>
            </div>
            <h2 className="text-2xl font-black text-white tracking-tight">
              PayPal Sandbox Synchronization & Adjudication Hub
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Authenticate via OAuth 2.0 client credentials, retrieve live sandbox claims,
              verify buyer transactions, and submit documented evidence directly to PayPal Resolution APIs.
            </p>
          </div>

          {/* Connection Status Widget */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 bg-slate-950/80 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center gap-3">
              <span className="relative flex h-3 w-3">
                <span
                  className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                    isLiveConnected ? 'bg-emerald-400' : 'bg-amber-400'
                  }`}
                />
                <span
                  className={`relative inline-flex rounded-full h-3 w-3 ${
                    isLiveConnected ? 'bg-emerald-500' : 'bg-amber-500'
                  }`}
                />
              </span>
              <div>
                <div className="text-xs font-bold text-white flex items-center gap-2">
                  <span>{isLiveConnected ? 'PayPal Sandbox Connected' : 'Demo / Sandbox Mock Mode'}</span>
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-mono uppercase font-bold ${
                      isLiveConnected
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                        : 'bg-amber-950 text-amber-300 border border-amber-700'
                    }`}
                  >
                    {isLiveConnected ? 'LIVE SANDBOX' : 'DEMO RECORDS'}
                  </span>
                </div>
                <div className="text-[11px] font-mono text-slate-400">
                  {statusInfo?.base_url || 'https://api-m.sandbox.paypal.com'}
                  {statusInfo?.token_expires_in_seconds && (
                    <span className="text-emerald-400 ml-2">
                      (Token valid: {Math.round(statusInfo.token_expires_in_seconds / 60)}m)
                    </span>
                  )}
                </div>
              </div>
            </div>

            <button
              onClick={loadData}
              disabled={refreshing}
              className="px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-slate-200 flex items-center gap-2 transition-all shadow-sm disabled:opacity-50"
              title="Refresh PayPal connection and sync records"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-sky-400' : 'text-slate-400'}`} />
              <span>{refreshing ? 'Syncing…' : 'Refresh Data'}</span>
            </button>
          </div>
        </div>

        {/* Data Origin & Sandbox Guidance Notice */}
        <div className="mt-4 pt-4 border-t border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between text-xs text-slate-400 gap-2">
          <div className="flex items-center gap-2">
            <Info className="w-4 h-4 text-sky-400 shrink-0" />
            <span>
              {isSandboxData ? (
                <span className="text-emerald-300 font-medium">
                  Verified: Data retrieved directly from PayPal Developer Sandbox REST API.
                </span>
              ) : (
                <span>
                  {disputeNotice ||
                    'Credentials (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET) not detected in environment. Displaying realistic PayPal REST demo dataset.'}
                </span>
              )}
            </span>
          </div>
          <div className="text-[11px] font-mono text-slate-500">
            Source: <strong className="text-slate-300">{disputeSource.toUpperCase()}</strong>
          </div>
        </div>
      </div>

      {/* Sub-Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveSubTab('disputes')}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
            activeSubTab === 'disputes'
              ? 'bg-sky-600 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>PayPal Disputes ({disputes.length})</span>
        </button>
        <button
          onClick={() => setActiveSubTab('transactions')}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
            activeSubTab === 'transactions'
              ? 'bg-sky-600 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          <Search className="w-3.5 h-3.5" />
          <span>Transaction Search ({transactions.length})</span>
        </button>
        <button
          onClick={() => setActiveSubTab('setup')}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
            activeSubTab === 'setup'
              ? 'bg-sky-600 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          <FileCheck className="w-3.5 h-3.5" />
          <span>Sandbox Guide & Credentials</span>
        </button>
      </div>

      {/* TAB 1: DISPUTES FEED & ADJUDICATION */}
      {activeSubTab === 'disputes' && (
        <div className="space-y-6">
          {/* Dispute State Filters */}
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Filter State:
              </span>
              {['ALL', 'REQUIRED_ACTION', 'UNDER_REVIEW', 'WAITING_FOR_SELLER_RESPONSE'].map((st) => (
                <button
                  key={st}
                  onClick={() => setFilterState(st)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition-all ${
                    filterState === st
                      ? 'bg-slate-800 text-sky-400 border border-sky-500/40 shadow-sm'
                      : 'text-slate-500 hover:text-slate-300 hover:bg-slate-900'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>

            <div className="text-xs text-slate-400">
              Showing <strong className="text-white">{disputes.length}</strong> dispute record(s)
            </div>
          </div>

          {/* Dispute Cards Grid */}
          <div className="grid grid-cols-1 gap-6">
            {disputes.length === 0 ? (
              <div className="p-12 text-center bg-slate-900/60 rounded-2xl border border-slate-800 text-slate-400">
                <ShieldCheck className="w-12 h-12 mx-auto text-slate-600 mb-3" />
                <h3 className="text-base font-bold text-slate-300">No disputes found for filter</h3>
                <p className="text-xs text-slate-500 mt-1">
                  Try adjusting the filter state or refreshing your PayPal connection.
                </p>
              </div>
            ) : (
              disputes.map((dispute) => {
                const amount = dispute.dispute_amount?.value || '0.00';
                const currency = dispute.dispute_amount?.currency_code || 'USD';
                const transactionsList = dispute.disputed_transactions || [];
                const firstTx = transactionsList[0] || {};
                const allowedOptions = dispute.allowed_response_options || [];

                return (
                  <div
                    key={dispute.dispute_id}
                    className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-2xl p-6 shadow-md transition-all space-y-5"
                  >
                    {/* Header Row: ID, Origin Pill, Status, Amount */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="text-base font-mono font-black text-white">
                          {dispute.dispute_id}
                        </span>

                        {/* Sandbox vs Demo Pill */}
                        <span
                          className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase ${
                            dispute.is_sandbox
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                              : 'bg-amber-950 text-amber-300 border border-amber-700'
                          }`}
                        >
                          {dispute.is_sandbox ? 'Live Sandbox' : 'Demo Record'}
                        </span>

                        <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-semibold">
                          {dispute.status}
                        </span>

                        {dispute.dispute_life_cycle_stage && (
                          <span className="text-xs font-mono px-2 py-0.5 rounded bg-blue-950/80 text-blue-300 border border-blue-800">
                            Stage: {dispute.dispute_life_cycle_stage}
                          </span>
                        )}
                      </div>

                      <div className="text-right">
                        <div className="text-lg font-black text-white">
                          ${amount} <span className="text-xs font-mono text-slate-400">{currency}</span>
                        </div>
                        {dispute.seller_response_due_date && (
                          <div className="text-[11px] font-mono text-amber-400 flex items-center gap-1 justify-end mt-0.5">
                            <Clock className="w-3 h-3" />
                            <span>Due: {new Date(dispute.seller_response_due_date).toLocaleDateString()}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Dispute Reason & Customer Complaint */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800/80 space-y-2">
                        <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">
                          PayPal Dispute Reason
                        </div>
                        <div className="text-sm font-bold text-sky-300">
                          {dispute.reason?.replace(/_/g, ' ')}
                        </div>
                        {dispute.customer_complaint && (
                          <div className="text-xs text-slate-300 italic pt-1">
                            &ldquo;{dispute.customer_complaint}&rdquo;
                          </div>
                        )}
                      </div>

                      <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800/80 space-y-2">
                        <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">
                          Disputed Transaction & Customer
                        </div>
                        <div className="text-xs text-slate-200 flex items-center gap-2">
                          <User className="w-3.5 h-3.5 text-slate-400" />
                          <span>{firstTx.buyer?.name || 'Customer Name'}</span>
                          <span className="text-slate-500 font-mono text-[11px]">
                            ({firstTx.buyer?.email || 'email not provided'})
                          </span>
                        </div>
                        <div className="text-[11px] font-mono text-slate-400">
                          Transaction ID: <span className="text-slate-300">{firstTx.seller_transaction_id || 'N/A'}</span>
                        </div>
                        {dispute.merchant_context && (
                          <div className="text-[11px] text-slate-400 pt-1">
                            <strong>Merchant Context:</strong> {dispute.merchant_context}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Allowed Actions & Evidence Requirements */}
                    <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-slate-400 font-medium">Supported Actions:</span>
                        {allowedOptions.length === 0 ? (
                          <span className="text-xs font-mono text-slate-500">PROVIDE_EVIDENCE</span>
                        ) : (
                          allowedOptions.map((opt) => (
                            <span
                              key={opt}
                              className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-sky-300 border border-slate-700"
                            >
                              {opt}
                            </span>
                          ))
                        )}
                      </div>

                      {/* Action Buttons */}
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => {
                            setSubmittingDispute(dispute);
                            setSubmissionSuccess(null);
                            setSubmissionError(null);
                          }}
                          className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 flex items-center gap-2 transition-all shadow"
                        >
                          <Send className="w-3.5 h-3.5 text-sky-400" />
                          <span>Submit Evidence</span>
                        </button>

                        <button
                          onClick={() => handleOpenInWorkspace(dispute)}
                          className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-xs font-bold text-white flex items-center gap-2 transition-all shadow-md shadow-sky-600/30"
                        >
                          <span>Open in Investigation</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* TAB 2: TRANSACTION SEARCH */}
      {activeSubTab === 'transactions' && (
        <div className="space-y-6">
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md">
            <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                  <Search className="w-4 h-4 text-sky-400" />
                  PayPal Transaction Search API
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Search merchant transaction records (31-day RFC3339 windows) to verify customer charges and fulfillment details.
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400">
                {transactions.length} records retrieved
              </span>
            </div>

            {/* Transactions List */}
            <div className="space-y-3">
              {transactions.length === 0 ? (
                <p className="text-xs text-slate-500 italic p-6 text-center">No transaction records returned.</p>
              ) : (
                transactions.map((tx, idx) => {
                  const info = tx.transaction_info || {};
                  const payer = tx.payer_info || {};
                  const amount = info.transaction_amount?.value || '0.00';
                  const currency = info.transaction_amount?.currency_code || 'USD';
                  const fee = info.fee_amount?.value || '0.00';
                  const net = info.net_amount?.value || amount;

                  return (
                    <div
                      key={info.transaction_id || idx}
                      className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs font-sans"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-white">{info.transaction_id}</span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                            Status: {info.transaction_status || 'S'}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-950 text-emerald-400 border border-emerald-800">
                            {info.protection_eligibility || 'ELIGIBLE'}
                          </span>
                        </div>
                        <div className="text-slate-400 text-[11px]">
                          Customer: <strong className="text-slate-300">{payer.name || `${payer.payer_name?.given_name || ''} ${payer.payer_name?.surname || ''}`}</strong> · {payer.email_address}
                        </div>
                        <div className="text-[11px] font-mono text-slate-500">
                          Date: {info.transaction_initiation_date ? new Date(info.transaction_initiation_date).toLocaleString() : 'N/A'}
                        </div>
                      </div>

                      <div className="text-right space-y-0.5">
                        <div className="font-bold text-white text-sm">
                          ${amount} <span className="font-mono text-[11px] text-slate-400">{currency}</span>
                        </div>
                        <div className="text-[11px] font-mono text-slate-400">
                          Fee: <span className="text-amber-400">${fee}</span> · Net: <span className="text-emerald-400">${net}</span>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: SANDBOX GUIDE & CREDENTIALS CONFIGURATION */}
      {activeSubTab === 'setup' && (
        <div className="space-y-6 max-w-4xl">
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              Official PayPal Sandbox Integration Setup
            </h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              ResolveIQ communicates securely with the PayPal REST Sandbox API using OAuth 2.0 Client Credentials.
              Credentials stay strictly on the backend and are never exposed to React or the client browser.
            </p>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3 text-xs font-mono text-slate-300">
              <div className="font-bold text-sky-400 font-sans text-xs">
                To connect your live PayPal Developer Sandbox account:
              </div>
              <ol className="list-decimal list-inside space-y-2 text-slate-400">
                <li>Create or login to a PayPal Developer account at <a href="https://developer.paypal.com" target="_blank" rel="noreferrer" className="text-sky-400 underline">developer.paypal.com</a>.</li>
                <li>Go to <strong>Apps &amp; Credentials</strong> and create a REST API App in <strong>Sandbox</strong> mode.</li>
                <li>Create or edit your local <code className="text-amber-300">.env</code> file in the project root:</li>
              </ol>
              <pre className="p-3 rounded-lg bg-slate-900 text-emerald-300 text-[11px] overflow-x-auto">
{`PAYPAL_CLIENT_ID=your_sandbox_client_id_here
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret_here
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com`}
              </pre>
              <p className="text-[11px] text-slate-400 font-sans">
                After saving <code className="text-amber-300">.env</code>, click the <strong>Refresh Data</strong> button above to immediately initiate OAuth authentication and retrieve your sandbox disputes!
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Direct PayPal Evidence Submission Drawer / Modal */}
      {submittingDispute && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Send className="w-4 h-4 text-sky-400" />
                  Submit Evidence to PayPal
                </h3>
                <span className="text-[11px] font-mono text-slate-400">
                  Dispute: {submittingDispute.dispute_id} (${submittingDispute.dispute_amount?.value || '0.00'})
                </span>
              </div>
              <button
                onClick={() => setSubmittingDispute(null)}
                className="text-slate-500 hover:text-white text-xs font-mono p-1"
              >
                ✕ Close
              </button>
            </div>

            {submissionSuccess ? (
              <div className="p-4 rounded-xl bg-emerald-950/50 border border-emerald-800 text-xs text-emerald-300 space-y-3">
                <div className="flex items-center gap-2 font-bold text-sm text-emerald-400">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  <span>Evidence Successfully Submitted!</span>
                </div>
                <p className="text-slate-300">{submissionSuccess.message}</p>
                <div className="p-3 bg-slate-950 rounded-lg font-mono text-[11px] space-y-1">
                  <div>PayPal-Debug-Id: <span className="text-sky-300">{submissionSuccess.submission_debug_id}</span></div>
                  <div>Evidence Type: <span className="text-slate-200">{submissionSuccess.evidence_type}</span></div>
                  <div>Timestamp: <span className="text-slate-400">{new Date(submissionSuccess.submitted_at).toLocaleString()}</span></div>
                </div>
                <button
                  onClick={() => setSubmittingDispute(null)}
                  className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-bold text-xs"
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmitEvidence} className="space-y-4 text-xs">
                {submissionError && (
                  <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                    <span>{submissionError}</span>
                  </div>
                )}

                <div>
                  <label className="block font-medium text-slate-400 mb-1">
                    Official Evidence Type
                  </label>
                  <select
                    value={evidenceType}
                    onChange={(e) => setEvidenceType(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-200 focus:outline-none focus:border-sky-500"
                  >
                    <option value="PROOF_OF_FULFILLMENT">PROOF_OF_FULFILLMENT (Tracking / Carrier Delivery)</option>
                    <option value="PROOF_OF_DELIVERY">PROOF_OF_DELIVERY (Signature / Porch Confirmation)</option>
                    <option value="PROOF_OF_REFUND">PROOF_OF_REFUND (Prior Refund Transaction Proof)</option>
                    <option value="MERCHANT_TERMS_AND_CONDITIONS">MERCHANT_TERMS_AND_CONDITIONS (Policy / Return Agreement)</option>
                    <option value="ADDITIONAL_INFORMATION_OF_ITEM">ADDITIONAL_INFORMATION_OF_ITEM (Specs / Photos)</option>
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-medium text-slate-400 mb-1">Carrier Name</label>
                    <select
                      value={carrierName}
                      onChange={(e) => setCarrierName(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-200 focus:outline-none focus:border-sky-500"
                    >
                      <option value="FEDEX">FedEx</option>
                      <option value="UPS">UPS</option>
                      <option value="USPS">USPS</option>
                      <option value="DHL">DHL Express</option>
                      <option value="OTHER">Other Carrier</option>
                    </select>
                  </div>

                  <div>
                    <label className="block font-medium text-slate-400 mb-1">Tracking Number</label>
                    <input
                      type="text"
                      value={trackingNumber}
                      onChange={(e) => setTrackingNumber(e.target.value)}
                      placeholder="e.g. 789456123012"
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                    />
                  </div>
                </div>

                <div>
                  <label className="block font-medium text-slate-400 mb-1">
                    Merchant Notes &amp; Factual Statements
                  </label>
                  <textarea
                    rows={3}
                    value={submissionNotes}
                    onChange={(e) => setSubmissionNotes(e.target.value)}
                    placeholder="Describe delivery timeline, signature, and order fulfillment..."
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-200 focus:outline-none focus:border-sky-500 font-sans"
                  />
                </div>

                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setSubmittingDispute(null)}
                    className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submissionLoading}
                    className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs uppercase tracking-wider shadow flex items-center gap-2 disabled:opacity-50"
                  >
                    {submissionLoading ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Submitting…</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-3.5 h-3.5" />
                        <span>Submit to PayPal</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
