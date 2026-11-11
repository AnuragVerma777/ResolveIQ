import React, { createContext, useContext, useState, useCallback } from 'react';
import {
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Info,
  X,
  HelpCircle,
} from 'lucide-react';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [confirmDialog, setConfirmDialog] = useState(null);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(({ type = 'info', title, message, duration = 4000 }) => {
    const id = Date.now() + Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, title, message }]);

    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }
    return id;
  }, [removeToast]);

  const toast = {
    success: (message, title = 'Success') => showToast({ type: 'success', title, message }),
    error: (message, title = 'Action Failed') => showToast({ type: 'error', title, message, duration: 6000 }),
    warning: (message, title = 'Notice') => showToast({ type: 'warning', title, message, duration: 5000 }),
    info: (message, title = 'Information') => showToast({ type: 'info', title, message }),
  };

  const confirmAction = useCallback(
    ({
      title = 'Confirm Action',
      message = 'Are you sure you want to proceed?',
      confirmText = 'Confirm',
      cancelText = 'Cancel',
      variant = 'primary', // 'primary' | 'danger' | 'warning'
      onConfirm,
    }) => {
      setConfirmDialog({
        title,
        message,
        confirmText,
        cancelText,
        variant,
        onConfirm: async () => {
          setConfirmDialog(null);
          if (onConfirm) await onConfirm();
        },
        onCancel: () => setConfirmDialog(null),
      });
    },
    []
  );

  return (
    <ToastContext.Provider value={{ showToast, toast, confirmAction }}>
      {children}

      {/* Floating Toasts Container */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-md w-full px-4 pointer-events-none">
        {toasts.map((t) => {
          const typeStyles = {
            success: {
              border: 'border-emerald-700/60',
              bg: 'bg-slate-900/95 shadow-emerald-500/10',
              icon: <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />,
              titleColor: 'text-emerald-300',
            },
            error: {
              border: 'border-rose-700/60',
              bg: 'bg-slate-900/95 shadow-rose-500/10',
              icon: <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />,
              titleColor: 'text-rose-300',
            },
            warning: {
              border: 'border-amber-700/60',
              bg: 'bg-slate-900/95 shadow-amber-500/10',
              icon: <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />,
              titleColor: 'text-amber-300',
            },
            info: {
              border: 'border-sky-700/60',
              bg: 'bg-slate-900/95 shadow-sky-500/10',
              icon: <Info className="w-5 h-5 text-sky-400 shrink-0 mt-0.5" />,
              titleColor: 'text-sky-300',
            },
          }[t.type] || {
            border: 'border-slate-700',
            bg: 'bg-slate-900/95 shadow-slate-500/10',
            icon: <Info className="w-5 h-5 text-slate-400 shrink-0 mt-0.5" />,
            titleColor: 'text-white',
          };

          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-3 p-4 rounded-2xl border ${typeStyles.border} ${typeStyles.bg} shadow-2xl backdrop-blur-md transition-all animate-in slide-in-from-bottom-5 duration-200`}
            >
              {typeStyles.icon}
              <div className="flex-1 min-w-0">
                {t.title && (
                  <h4 className={`text-xs font-bold uppercase tracking-wider ${typeStyles.titleColor}`}>
                    {t.title}
                  </h4>
                )}
                <p className="text-xs text-slate-200 mt-0.5 leading-relaxed break-words">
                  {t.message}
                </p>
              </div>
              <button
                onClick={() => removeToast(t.id)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
                title="Dismiss"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>

      {/* Confirmation Modal */}
      {confirmDialog && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-5 animate-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div
                className={`p-3 rounded-2xl border ${
                  confirmDialog.variant === 'danger'
                    ? 'bg-rose-950/60 border-rose-800 text-rose-400'
                    : confirmDialog.variant === 'warning'
                    ? 'bg-amber-950/60 border-amber-800 text-amber-400'
                    : 'bg-sky-950/60 border-sky-800 text-sky-400'
                }`}
              >
                {confirmDialog.variant === 'danger' ? (
                  <AlertCircle className="w-6 h-6" />
                ) : confirmDialog.variant === 'warning' ? (
                  <AlertTriangle className="w-6 h-6" />
                ) : (
                  <HelpCircle className="w-6 h-6" />
                )}
              </div>
              <div>
                <h3 className="text-base font-bold text-white tracking-tight">
                  {confirmDialog.title}
                </h3>
                <span className="text-[11px] font-mono text-slate-400">
                  Merchant Confirmation Required
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              {confirmDialog.message}
            </p>

            <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-800">
              <button
                onClick={confirmDialog.onCancel}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition-colors"
              >
                {confirmDialog.cancelText}
              </button>
              <button
                onClick={confirmDialog.onConfirm}
                className={`px-5 py-2 rounded-xl text-xs font-bold text-white uppercase tracking-wider shadow-lg transition-all ${
                  confirmDialog.variant === 'danger'
                    ? 'bg-rose-600 hover:bg-rose-500 shadow-rose-600/20'
                    : confirmDialog.variant === 'warning'
                    ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-600/20'
                    : 'bg-sky-600 hover:bg-sky-500 shadow-sky-600/20'
                }`}
              >
                {confirmDialog.confirmText}
              </button>
            </div>
          </div>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    // Fallback if rendered outside provider so it never crashes
    return {
      showToast: ({ message }) => console.log(message),
      toast: {
        success: (msg) => console.log('SUCCESS:', msg),
        error: (msg) => console.error('ERROR:', msg),
        warning: (msg) => console.warn('WARN:', msg),
        info: (msg) => console.log('INFO:', msg),
      },
      confirmAction: ({ onConfirm }) => {
        if (window.confirm('Confirm action?')) onConfirm?.();
      },
    };
  }
  return context;
}
