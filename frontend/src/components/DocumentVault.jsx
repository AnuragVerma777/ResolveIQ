import React, { useState, useEffect } from 'react';
import { FileText, UploadCloud, Eye, Download, Trash2, RefreshCw, CheckCircle2, AlertCircle, Hash, Truck, DollarSign } from 'lucide-react';
import { listDocuments, uploadDocument, deleteDocument } from '../api';
import { useToast } from '../context/ToastContext';
import DocumentDrawer from './DocumentDrawer';
import ExtractedFieldsCard from './ExtractedFieldsCard';

export default function DocumentVault() {
  const { toast, confirmAction } = useToast();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [filterDispute, setFilterDispute] = useState('');

  const loadDocs = async () => {
    setLoading(true);
    try {
      const data = await listDocuments(filterDispute || null);
      setDocuments(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
  }, [filterDispute]);

  const handleFileUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    setUploading(true);
    setUploadError(null);

    try {
      for (const file of files) {
        await uploadDocument(file, filterDispute || null, 'other');
      }
      await loadDocs();
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleDelete = (docId) => {
    confirmAction({
      title: 'Delete Document from Vault?',
      message: 'This document and its extracted structured intelligence will be permanently removed from disk and database.',
      confirmText: 'Delete Document',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteDocument(docId);
          await loadDocs();
          if (selectedDoc?.id === docId) setSelectedDoc(null);
          toast.success('Document deleted successfully from vault.', 'Deleted');
        } catch (err) {
          toast.error(`Delete failed: ${err.message}`);
        }
      },
    });
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-md backdrop-blur-md">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <FileText className="w-5 h-5 text-sky-400" />
            Document Intelligence Vault
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Secure multi-format document storage, PyMuPDF PDF parsing, python-docx extractor, and Gemini OCR.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="text"
            placeholder="Filter by Dispute ID..."
            value={filterDispute}
            onChange={(e) => setFilterDispute(e.target.value)}
            className="px-3 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500 w-48"
          />
          <button
            onClick={loadDocs}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Upload Banner */}
      <div className="relative border-2 border-dashed border-slate-800 hover:border-slate-700 bg-slate-900/40 rounded-2xl p-8 text-center transition-all">
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.csv,.md,.png,.jpg,.jpeg,.webp"
          onChange={handleFileUpload}
          disabled={uploading}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />
        <UploadCloud className="w-10 h-10 text-sky-400 mx-auto mb-2" />
        <h4 className="text-sm font-semibold text-slate-200">
          {uploading ? 'Extracting & Parsing Document Text…' : 'Drag & drop or click to upload merchant records'}
        </h4>
        <p className="text-xs text-slate-500 mt-1">
          Supports PDF invoices, order confirmations, shipping receipts, tracking documents, emails, and screenshots.
        </p>
      </div>

      {uploadError && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800/80 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}

      {/* Document Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {documents.map((doc) => {
          const fields = doc.extracted_fields || {};
          const isCompleted = doc.status === 'COMPLETED';

          return (
            <div
              key={doc.id}
              className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-md flex flex-col justify-between hover:border-slate-700 transition-all"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="w-4 h-4 text-sky-400 shrink-0" />
                    <h4 className="font-semibold text-xs text-slate-200 truncate" title={doc.filename}>
                      {doc.filename}
                    </h4>
                  </div>
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0 ${
                    doc.status === 'COMPLETED' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' :
                    doc.status === 'FAILED' ? 'bg-rose-950 text-rose-400 border border-rose-800/60' :
                    'bg-amber-950 text-amber-400 border border-amber-800/60'
                  }`}>
                    {doc.status}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-[11px] text-slate-500 font-mono mb-3">
                  <span className="capitalize">{doc.doc_type || 'other'}</span>
                  <span>•</span>
                  <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                  {doc.dispute_id && (
                    <>
                      <span>•</span>
                      <span className="text-sky-400">{doc.dispute_id}</span>
                    </>
                  )}
                </div>

                {/* Key extracted items preview */}
                <div className="space-y-1.5 mb-4 p-3 rounded-lg bg-slate-950/60 border border-slate-800/60 text-[11px] font-mono">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-slate-500 flex items-center gap-1"><Hash className="w-3 h-3" /> Order:</span>
                    <span className="text-slate-200 truncate max-w-[140px]">{fields.order_id || 'null'}</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-slate-500 flex items-center gap-1"><Truck className="w-3 h-3" /> Tracking:</span>
                    <span className="text-slate-200 truncate max-w-[140px]">{fields.tracking_number || 'null'}</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-slate-500 flex items-center gap-1"><DollarSign className="w-3 h-3" /> Total:</span>
                    <span className="text-slate-200">{fields.amount ? `${fields.amount} ${fields.currency || ''}` : 'null'}</span>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-between pt-3 border-t border-slate-800/80 text-xs">
                <button
                  onClick={() => setSelectedDoc(doc)}
                  className="flex items-center gap-1 text-sky-400 hover:text-sky-300 font-medium"
                >
                  <Eye className="w-3.5 h-3.5" />
                  View Intelligence
                </button>
                <div className="flex items-center gap-1">
                  <a
                    href={`/api/documents/${doc.id}/download`}
                    target="_blank"
                    rel="noreferrer"
                    className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
                    title="Download"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </a>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="p-1.5 rounded hover:bg-rose-950/60 text-slate-500 hover:text-rose-400 transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {documents.length === 0 && !loading && (
        <div className="text-center py-12 text-slate-500 bg-slate-900/30 rounded-2xl border border-slate-800">
          <p className="text-sm">No documents found matching the filter.</p>
        </div>
      )}

      {selectedDoc && (
        <DocumentDrawer doc={selectedDoc} onClose={() => setSelectedDoc(null)} />
      )}
    </div>
  );
}
