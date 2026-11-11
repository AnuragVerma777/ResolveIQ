import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  FileText,
  Activity,
  Layers,
  Sparkles,
  ExternalLink,
  BookOpen,
  Lock,
  Cpu,
  Scale,
  CreditCard,
  RefreshCw,
  Zap,
  Award,
} from 'lucide-react';
import ResolutionWorkflow from './components/ResolutionWorkflow';
import EvidenceMatrixWorkspace from './components/EvidenceMatrixWorkspace';
import ResolutionStudio from './components/ResolutionStudio';
import DisputeInvestigation from './components/DisputeInvestigation';
import DocumentVault from './components/DocumentVault';
import PayPalLiveHub from './components/PayPalLiveHub';
import AutomationSettings from './components/AutomationSettings';
import JudgeEvaluationGuideModal from './components/JudgeEvaluationGuideModal';
import JudgeBriefingBanner from './components/JudgeBriefingBanner';
import { fetchHealth, fetchPayPalStatus, seedSampleEvidence } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState('workflow');
  const [health, setHealth] = useState(null);
  const [paypalStatus, setPaypalStatus] = useState(null);
  const [activeDispute, setActiveDispute] = useState({ dispute_id: 'PP-D-849201' });
  const [syncing, setSyncing] = useState(false);
  const [showJudgeGuide, setShowJudgeGuide] = useState(false);

  const refreshSystemStatus = async () => {
    setSyncing(true);
    try {
      const [h, pp] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchPayPalStatus().catch(() => null),
      ]);
      setHealth(h);
      setPaypalStatus(pp);
    } catch (err) {
      console.error('Status refresh failed', err);
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    refreshSystemStatus();
  }, []);

  const handleSelectDispute = (dispute) => {
    setActiveDispute(dispute);
    setActiveTab('workflow');
  };

  const handleSelectCaseId = (caseId) => {
    setActiveDispute({ dispute_id: caseId });
    setActiveTab('workflow');
  };

  const launchJudgeDemo = async () => {
    const targetId = 'PP-D-849201';
    setActiveDispute({ dispute_id: targetId });
    setActiveTab('workflow');
    try {
      await seedSampleEvidence(targetId).catch(() => null);
    } catch (err) {
      console.error('Auto seed error', err);
    }
  };

  const isPayPalLive = paypalStatus?.connected && paypalStatus?.mode === 'sandbox';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-sky-500 selection:text-white overflow-x-hidden w-full">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-40 bg-slate-950/90 backdrop-blur-md border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-2 sm:gap-4">
          {/* Logo & Brand */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-sky-500 via-blue-600 to-indigo-700 flex items-center justify-center shadow-lg shadow-sky-500/20 border border-sky-400/30">
              <span className="font-black text-white text-base tracking-tighter">RQ</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-extrabold text-base tracking-tight text-white">
                  Resolve<span className="text-sky-400">IQ</span>
                </h1>
                <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[10px] font-mono font-semibold text-slate-300 border border-slate-700">
                  v3.0 · Judge Edition
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium hidden md:block">
                Autonomous PayPal Dispute Intelligence &amp; Evidence Grounding
              </p>
            </div>
          </div>

          {/* Navigation Tabs - Horizontally scrollable on mobile */}
          <nav className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-xl border border-slate-800 overflow-x-auto min-w-0 flex-1 scrollbar-none flex-nowrap mx-1 sm:mx-2">
            <button
              onClick={() => setActiveTab('workflow')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                activeTab === 'workflow'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Workflow</span>
            </button>
            <button
              onClick={() => setActiveTab('paypal')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                activeTab === 'paypal'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <CreditCard className="w-3.5 h-3.5" />
              <span>PayPal Hub</span>
            </button>
            <button
              onClick={() => setActiveTab('matrix')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                activeTab === 'matrix'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Scale className="w-3.5 h-3.5" />
              <span>Evidence Matrix</span>
            </button>
            <button
              onClick={() => setActiveTab('resolution')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                activeTab === 'resolution'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Studio</span>
            </button>
            <button
              onClick={() => setActiveTab('investigation')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                activeTab === 'investigation'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Intake</span>
            </button>
            <button
              onClick={() => setActiveTab('vault')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                activeTab === 'vault'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Vault</span>
            </button>
            <button
              onClick={() => setActiveTab('automation')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                activeTab === 'automation'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Zapier</span>
            </button>
            <button
              onClick={() => setActiveTab('docs')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                activeTab === 'docs'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>API</span>
            </button>
          </nav>

          {/* Actions & Status Pill */}
          <div className="flex items-center gap-2.5 shrink-0">
            {/* Judge Guide Action Button */}
            <button
              onClick={() => setShowJudgeGuide(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-sky-500 via-blue-600 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-xs font-bold text-white shadow-md shadow-sky-500/20 border border-sky-400/30 transition-all"
              title="Open Hackathon Evaluation Guide & 12-Step Walkthrough"
            >
              <Award className="w-3.5 h-3.5 text-sky-200" />
              <span className="hidden sm:inline">Judge Guide</span>
            </button>

            {/* PayPal Gateway Status Pill */}
            <div
              className={`hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-mono ${
                isPayPalLive
                  ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
                  : 'bg-amber-950/60 border-amber-800 text-amber-300'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  isPayPalLive ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
                }`}
              />
              <span className="text-[11px] font-semibold">
                {isPayPalLive ? 'Sandbox Live' : 'Demo Mode'}
              </span>
            </div>

            {/* Refresh Status Action */}
            <button
              onClick={refreshSystemStatus}
              disabled={syncing}
              className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition-colors"
              title="Refresh PayPal & System Health"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin text-sky-400' : ''}`} />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 py-6 w-full">
        {/* Judge / Executive Briefing Banner */}
        <JudgeBriefingBanner
          onLaunchDemo={launchJudgeDemo}
          onOpenGuide={() => setShowJudgeGuide(true)}
          activeCaseId={activeDispute?.dispute_id}
          onSelectCase={handleSelectCaseId}
        />

        {activeTab === 'workflow' && (
          <ResolutionWorkflow activeDispute={activeDispute} />
        )}
        {activeTab === 'paypal' && (
          <PayPalLiveHub onSelectDispute={handleSelectDispute} />
        )}
        {activeTab === 'matrix' && (
          <EvidenceMatrixWorkspace importedDispute={activeDispute} />
        )}
        {activeTab === 'resolution' && (
          <ResolutionStudio activeDisputeId={activeDispute?.dispute_id} />
        )}
        {activeTab === 'investigation' && (
          <DisputeInvestigation initialDisputeId={activeDispute?.dispute_id} />
        )}
        {activeTab === 'vault' && <DocumentVault />}
        {activeTab === 'automation' && <AutomationSettings />}
        {activeTab === 'docs' && (
          <div className="max-w-4xl mx-auto bg-slate-900/90 border border-slate-800 rounded-3xl p-8 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
              <div>
                <h2 className="text-xl font-bold text-white">ResolveIQ Production API Specifications</h2>
                <p className="text-xs text-slate-400 mt-1">
                  FastAPI OpenAPI documentation, PayPal REST integration, and Zapier Webhooks automation endpoints.
                </p>
              </div>
              <a
                href="/docs"
                target="_blank"
                rel="noreferrer"
                className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-xs font-semibold text-white flex items-center gap-2 shadow"
              >
                <span>Interactive Swagger UI</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-slate-200">Pre-Flight &amp; Workflow Endpoints</h3>
              <div className="grid grid-cols-1 gap-2.5 font-mono text-xs">
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-emerald-400 font-bold">GET /api/disputes/{'{id}'}/preflight-check</span>
                  <span className="text-slate-400 font-sans text-[11px]">Verifies open status, valid deadline, permissions, and required evidence</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-sky-400 font-bold">GET /api/paypal/status</span>
                  <span className="text-slate-400 font-sans text-[11px]">OAuth status, token validity, and sandbox mode</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-emerald-400 font-bold">GET /api/paypal/disputes</span>
                  <span className="text-slate-400 font-sans text-[11px]">Lists customer disputes with sandbox/demo tags</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-blue-400 font-bold">GET /api/paypal/disputes/{'{id}'}</span>
                  <span className="text-slate-400 font-sans text-[11px]">Dispute details &amp; evidence requirements</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-purple-400 font-bold">POST /api/paypal/disputes/{'{id}'}/provide-evidence</span>
                  <span className="text-slate-400 font-sans text-[11px]">Submits tracking &amp; evidence to PayPal API</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-indigo-400 font-bold">POST /api/disputes/{'{id}'}/resolution/{'{resp_id}'}/submit</span>
                  <span className="text-slate-400 font-sans text-[11px]">Submits approved rebuttal with auto-harvested tracking</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-pink-400 font-bold">POST /api/disputes/{'{id}'}/seed-sample-evidence</span>
                  <span className="text-slate-400 font-sans text-[11px]">Seeds sample FedEx Proof &amp; Tax Invoice for judges</span>
                </div>
              </div>
            </div>

            <div className="space-y-4 pt-2">
              <h3 className="text-sm font-semibold text-slate-200">Zapier Automation Webhook Endpoints</h3>
              <div className="grid grid-cols-1 gap-2.5 font-mono text-xs">
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-amber-400 font-bold">GET /api/automation/settings</span>
                  <span className="text-slate-400 font-sans text-[11px]">Retrieves masked webhook URL, verification status, and enabled events</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-amber-400 font-bold">PUT /api/automation/settings</span>
                  <span className="text-slate-400 font-sans text-[11px]">Updates Zapier HTTPS Catch Hook URL, events, timeout and retries</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-emerald-400 font-bold">POST /api/automation/test</span>
                  <span className="text-slate-400 font-sans text-[11px]">Fires real test webhook; marks connection verified only on 2xx response</span>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-sky-400 font-bold">GET /api/automation/deliveries</span>
                  <span className="text-slate-400 font-sans text-[11px]">Historical delivery audit trail with latency, attempts, and payload inspection</span>
                </div>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs text-slate-300">
              <h4 className="font-semibold text-slate-200 flex items-center gap-2">
                <Lock className="w-3.5 h-3.5 text-emerald-400" />
                Safety &amp; Reliability Guarantees
              </h4>
              <ul className="list-disc list-inside space-y-1 text-slate-400">
                <li>No automatic submissions: Explicit merchant approval is strictly mandatory.</li>
                <li>Pre-flight verification blocks expired disputes, closed claims, or unauthorized actions.</li>
                <li>All factual statements cite actual documentary evidence; zero fabricated tracking or scans.</li>
                <li>Accidental duplicate submissions are detected and prevented via atomic mutex locks.</li>
                <li>API submission state is persistent in SQLite and recorded in the audit trail.</li>
              </ul>
            </div>
          </div>
        )}
      </main>

      {/* Judge Evaluation Guide Modal */}
      <JudgeEvaluationGuideModal
        isOpen={showJudgeGuide}
        onClose={() => setShowJudgeGuide(false)}
        onLaunchDemo={launchJudgeDemo}
      />

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-slate-950/60 py-4 px-6 text-center text-[11px] text-slate-500">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>ResolveIQ · Autonomous Dispute Intelligence &amp; Evidence Studio</span>
          <span className="italic text-slate-600">
            Advisory intelligence only · Merchant approval required prior to dispute submission
          </span>
        </div>
      </footer>
    </div>
  );
}
