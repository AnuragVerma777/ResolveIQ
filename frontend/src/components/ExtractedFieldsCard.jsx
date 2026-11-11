import React, { useState } from 'react';
import { Hash, CreditCard, User, Calendar, Package, DollarSign, Truck, Clock, CheckCircle2, Copy, Check, FileText } from 'lucide-react';

export default function ExtractedFieldsCard({ fields, title = 'Extracted Intelligence' }) {
  const [copiedKey, setCopiedKey] = useState(null);

  if (!fields) return null;

  const handleCopy = (key, val) => {
    navigator.clipboard.writeText(String(val));
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1800);
  };

  const items = [
    { key: 'order_id', label: 'Order ID', val: fields.order_id, icon: Hash },
    { key: 'transaction_id', label: 'Transaction ID', val: fields.transaction_id, icon: CreditCard },
    { key: 'customer_name', label: 'Customer Name', val: fields.customer_name, icon: User },
    { key: 'purchase_date', label: 'Purchase Date', val: fields.purchase_date, icon: Calendar },
    { key: 'product_or_service', label: 'Product / Service', val: fields.product_or_service, icon: Package },
    {
      key: 'amount',
      label: 'Amount & Currency',
      val: fields.amount !== null && fields.amount !== undefined ? `${fields.amount} ${fields.currency || ''}`.trim() : null,
      icon: DollarSign,
    },
    { key: 'tracking_number', label: 'Tracking Number', val: fields.tracking_number, icon: Truck },
    { key: 'shipment_date', label: 'Shipment Date', val: fields.shipment_date, icon: Clock },
    { key: 'delivery_date', label: 'Delivery Date', val: fields.delivery_date, icon: CheckCircle2 },
    { key: 'refund_status', label: 'Refund Status', val: fields.refund_status, icon: FileText },
  ];

  const sourceRefs = fields.source_references || {};

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-md">
      <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-800">
        <h4 className="text-sm font-semibold text-slate-200 tracking-wide flex items-center gap-2">
          <FileText className="w-4 h-4 text-sky-400" />
          {title}
        </h4>
        <span className="text-[11px] text-slate-400 font-mono">
          {Object.values(fields).filter(v => v !== null && v !== undefined && typeof v !== 'object').length} fields extracted
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map(({ key, label, val, icon: Icon }) => {
          const hasVal = val !== null && val !== undefined && val !== '';
          const sourceExcerpt = sourceRefs[key];

          return (
            <div
              key={key}
              className={`p-3 rounded-lg border transition-all ${
                hasVal
                  ? 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                  : 'bg-slate-950/30 border-slate-900 opacity-60'
              }`}
            >
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className="text-[11px] font-medium text-slate-400 flex items-center gap-1.5">
                  <Icon className="w-3.5 h-3.5 text-slate-400" />
                  {label}
                </span>
                {hasVal && (
                  <button
                    onClick={() => handleCopy(key, val)}
                    title="Copy value"
                    className="text-slate-500 hover:text-slate-300 transition-colors p-1"
                  >
                    {copiedKey === key ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                  </button>
                )}
              </div>

              <div className="font-mono text-xs font-semibold text-slate-200 truncate">
                {hasVal ? (
                  <span className="text-sky-300">{String(val)}</span>
                ) : (
                  <span className="text-slate-600 italic">null</span>
                )}
              </div>

              {sourceExcerpt && (
                <div className="mt-1.5 pt-1.5 border-t border-slate-900 text-[10px] text-slate-400 truncate" title={`Excerpt: "${sourceExcerpt}"`}>
                  <span className="text-slate-500">Source:</span> &ldquo;{sourceExcerpt}&rdquo;
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
