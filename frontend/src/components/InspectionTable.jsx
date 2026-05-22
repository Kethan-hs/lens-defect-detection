import React, { useEffect, useState, useCallback } from 'react';
import { getInspections } from '../api/client';

/* ── helpers ─────────────────────────────────────────────────────────────── */
const parseDefects = (json) => {
  try { return JSON.parse(json || '[]'); }
  catch { return []; }
};

// FIX: normalise label — backend may return "label" or "class"
const defectName = (d) => d?.label ?? d?.class ?? '?';

const fmtTs = (raw) => {
  if (!raw) return '—';
  const ts = !raw.endsWith('Z') && !raw.includes('+') ? raw + 'Z' : raw;
  const d  = new Date(ts);
  return isNaN(d) ? raw : d.toLocaleString();
};

/* ── JSON tree viewer ─────────────────────────────────────────────────────── */
const JsonNode = ({ data, depth = 0 }) => {
  const [collapsed, setCollapsed] = useState(depth > 1);

  if (data === null || data === undefined)
    return <span className="text-slate-500 italic">null</span>;
  if (typeof data === 'boolean')
    return <span className="text-purple-400">{String(data)}</span>;
  if (typeof data === 'number')
    return <span className="text-cyan-400">{data}</span>;
  if (typeof data === 'string')
    return <span className="text-amber-400">"{data}"</span>;

  if (Array.isArray(data)) {
    if (!data.length) return <span className="text-slate-500">[]</span>;
    return (
      <span>
        <button onClick={() => setCollapsed(!collapsed)}
          className="text-slate-400 hover:text-slate-200 text-xs mr-1 select-none">
          {collapsed ? '▶' : '▼'}
        </button>
        <span className="text-slate-500">Array({data.length})</span>
        {!collapsed && (
          <div className="border-l border-slate-700 ml-2 pl-3">
            {data.map((item, i) => (
              <div key={i} className="py-0.5">
                <span className="text-slate-600 text-xs mr-2">{i}:</span>
                <JsonNode data={item} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </span>
    );
  }

  const keys = Object.keys(data);
  if (!keys.length) return <span className="text-slate-500">{'{}'}</span>;
  return (
    <span>
      <button onClick={() => setCollapsed(!collapsed)}
        className="text-slate-400 hover:text-slate-200 text-xs mr-1 select-none">
        {collapsed ? '▶' : '▼'}
      </button>
      <span className="text-slate-500">Object({keys.length})</span>
      {!collapsed && (
        <div className="border-l border-slate-700 ml-2 pl-3">
          {keys.map(k => (
            <div key={k} className="py-0.5">
              <span className="text-indigo-400 text-sm">{k}</span>
              <span className="text-slate-600 mx-1">:</span>
              <JsonNode data={data[k]} depth={depth + 1} />
            </div>
          ))}
        </div>
      )}
    </span>
  );
};

/* ── Detail modal ─────────────────────────────────────────────────────────── */
const DetailModal = ({ log, onClose }) => {
  const defects = parseDefects(log.defects_json);
  const isPass  = log.pass_fail === 'Pass';
  const [viewMode, setViewMode] = useState('tree');

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', handler);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  const onBackdrop = useCallback((e) => {
    if (e.target === e.currentTarget) onClose();
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-6"
      onClick={onBackdrop}
      style={{ backgroundColor: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
    >
      <div
        className="bg-slate-800 w-full sm:max-w-lg sm:rounded-2xl rounded-t-2xl max-h-[95vh] sm:max-h-[85vh] border-t sm:border border-slate-600/50 shadow-2xl flex flex-col overflow-hidden"
        style={{ animation: 'modalIn 0.22s ease-out' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-slate-700 shrink-0">
          <div className="flex items-center gap-3">
            <div
              className={`w-3 h-3 rounded-full ${isPass ? 'bg-emerald-400' : 'bg-rose-400'}`}
              style={{ boxShadow: isPass ? '0 0 8px #34d399' : '0 0 8px #fb7185' }}
            />
            <h3 className="text-base sm:text-lg font-bold text-slate-100">Inspection #{log.id}</h3>
          </div>
          <button onClick={onClose}
            className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-700 transition-colors text-lg">
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4 overscroll-contain">
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-900/60 rounded-lg p-3">
              <span className="text-xs text-slate-500 uppercase tracking-wider block mb-1">Time</span>
              <span className="text-sm text-slate-200">{fmtTs(log.timestamp)}</span>
            </div>
            <div className="bg-slate-900/60 rounded-lg p-3">
              <span className="text-xs text-slate-500 uppercase tracking-wider block mb-1">Result</span>
              <span className={`text-sm font-bold ${isPass ? 'text-emerald-400' : 'text-rose-400'}`}>
                {log.pass_fail}
              </span>
            </div>
          </div>

          {defects.length > 0 && (
            <div>
              <span className="text-xs text-slate-500 uppercase tracking-wider block mb-2">
                Defects ({defects.length})
              </span>
              <div className="flex flex-wrap gap-2">
                {defects.map((d, i) => (
                  <span key={i} className="inline-flex items-center gap-1.5 text-xs bg-slate-700/80 text-slate-200 px-2.5 py-1.5 rounded-lg border border-slate-600/50">
                    <span className="font-medium text-amber-400">{defectName(d)}</span>
                    <span className="text-slate-400">{((d.confidence ?? 0) * 100).toFixed(0)}%</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-500 uppercase tracking-wider">Raw Data</span>
              <div className="flex bg-slate-900/60 rounded-lg p-0.5">
                {['tree', 'raw'].map(m => (
                  <button key={m} onClick={() => setViewMode(m)}
                    className={`px-3 py-1.5 text-xs rounded-md transition-colors min-h-[32px] ${
                      viewMode === m ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'
                    }`}>
                    {m.charAt(0).toUpperCase() + m.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <div className="bg-slate-900 rounded-lg p-3 max-h-48 overflow-y-auto overflow-x-auto text-sm font-mono border border-slate-700/50">
              {viewMode === 'tree'
                ? <JsonNode data={defects} />
                : <pre className="text-amber-400 whitespace-pre-wrap break-words text-xs">{JSON.stringify(defects, null, 2)}</pre>
              }
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 shrink-0">
          <button onClick={onClose}
            className="w-full py-3 sm:py-2.5 bg-slate-700 hover:bg-slate-600 active:bg-slate-500 rounded-lg text-slate-100 font-medium transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

/* ── Mobile card ──────────────────────────────────────────────────────────── */
const InspectionCard = ({ log, onDetails }) => {
  const defects = parseDefects(log.defects_json);
  const isPass  = log.pass_fail === 'Pass';

  return (
    <div className="bg-slate-900/40 rounded-lg p-4 border border-slate-700/50 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-slate-400 text-sm font-mono">#{log.id}</span>
          <span className={`px-2 py-0.5 rounded text-xs font-bold ${
            isPass ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
          }`}>{log.pass_fail}</span>
        </div>
        <button onClick={() => onDetails(log)}
          className="text-indigo-400 text-sm font-medium px-3 py-1.5 rounded-lg hover:bg-indigo-500/10 transition-colors min-h-[36px]">
          Details →
        </button>
      </div>
      <div className="text-xs text-slate-500">{fmtTs(log.timestamp)}</div>
      {defects.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {defects.map((d, i) => (
            <span key={i} className="text-xs bg-slate-700/80 px-2 py-1 rounded border border-slate-600/50 text-slate-300">
              {defectName(d)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

/* ── Main component ───────────────────────────────────────────────────────── */
const InspectionTable = () => {
  const [logs, setLogs]           = useState([]);
  const [selectedLog, setSelectedLog] = useState(null);
  const [error, setError]         = useState(false);

  useEffect(() => {
    const fetch = async () => {
      try {
        const data = await getInspections(0, 10);
        setLogs(data);
        setError(false);
      } catch {
        setError(true);
      }
    };
    fetch();
    const id = setInterval(fetch, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="bg-slate-800 rounded-xl shadow-lg border border-slate-700 overflow-hidden">
      <div className="p-4 border-b border-slate-700">
        <h2 className="text-lg sm:text-xl font-bold text-slate-100">Recent Inspections</h2>
      </div>

      {error && (
        <div className="p-6 text-center text-slate-500 text-sm">Failed to load inspection data</div>
      )}

      {/* Desktop table */}
      {!error && (
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-900/50 text-slate-400 text-xs uppercase tracking-wider">
                <th className="p-4 font-medium">ID</th>
                <th className="p-4 font-medium">Time</th>
                <th className="p-4 font-medium">Result</th>
                <th className="p-4 font-medium">Defects</th>
                <th className="p-4 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-slate-500 text-sm">No inspections yet</td>
                </tr>
              ) : logs.map(log => {
                const defects = parseDefects(log.defects_json);
                const isPass  = log.pass_fail === 'Pass';
                return (
                  <tr key={log.id} className="hover:bg-slate-700/30 transition-colors">
                    <td className="p-4 text-slate-300 font-mono text-sm">#{log.id}</td>
                    <td className="p-4 text-slate-400 text-sm">{fmtTs(log.timestamp)}</td>
                    <td className="p-4">
                      <span className={`px-2 py-1 rounded text-xs font-bold ${
                        isPass ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                      }`}>{log.pass_fail}</span>
                    </td>
                    <td className="p-4">
                      {defects.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {defects.map((d, i) => (
                            <span key={i} className="text-xs bg-slate-700 px-2 py-1 rounded border border-slate-600">
                              {defectName(d)}
                            </span>
                          ))}
                        </div>
                      ) : <span className="text-slate-500 text-sm">—</span>}
                    </td>
                    <td className="p-4 text-right">
                      <button onClick={() => setSelectedLog(log)}
                        className="text-indigo-400 hover:text-indigo-300 text-sm font-medium px-2 py-1 rounded hover:bg-indigo-500/10 transition-colors min-h-[36px]">
                        Details
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Mobile cards */}
      {!error && (
        <div className="sm:hidden p-3 space-y-2">
          {logs.length === 0
            ? <div className="text-center text-slate-500 py-8 text-sm">No inspections yet</div>
            : logs.map(log => <InspectionCard key={log.id} log={log} onDetails={setSelectedLog} />)
          }
        </div>
      )}

      {selectedLog && <DetailModal log={selectedLog} onClose={() => setSelectedLog(null)} />}
    </div>
  );
};

export default InspectionTable;
