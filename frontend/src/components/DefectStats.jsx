import React, { useState, useEffect, useRef } from 'react';
import { getStats } from '../api/client';

// Optimistic local counters update immediately from WS metadata;
// REST polling every 10s reconciles with the DB ground truth.

const DEFECT_COLORS = {
  bubble:  'text-blue-400 bg-blue-400/10 border-blue-400/20',
  crack:   'text-rose-400 bg-rose-400/10 border-rose-400/20',
  dots:    'text-yellow-400 bg-yellow-400/10 border-yellow-400/20',
  scratch: 'text-orange-400 bg-orange-400/10 border-orange-400/20',
};

const DefectStats = ({ liveMetadata }) => {
  const [stats, setStats]   = useState(null);
  const [error, setError]   = useState(false);
  const prevMetaRef         = useRef(null);

  // Fetch from API
  const fetchStats = async () => {
    try {
      const data = await getStats();
      setStats(data);
      setError(false);
    } catch {
      setError(true);
    }
  };

  useEffect(() => {
    fetchStats();
    const id = setInterval(fetchStats, 10000); // reconcile every 10s
    return () => clearInterval(id);
  }, []);

  // Optimistic increment: when live feed reports a new FAIL, bump local counters immediately.
  // Prevents the 5-10s delay before the DB write propagates back via polling.
  useEffect(() => {
    if (!liveMetadata || !stats) return;
    const prev = prevMetaRef.current;
    prevMetaRef.current = liveMetadata;

    if (!prev || prev.pass_fail === liveMetadata.pass_fail) return;
    if (liveMetadata.pass_fail !== 'Fail') return;

    const newCounts = { ...(stats.defect_counts ?? {}) };
    (liveMetadata.detections ?? []).forEach(d => {
      const cls = d.label || d.class;
      if (cls) newCounts[cls] = (newCounts[cls] ?? 0) + 1;
    });

    setStats(prev => prev ? ({
      ...prev,
      total:      prev.total + 1,
      fail_count: prev.fail_count + 1,
      defect_counts: newCounts,
    }) : prev);
  }, [liveMetadata]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return (
    <div className="bg-slate-800 p-3 sm:p-4 rounded-xl border border-slate-700 flex items-center justify-center h-40">
      <span className="text-slate-500 text-sm">Stats unavailable</span>
    </div>
  );

  if (!stats) return <div className="animate-pulse bg-slate-800 h-40 rounded-xl border border-slate-700" />;

  const passCount = stats.pass_count ?? stats.pass ?? 0;
  const yieldPct  = stats.total ? ((passCount / stats.total) * 100).toFixed(1) : '—';
  const counts    = stats.defect_counts ?? {};

  return (
    <div className="bg-slate-800 p-3 sm:p-4 rounded-xl shadow-lg border border-slate-700">
      <h2 className="text-lg sm:text-xl font-bold text-slate-100 mb-3 sm:mb-4">Defect Distribution</h2>

      <div className="grid grid-cols-2 gap-2 sm:gap-3">
        {['bubble', 'crack', 'dots', 'scratch'].map(cls => (
          <div
            key={cls}
            className={`p-2.5 sm:p-3 rounded-lg border flex flex-col items-center justify-center ${
              DEFECT_COLORS[cls]
            }`}
          >
            <span className="text-xs font-medium uppercase tracking-wider mb-1">{cls}</span>
            <span className="text-xl sm:text-2xl font-bold tabular-nums">{counts[cls] ?? 0}</span>
          </div>
        ))}
      </div>

      <div className="mt-3 sm:mt-4 flex justify-between text-xs sm:text-sm text-slate-400 border-t border-slate-700 pt-3">
        <span>Total: <span className="text-slate-200 font-mono tabular-nums">{stats.total}</span></span>
        <span>
          Yield:{' '}
          <span className={`font-bold tabular-nums ${parseFloat(yieldPct) >= 80 ? 'text-emerald-400' : 'text-amber-400'}`}>
            {yieldPct}%
          </span>
        </span>
      </div>
    </div>
  );
};

export default DefectStats;