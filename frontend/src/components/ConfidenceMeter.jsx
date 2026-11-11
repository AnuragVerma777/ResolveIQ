import React from 'react';
import { ShieldCheck, ShieldAlert, AlertCircle, Info } from 'lucide-react';

export default function ConfidenceMeter({ confidence, disclaimer }) {
  if (!confidence) return null;

  const { level, score, explanation } = confidence;
  const pct = Math.round((score || 0) * 100);

  const getTheme = () => {
    switch (level) {
      case 'HIGH':
        return {
          bg: 'bg-emerald-950/60',
          border: 'border-emerald-500/40',
          text: 'text-emerald-400',
          bar: 'bg-gradient-to-r from-emerald-600 to-teal-400',
          icon: ShieldCheck,
        };
      case 'MEDIUM':
        return {
          bg: 'bg-amber-950/60',
          border: 'border-amber-500/40',
          text: 'text-amber-400',
          bar: 'bg-gradient-to-r from-amber-600 to-yellow-400',
          icon: ShieldAlert,
        };
      default:
        return {
          bg: 'bg-slate-900/80',
          border: 'border-slate-700',
          text: 'text-slate-400',
          bar: 'bg-slate-500',
          icon: AlertCircle,
        };
    }
  };

  const theme = getTheme();
  const IconComponent = theme.icon;

  return (
    <div className={`rounded-xl border ${theme.border} ${theme.bg} p-5 shadow-lg backdrop-blur-sm transition-all`}>
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-center gap-2.5">
          <div className={`p-2 rounded-lg ${theme.bg} border ${theme.border}`}>
            <IconComponent className={`w-5 h-5 ${theme.text}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
                Classification Confidence
              </span>
              <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${theme.text} bg-slate-900/90 border border-slate-700`}>
                {level}
              </span>
            </div>
            <div className="text-2xl font-black tracking-tight text-white mt-0.5">
              {pct}%
            </div>
          </div>
        </div>

        <div className="text-right max-w-xs">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/90 border border-slate-800 text-[11px] text-slate-400">
            <Info className="w-3.5 h-3.5 text-sky-400 shrink-0" />
            <span>Not a win probability</span>
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-slate-900 rounded-full h-2.5 overflow-hidden border border-slate-800/80 mb-3">
        <div
          className={`h-full rounded-full transition-all duration-700 ${theme.bar}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Explanation */}
      {explanation && (
        <p className="text-xs text-slate-300 leading-relaxed font-normal bg-slate-950/40 p-2.5 rounded-lg border border-slate-800/60">
          <strong className="text-slate-200">Assessment rationale:</strong> {explanation}
        </p>
      )}

      {/* Mandatory Disclaimer */}
      {disclaimer && (
        <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-start gap-1.5 text-[11px] text-slate-400 italic">
          <span>⚠️ {disclaimer}</span>
        </div>
      )}
    </div>
  );
}
