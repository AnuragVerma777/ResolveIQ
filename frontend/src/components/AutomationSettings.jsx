import React, { useState, useEffect } from 'react';
import {
  Zap,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Send,
  Save,
  Lock,
  Clock,
  ExternalLink,
  ShieldCheck,
  Activity,
  Check,
  AlertCircle,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  FileText,
  Sliders,
} from 'lucide-react';
import {
  fetchAutomationSettings,
  updateAutomationSettings,
  testZapierWebhook,
  fetchWebhookDeliveries,
} from '../api';
import { useToast } from '../context/ToastContext';

export default function AutomationSettings() {
  const { toast } = useToast();
  const [settings, setSettings] = useState(null);
  const [webhookUrl, setWebhookUrl] = useState('');
  const [enabledEvents, setEnabledEvents] = useState([]);
  const [timeoutSeconds, setTimeoutSeconds] = useState(8.0);
  const [maxRetries, setMaxRetries] = useState(2);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [deliveries, setDeliveries] = useState([]);
  const [loadingDeliveries, setLoadingDeliveries] = useState(false);
  const [expandedDeliveryId, setExpandedDeliveryId] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);

  // Load automation configuration and delivery log
  const loadData = async () => {
    setLoading(true);
    try {
      const [st, dels] = await Promise.all([
        fetchAutomationSettings(),
        fetchWebhookDeliveries(50).catch(() => []),
      ]);
      setSettings(st);
      setWebhookUrl(st.webhook_url || '');
      setEnabledEvents(st.enabled_events || []);
      setTimeoutSeconds(st.timeout_seconds || 8.0);
      setMaxRetries(st.max_retries !== undefined ? st.max_retries : 2);
      setDeliveries(dels);
    } catch (err) {
      console.error('Failed to load automation settings', err);
    } finally {
      setLoading(false);
    }
  };

  const refreshDeliveries = async () => {
    setLoadingDeliveries(true);
    try {
      const dels = await fetchWebhookDeliveries(50);
      setDeliveries(dels);
    } catch (err) {
      console.error('Failed to refresh deliveries', err);
    } finally {
      setLoadingDeliveries(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Save Settings
  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setSaving(true);
    setStatusMessage(null);
    try {
      const res = await updateAutomationSettings({
        webhook_url: webhookUrl.trim(),
        enabled_events: enabledEvents,
        timeout_seconds: parseFloat(timeoutSeconds) || 8.0,
        max_retries: parseInt(maxRetries, 10) || 2,
      });
      setSettings(res);
      setWebhookUrl(res.webhook_url);
      setEnabledEvents(res.enabled_events);
      setStatusMessage({ type: 'success', text: 'Automation settings updated successfully.' });
    } catch (err) {
      setStatusMessage({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  // Test Webhook
  const handleTestWebhook = async () => {
    if (!webhookUrl.trim()) {
      toast.warning('Please enter a Zapier Catch Hook URL first.');
      return;
    }
    setTesting(true);
    setTestResult(null);
    setStatusMessage(null);
    try {
      const res = await testZapierWebhook(webhookUrl.trim());
      setTestResult(res);
      await loadData();
    } catch (err) {
      setTestResult({
        success: false,
        message: err.message,
        response_time_ms: 0,
      });
    } finally {
      setTesting(false);
    }
  };

  // Toggle event
  const handleToggleEvent = (eventId) => {
    if (enabledEvents.includes(eventId)) {
      setEnabledEvents(enabledEvents.filter((e) => e !== eventId));
    } else {
      setEnabledEvents([...enabledEvents, eventId]);
    }
  };

  const isConnectedAndVerified = settings?.is_configured && settings?.is_verified;

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-20">
      {/* Top Banner: Automation Hub & Status */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="p-1.5 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
                <Zap className="w-4 h-4" />
              </span>
              <span className="text-xs font-mono font-bold uppercase tracking-widest text-amber-400">
                Zapier Webhook Automation Engine
              </span>
            </div>
            <h2 className="text-2xl font-black text-white tracking-tight">
              Automation &amp; Notification Settings
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Connect ResolveIQ to Zapier via secure HTTPS Catch Hooks. Automatically notify Slack channels,
              dispatch Gmail alerts, or generate Jira follow-up tasks as disputes progress through investigation.
            </p>
          </div>

          {/* Connection Status Badge */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center gap-3">
              <span className="relative flex h-3 w-3">
                <span
                  className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                    isConnectedAndVerified ? 'bg-emerald-400' : 'bg-amber-400'
                  }`}
                />
                <span
                  className={`relative inline-flex rounded-full h-3 w-3 ${
                    isConnectedAndVerified ? 'bg-emerald-500' : 'bg-amber-500'
                  }`}
                />
              </span>
              <div>
                <div className="text-xs font-bold text-white flex items-center gap-2">
                  <span>
                    {isConnectedAndVerified
                      ? 'Zapier Connected & Verified'
                      : settings?.is_configured
                      ? 'Configured (Verification Needed)'
                      : 'Not Connected'}
                  </span>
                  <span
                    className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-bold uppercase ${
                      isConnectedAndVerified
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                        : 'bg-amber-950 text-amber-300 border border-amber-700'
                    }`}
                  >
                    {isConnectedAndVerified ? 'VERIFIED' : 'UNVERIFIED'}
                  </span>
                </div>
                <div className="text-[11px] font-mono text-slate-400">
                  {settings?.webhook_url_masked || 'No Webhook URL configured'}
                </div>
              </div>
            </div>

            <button
              onClick={handleTestWebhook}
              disabled={testing || !webhookUrl}
              className="px-3.5 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 transition-all shadow disabled:opacity-50"
            >
              <Send className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
              <span>{testing ? 'Testing…' : 'Send Test Webhook'}</span>
            </button>
          </div>
        </div>

        {/* Test Result Callout if present */}
        {testResult && (
          <div
            className={`mt-4 p-4 rounded-xl border text-xs flex items-start justify-between gap-3 animate-in fade-in duration-150 ${
              testResult.success
                ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
                : 'bg-rose-950/60 border-rose-800 text-rose-300'
            }`}
          >
            <div className="flex items-start gap-2.5">
              {testResult.success ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              )}
              <div>
                <strong className="block text-sm">
                  {testResult.success ? 'Zapier Hook Verified!' : 'Test Delivery Failed'}
                </strong>
                <p className="mt-0.5 text-[11px] opacity-90">{testResult.message}</p>
                <div className="mt-1 font-mono text-[10px] opacity-75">
                  Latency: {testResult.response_time_ms}ms · Status Code: {testResult.status_code || 'N/A'}
                </div>
              </div>
            </div>
            <button
              onClick={() => setTestResult(null)}
              className="text-xs opacity-60 hover:opacity-100 font-mono p-1"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Webhook URL & Event Configuration (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* Webhook Configuration Form */}
          <form
            onSubmit={handleSaveSettings}
            className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-5"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Sliders className="w-4 h-4 text-amber-400" />
                Zapier Webhook Endpoint Configuration
              </h3>
              <span className="text-[11px] font-mono text-slate-400">HTTPS Required</span>
            </div>

            {statusMessage && (
              <div
                className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                  statusMessage.type === 'success'
                    ? 'bg-emerald-950/60 border border-emerald-800 text-emerald-300'
                    : 'bg-rose-950/60 border border-rose-800 text-rose-300'
                }`}
              >
                <span>{statusMessage.text}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Zapier Catch Hook URL
              </label>
              <input
                type="url"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                placeholder="https://hooks.zapier.com/hooks/catch/1234567/abcdefg/"
                className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs font-mono text-slate-200 focus:outline-none focus:border-amber-500"
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Obtain this from your Zapier Zap trigger (&quot;Webhooks by Zapier &rarr; Catch Hook&quot;).
              </p>
            </div>

            {/* Timeout & Retries */}
            <div className="grid grid-cols-2 gap-4 pt-1">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Timeout (Seconds)
                </label>
                <input
                  type="number"
                  min="1"
                  max="30"
                  step="0.5"
                  value={timeoutSeconds}
                  onChange={(e) => setTimeoutSeconds(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-amber-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Max Transient Retries (5xx / Timeout)
                </label>
                <input
                  type="number"
                  min="0"
                  max="5"
                  value={maxRetries}
                  onChange={(e) => setMaxRetries(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>

            {/* Supported Events Checkboxes */}
            <div className="space-y-3 pt-3 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Triggered Automation Events
                </span>
                <span className="text-[11px] font-mono text-slate-400">
                  {enabledEvents.length} of {settings?.all_supported_events?.length || 6} enabled
                </span>
              </div>

              <div className="space-y-2">
                {settings?.all_supported_events?.map((ev) => {
                  const isChecked = enabledEvents.includes(ev.id);
                  return (
                    <label
                      key={ev.id}
                      className={`p-3 rounded-xl border flex items-start gap-3 cursor-pointer select-none transition-all ${
                        isChecked
                          ? 'bg-slate-950 border-amber-500/40 text-slate-200'
                          : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => handleToggleEvent(ev.id)}
                        className="mt-1 rounded bg-slate-900 border-slate-700 text-amber-500 focus:ring-0"
                      />
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs text-white">{ev.name}</span>
                          <span className="font-mono text-[10px] text-amber-400/90 px-1.5 py-0.2 rounded bg-amber-950/60 border border-amber-800/60">
                            {ev.id}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 leading-relaxed">
                          {ev.description}
                        </p>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            <div className="pt-2 flex items-center justify-end gap-3">
              <button
                type="submit"
                disabled={saving}
                className="px-6 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 font-bold text-xs uppercase tracking-wider text-slate-950 flex items-center gap-2 shadow transition-all disabled:opacity-50"
              >
                <Save className="w-3.5 h-3.5" />
                <span>{saving ? 'Saving…' : 'Save Automation Settings'}</span>
              </button>
            </div>
          </form>
        </div>

        {/* Right Column: Zapier Setup Instructions & Privacy Guarantees (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Step-by-Step Zapier Setup Guide */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <ExternalLink className="w-4 h-4 text-amber-400" />
              How to Connect a Zap (3 Minutes)
            </h3>

            <div className="space-y-3 text-xs text-slate-300">
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                <span className="font-bold text-amber-400">1. Create a Zap in Zapier</span>
                <p className="text-slate-400 text-[11px]">
                  Go to <a href="https://zapier.com" target="_blank" rel="noreferrer" className="text-sky-400 underline">zapier.com</a> and click <strong>+ Create Zap</strong>.
                </p>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                <span className="font-bold text-amber-400">2. Select &quot;Webhooks by Zapier&quot;</span>
                <p className="text-slate-400 text-[11px]">
                  Choose trigger <strong>Webhooks by Zapier</strong>, then select event <strong>Catch Hook</strong>.
                </p>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                <span className="font-bold text-amber-400">3. Paste Hook URL &amp; Test</span>
                <p className="text-slate-400 text-[11px]">
                  Copy the generated Catch Hook URL, paste it into ResolveIQ, and click <strong>Send Test Webhook</strong>.
                </p>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                <span className="font-bold text-amber-400">4. Map Action in Zapier</span>
                <p className="text-slate-400 text-[11px]">
                  In Zapier, click <strong>Test Trigger</strong> to see the test payload, then add an action:
                  Slack message, Gmail notification, or Jira task!
                </p>
              </div>
            </div>
          </div>

          {/* Privacy & Anti-Spam Guarantees */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-3 text-xs text-slate-300">
            <h4 className="font-bold text-slate-200 flex items-center gap-2">
              <Lock className="w-4 h-4 text-emerald-400" />
              Privacy &amp; Data Protection Guarantees
            </h4>
            <ul className="space-y-2 text-slate-400 text-[11px] list-disc list-inside">
              <li>Customer credit cards, passwords, and access tokens are strictly stripped prior to transmission.</li>
              <li>Document binaries and raw OCR text are never sent over third-party webhooks.</li>
              <li>Customer email addresses are masked (e.g. <code>jo***@domain.com</code>).</li>
              <li>Automated deduplication prevents accidental duplicate event alerts within 30 seconds.</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Full-width: Chronological Webhook Delivery History */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <Activity className="w-4 h-4 text-sky-400" />
              Recent Webhook Delivery History (SQLite)
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Audited record of all dispatched webhook payloads, status codes, latency, and retry attempts.
            </p>
          </div>

          <button
            onClick={refreshDeliveries}
            disabled={loadingDeliveries}
            className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 border border-slate-700 flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingDeliveries ? 'animate-spin' : ''}`} />
            <span>Refresh History</span>
          </button>
        </div>

        {/* Deliveries Table */}
        <div className="overflow-x-auto">
          {deliveries.length === 0 ? (
            <p className="text-xs text-slate-500 italic p-8 text-center">
              No webhook events dispatched yet. Click &quot;Send Test Webhook&quot; above to verify your Catch Hook!
            </p>
          ) : (
            <div className="space-y-2">
              {deliveries.map((del) => {
                const isExpanded = expandedDeliveryId === del.id;
                return (
                  <div
                    key={del.id}
                    className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs font-sans space-y-2"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span
                          className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold uppercase ${
                            del.delivered
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                              : 'bg-rose-950 text-rose-300 border border-rose-700'
                          }`}
                        >
                          {del.delivered ? 'DELIVERED (2xx)' : 'FAILED'}
                        </span>
                        <span className="font-mono text-slate-200 font-bold">{del.event_name}</span>
                        {del.dispute_id && (
                          <span className="font-mono text-[11px] text-sky-400 bg-sky-950/60 px-1.5 py-0.2 rounded border border-sky-800/60">
                            {del.dispute_id}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-4 text-slate-400 font-mono text-[11px]">
                        <span>Status: <strong className={del.delivered ? 'text-emerald-400' : 'text-rose-400'}>{del.status_code || 'Err'}</strong></span>
                        <span>Latency: {del.response_time_ms ? `${del.response_time_ms}ms` : 'N/A'}</span>
                        <span>Attempts: {del.attempts}</span>
                        <span>{new Date(del.created_at).toLocaleTimeString()}</span>
                        <button
                          onClick={() => setExpandedDeliveryId(isExpanded ? null : del.id)}
                          className="text-sky-400 hover:text-sky-300 flex items-center gap-1 font-sans text-xs"
                        >
                          <span>{isExpanded ? 'Hide Payload' : 'View Payload'}</span>
                          {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </button>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="p-3 rounded-lg bg-slate-900 border border-slate-800/80 font-mono text-[11px] text-slate-300 space-y-1">
                        <div>Target URL: <span className="text-amber-300">{del.target_url_masked}</span></div>
                        <div>Event ID: <span className="text-sky-300">{del.event_id}</span></div>
                        {del.error && <div className="text-rose-400">Error: {del.error}</div>}
                        <div className="text-slate-400 text-[10px] pt-1">Payload:</div>
                        <pre className="p-2 rounded bg-slate-950 text-slate-300 text-[10px] overflow-x-auto">
                          {JSON.stringify(del.payload, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
