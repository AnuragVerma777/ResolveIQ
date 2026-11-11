import React, { useState, useEffect } from 'react';
import { X, ExternalLink, Download, FileText, CheckCircle, AlertTriangle, Copy, Check } from 'lucide-react';
import ExtractedFieldsCard from './ExtractedFieldsCard';
import { getDocumentText, getDocumentPreviewUrl, getDocumentDownloadUrl } from '../api';

export default function DocumentDrawer({ doc: docProp, document: documentProp, onClose }) {
  const doc = docProp || documentProp;
  const [activeTab, setActiveTab] = useState('fields');
  const [rawText, setRawText] = useState(doc?.raw_text || '');
  const [loadingText, setLoadingText] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (doc && !rawText) {
      setLoadingText(true);
      getDocumentText(doc.id)
        .then(res => setRawText(res.text || ''))
        .catch(err => setRawText(`Failed to load text: ${err.message}`))
        .finally(() => setLoadingText(false));
    }
  }, [doc]);

  if (!doc) return null;

  const handleCopyText = () => {
    navigator.clipboard.writeText(rawText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isPdf = doc.filename?.toLowerCase().endsWith('.pdf') || doc.content_type?.includes('pdf');
  const isImage = /\.(png|jpg|jpeg|webp)$/i.test(doc.filename || '') || doc.content_type?.startsWith('image/');

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex justify-end transition-opacity animate-in fade-in duration-200">
      <div className="w-full max-w-2xl bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="p-2 bg-sky-950/70 border border-sky-800/60 rounded-lg text-sky-400 shrink-0">
              <FileText className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-slate-100 text-sm truncate" title={doc.filename}>
                {doc.filename}
              </h3>
              <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5">
                <span className="capitalize px-1.5 py-0.5 rounded bg-slate-800 text-[10px] font-mono text-slate-300">
                  {doc.doc_type || 'document'}
                </span>
                <span>•</span>
                <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                <span>•</span>
                <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                  doc.status === 'COMPLETED' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' :
                  doc.status === 'FAILED' ? 'bg-rose-950 text-rose-400 border border-rose-800/60' :
                  'bg-amber-950 text-amber-400 border border-amber-800/60'
                }`}>
                  {doc.status}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <a
              href={getDocumentDownloadUrl(doc.id)}
              target="_blank"
              rel="noreferrer"
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
              title="Download original file"
            >
              <Download className="w-4 h-4" />
            </a>
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab switcher */}
        <div className="flex items-center gap-1 px-6 pt-3 border-b border-slate-800 bg-slate-950/40 text-xs font-medium">
          <button
            onClick={() => setActiveTab('fields')}
            className={`px-4 py-2 border-b-2 font-semibold transition-colors ${
              activeTab === 'fields'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            Structured Intelligence
          </button>
          <button
            onClick={() => setActiveTab('text')}
            className={`px-4 py-2 border-b-2 font-semibold transition-colors ${
              activeTab === 'text'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            Extracted Text
          </button>
          <button
            onClick={() => setActiveTab('preview')}
            className={`px-4 py-2 border-b-2 font-semibold transition-colors ${
              activeTab === 'preview'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            File Preview
          </button>
        </div>

        {/* Content body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {activeTab === 'fields' && (
            <div>
              {doc.extracted_fields ? (
                <ExtractedFieldsCard fields={doc.extracted_fields} title="Intelligence Pipeline Extraction" />
              ) : (
                <div className="p-8 text-center text-slate-400 bg-slate-950/50 rounded-xl border border-slate-800">
                  <p className="text-sm">No structured fields extracted yet.</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'text' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Total Characters: {rawText.length}</span>
                <button
                  onClick={handleCopyText}
                  className="flex items-center gap-1 text-sky-400 hover:text-sky-300 font-medium"
                >
                  {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? 'Copied' : 'Copy All Text'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-xs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap select-all max-h-[550px] overflow-y-auto">
                {loadingText ? 'Loading text from server…' : rawText || '(No text extracted)'}
              </pre>
            </div>
          )}

          {activeTab === 'preview' && (
            <div className="h-full flex flex-col">
              {isPdf ? (
                <iframe
                  src={getDocumentPreviewUrl(doc.id)}
                  className="w-full h-[600px] rounded-xl border border-slate-800 bg-slate-950"
                  title="PDF Document Preview"
                />
              ) : isImage ? (
                <div className="flex justify-center p-4 bg-slate-950 rounded-xl border border-slate-800">
                  <img
                    src={getDocumentPreviewUrl(doc.id)}
                    alt="Document preview"
                    className="max-h-[550px] object-contain rounded-lg"
                  />
                </div>
              ) : (
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between text-xs text-slate-400 pb-2 border-b border-slate-800/80">
                    <span className="font-mono text-[11px] text-sky-400">Plaintext Document Content</span>
                    <button
                      onClick={handleCopyText}
                      className="flex items-center gap-1 text-sky-400 hover:text-sky-300 font-medium"
                    >
                      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copied ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                  <pre className="text-xs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap select-all max-h-[500px] overflow-y-auto">
                    {loadingText ? 'Loading text from server…' : rawText || '(No content available)'}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
