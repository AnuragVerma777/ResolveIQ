import React, { useState } from 'react';
import {
  Sparkles,
  ShieldCheck,
  Scale,
  Lock,
  ArrowRight,
  BookOpen,
  ChevronUp,
  ChevronDown,
  Layers,
  Award,
} from 'lucide-react';

export default function JudgeBriefingBanner({ onLaunchDemo, onOpenGuide, activeCaseId, onSelectCase }) {
  const [collapsed, setCollapsed] = useState(false);

  const DEMO_CASES = [
    { id: 'PP-D-849201', label: 'Case 1: Item Not Received', amount: '$189.50', tag: 'INR' },
    { id: 'PP-D-910482', label: 'Case 2: Significantly Not As Described', amount: '$450.00', tag: 'SNAD' },
    { id: 'PP-D-739104', label: 'Case 3: Unauthorized Transaction', amount: '$75.25', tag: 'Fraud' },
    { id: 'PP-D-628405', label: 'Case 4: Duplicate Charge', amount: '$120.00', tag: 'Duplicate' },
    { id: 'PP-D-517392', label: 'Case 5: Refund / Credit Claim', amount: '$95.00', tag: 'Refund' },
  ];

  if (collapsed) {
    return (
      <div className="mb-6 px-4 py-2.5 bg-slate-900/90 border border-slate-800 rounded-2xl flex items-center justify-between text-xs backdrop-blur-md">
        <div className="flex items-center gap-2">
          <Award className="w-4 h-4 text-sky-400" />
          <span className="font-bold text-white">Hackathon Evaluation Briefing</span>
          <span className="text-slate-500">•</span>
          <span className="text-slate-400 hidden sm:inline">
            Autonomous PayPal Dispute Intelligence &amp; Evidence Grounding Engine
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onOpenGuide}
            className="px-2.5 py-1 rounded-lg bg-sky-950/60 border border-sky-800 text-sky-300 font-semibold hover:bg-sky-900/60 transition-colors"
          >
            Open Guide
          </button>
          <button
            onClick={() => setCollapsed(false)}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            title="Expand briefing"
          >
            <ChevronDown className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-6 relative overflow-hidden bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 border border-slate-800 rounded-3xl p-6 shadow-xl backdrop-blur-md">
      {/* Background Glow */}
      <div className="absolute -top-24 -right-24 w-72 h-72 bg-sky-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-24 -left-24 w-72 h-72 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="relative z-10 space-y-4">
        {/* Header row */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-sky-500/20 border border-sky-400/30 flex items-center justify-center text-sky-400">
              <Award className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-sky-400">
                  Hackathon Judge Experience
                </span>
                <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px] font-mono font-bold">
                  JUDGE-READY
                </span>
              </div>
              <h2 className="text-lg font-black text-white tracking-tight mt-0.5">
                ResolveIQ · Autonomous PayPal Dispute Intelligence
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onOpenGuide}
              className="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 flex items-center gap-1.5 transition-colors shadow-sm"
            >
              <BookOpen className="w-3.5 h-3.5 text-sky-400" />
              <span>Evaluation Rubric</span>
            </button>
            <button
              onClick={() => setCollapsed(true)}
              className="p-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
              title="Minimize banner"
            >
              <ChevronUp className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Value Proposition Description */}
        <p className="text-xs text-slate-300 leading-relaxed max-w-4xl">
          ResolveIQ protects merchant revenue against invalid chargebacks by converting raw shipping receipts, delivery scans,
          and invoices into <strong>structured proof</strong>, detecting chronological and monetary contradictions, and drafting
          <strong> audit-backed legal rebuttals</strong> with strict zero-hallucination citations and mandatory human sign-off.
        </p>

        {/* 3 Pillars */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
          <div className="p-3 bg-slate-950/70 border border-slate-800/90 rounded-2xl flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-xs font-bold text-white">Grounded Citations</h4>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Every factual claim is verified against verbatim document text.
              </p>
            </div>
          </div>

          <div className="p-3 bg-slate-950/70 border border-slate-800/90 rounded-2xl flex items-start gap-2.5">
            <Scale className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-xs font-bold text-white">Explainable Completeness</h4>
              <p className="text-[11px] text-slate-400 mt-0.5">
                0–100 coverage score based on actual evidence, not invented win probability.
              </p>
            </div>
          </div>

          <div className="p-3 bg-slate-950/70 border border-slate-800/90 rounded-2xl flex items-start gap-2.5">
            <Lock className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-xs font-bold text-white">Approval Gate</h4>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Strict merchant review gate prevents accidental or automated submissions.
              </p>
            </div>
          </div>
        </div>

        {/* CTA & Case Selector Row */}
        <div className="pt-2 border-t border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-mono text-slate-400 font-semibold uppercase">
              Select Demo Case:
            </span>
            <div className="flex items-center gap-1.5 flex-wrap">
              {DEMO_CASES.map((c) => (
                <button
                  key={c.id}
                  onClick={() => onSelectCase(c.id)}
                  className={`px-3 py-1.5 rounded-lg text-[11px] font-mono font-semibold transition-all border ${
                    activeCaseId === c.id
                      ? 'bg-sky-600/30 border-sky-400 text-sky-200 shadow-sm'
                      : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                  }`}
                >
                  <span className="font-sans mr-1">{c.label}</span>
                  <span className="text-[10px] px-1 rounded bg-slate-800 text-slate-300">{c.amount}</span>
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={onLaunchDemo}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-sky-500 via-blue-600 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-xs font-bold text-white uppercase tracking-wider flex items-center justify-center gap-2 shadow-lg shadow-sky-500/25 transition-all shrink-0"
          >
            <Sparkles className="w-4 h-4 text-sky-200" />
            <span>Launch 1-Click Interactive Demo</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
