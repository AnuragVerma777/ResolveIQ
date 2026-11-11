import React from 'react';
import {
  X,
  CheckCircle2,
  ShieldCheck,
  Scale,
  Sparkles,
  Zap,
  Lock,
  ArrowRight,
  ExternalLink,
  Award,
  Layers,
  FileText,
  AlertTriangle,
} from 'lucide-react';

export default function JudgeEvaluationGuideModal({ isOpen, onClose, onLaunchDemo }) {
  if (!isOpen) return null;

  const EVALUATION_STEPS = [
    {
      step: '01',
      title: 'Dispute Ingestion & Real Context',
      desc: 'Inspects real transaction amounts, customer allegations, and PayPal deadlines. Seamlessly operates in Live Sandbox or labelled Demo mode.',
    },
    {
      step: '02',
      title: 'Document Intelligence & Extraction',
      desc: 'Multi-format parser (PyMuPDF, python-docx, OCR) extracts Order IDs, tracking numbers, carriers, dates, and amounts without hallucination.',
    },
    {
      step: '03',
      title: 'Evidence-to-Claim Matrix',
      desc: 'Decomposes customer allegations into adjudicable claims and cross-references documentary proof with strict status tags (Supported, Partial, Contradictory).',
    },
    {
      step: '04',
      title: 'Explainable Completeness Score',
      desc: 'Transparent 0–100 rubric evaluating documented evidence coverage, core fulfillment proof, and data consistency. Never an invented "win probability".',
    },
    {
      step: '05',
      title: 'Evidence-Backed Rebuttal Synthesis',
      desc: 'Generates formal legal rebuttals where every factual claim cites an exact document reference. Unknown claims are flagged for merchant input.',
    },
    {
      step: '06',
      title: 'Mandatory Merchant Approval Gate',
      desc: 'Preflight checks enforce claim validity, block expired disputes, and require explicit merchant sign-off before dispatch.',
    },
    {
      step: '07',
      title: 'PayPal API Dispatch & Zapier Event Bus',
      desc: 'Submits evidence via PayPal REST API with PayPal-Debug-Id tracking and fires real-time automation webhooks to Zapier.',
    },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-4xl w-full max-h-[90vh] flex flex-col shadow-2xl overflow-hidden my-auto">
        {/* Modal Header */}
        <div className="px-8 py-6 border-b border-slate-800 bg-slate-950 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-sky-500/20 border border-sky-400/30">
              <Award className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-black text-white tracking-tight">
                  Resolve<span className="text-sky-400">IQ</span> Hackathon Judge Guide
                </h3>
                <span className="px-2 py-0.5 rounded-full bg-sky-950 text-sky-300 border border-sky-800 text-[10px] font-mono font-bold">
                  EVALUATION BRIEF
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Autonomous PayPal Dispute Intelligence &amp; Evidence Grounding Platform
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-8 overflow-y-auto space-y-8 flex-1">
          {/* Executive Overview */}
          <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-950 to-slate-900 border border-slate-800 space-y-3">
            <h4 className="text-xs font-mono uppercase font-bold text-sky-400 tracking-wider flex items-center gap-2">
              <Sparkles className="w-4 h-4" />
              The Core Problem &amp; Innovation
            </h4>
            <p className="text-sm text-slate-200 leading-relaxed">
              Merchants lose billions annually to friendly fraud and chargebacks because compiling evidence across
              invoices, carriers, and CRMs is slow and disjointed. Existing generic LLM bots hallucinate delivery facts
              and submit unverified letters that fail PayPal rules.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
              <div className="p-3 bg-slate-950 rounded-xl border border-slate-800/80">
                <div className="text-xs font-bold text-emerald-400 flex items-center gap-1.5 mb-1">
                  <ShieldCheck className="w-4 h-4" />
                  <span>Zero Hallucination</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Every factual claim cites verbatim document excerpts. Unknown claims are flagged as pending merchant input.
                </p>
              </div>
              <div className="p-3 bg-slate-950 rounded-xl border border-slate-800/80">
                <div className="text-xs font-bold text-sky-400 flex items-center gap-1.5 mb-1">
                  <Scale className="w-4 h-4" />
                  <span>Evidence Matrix</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Calculates an explainable 0–100 completeness score based on documented coverage, not fake win probabilities.
                </p>
              </div>
              <div className="p-3 bg-slate-950 rounded-xl border border-slate-800/80">
                <div className="text-xs font-bold text-indigo-400 flex items-center gap-1.5 mb-1">
                  <Lock className="w-4 h-4" />
                  <span>Human-in-the-Loop</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  No automatic API submission. Merchant review and explicit approval are strictly mandatory.
                </p>
              </div>
            </div>
          </div>

          {/* 7-Step Evaluation Walkthrough */}
          <div className="space-y-4">
            <h4 className="text-xs font-mono uppercase font-bold text-slate-300 tracking-wider">
              Recommended Evaluation Flow (7-Step Journey)
            </h4>
            <div className="space-y-2.5">
              {EVALUATION_STEPS.map((item) => (
                <div
                  key={item.step}
                  className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 flex items-start gap-4 hover:border-slate-700 transition-colors"
                >
                  <span className="px-2 py-1 rounded-md bg-sky-950 text-sky-400 font-mono text-xs font-bold shrink-0 border border-sky-800/50">
                    {item.step}
                  </span>
                  <div>
                    <h5 className="text-xs font-bold text-white mb-0.5">{item.title}</h5>
                    <p className="text-xs text-slate-400 leading-relaxed">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Sandbox & Demo Integrity Note */}
          <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-800/60 flex items-start gap-3 text-xs text-amber-200/90">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <strong className="text-amber-300 block">Strict Data Provenance &amp; Demo Mode Integrity</strong>
              <p className="text-slate-300 text-[11px] leading-relaxed">
                When live PayPal credentials are not configured in your environment, ResolveIQ operates in safe
                <strong> Demo Mode</strong>. Every simulated record is explicitly tagged <span className="font-mono text-amber-400">DEMO RECORD</span>.
                Real document uploads, OCR extractions, and Gemini reasoning execute live in both modes.
              </p>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-8 py-5 border-t border-slate-800 bg-slate-950 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-xs text-slate-400 flex items-center gap-2">
            <span>FastAPI OpenAPI Specs:</span>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="text-sky-400 hover:text-sky-300 font-mono flex items-center gap-1"
            >
              <span>/docs</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition-colors flex-1 sm:flex-none"
            >
              Close
            </button>
            <button
              onClick={() => {
                onClose();
                onLaunchDemo();
              }}
              className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-sky-500 via-blue-600 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-xs font-bold text-white uppercase tracking-wider flex items-center justify-center gap-2 shadow-lg shadow-sky-500/25 transition-all flex-1 sm:flex-none"
            >
              <span>Launch Demo Case</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
