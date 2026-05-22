import React, { useEffect, useState, useRef } from 'react';
import { getInspections } from '../api/client';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

const MAX_POINTS = 60;

const fmtTs = (raw) => {
  if (!raw) return '';
  const ts = !raw.endsWith('Z') && !raw.includes('+') ? raw + 'Z' : raw;
  const d  = new Date(ts);
  return isNaN(d) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

// Props: liveMetadata — current frame metadata from LiveFeed
const PassFailTrend = ({ liveMetadata }) => {
  const [data, setData]   = useState([]);
  const [error, setError] = useState(false);
  const lastIdRef         = useRef(null);

  // Build trend array from an ordered list of logs
  const buildTrend = (logs) => {
    let passCount = 0;
    return logs.map((log, i) => {
      if (log.pass_fail === 'Pass') passCount++;
      return {
        id:       log.id,
        time:     fmtTs(log.timestamp),
        passRate: parseFloat(((passCount / (i + 1)) * 100).toFixed(1)),
        result:   log.pass_fail,
      };
    });
  };

  // Initial load
  useEffect(() => {
    const load = async () => {
      try {
        const logs = await getInspections(0, MAX_POINTS);
        const chrono = [...logs].reverse();
        if (chrono.length) lastIdRef.current = chrono[chrono.length - 1].id;
        setData(buildTrend(chrono));
        setError(false);
      } catch {
        setError(true);
      }
    };
    load();
    // Reconcile with DB every 30s (not every 5s — live metadata handles real-time updates)
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  // Optimistic append: when live frame transitions to a new inspection result, append a point.
  const prevResult = useRef(null);
  useEffect(() => {
    if (!liveMetadata) return;
    const result = liveMetadata.pass_fail;
    if (!result || result === 'No Lens' || result === prevResult.current) return;
    prevResult.current = result;

    const now = new Date();
    const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setData(prev => {
      const next = [...prev, { id: `live-${Date.now()}`, time, result, passRate: 0 }].slice(-MAX_POINTS);
      // Recalculate passRate across the window
      let p = 0;
      return next.map((pt, i) => {
        if (pt.result === 'Pass') p++;
        return { ...pt, passRate: parseFloat(((p / (i + 1)) * 100).toFixed(1)) };
      });
    });
  }, [liveMetadata]);

  return (
    <div className="bg-slate-800 p-4 rounded-xl shadow-lg border border-slate-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg sm:text-xl font-bold text-slate-100">
          Yield Trend
          <span className="text-sm font-normal text-slate-500 ml-2">(last {MAX_POINTS} scans)</span>
        </h2>
        {/* Live indicator */}
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" style={{ animation: 'pulse 2s infinite' }} />
          <span className="text-xs text-slate-500">Live</span>
        </div>
      </div>

      {error ? (
        <div className="flex items-center justify-center h-[160px] text-slate-500 text-sm">Could not load trend data</div>
      ) : data.length === 0 ? (
        <div className="flex items-center justify-center h-[160px] text-slate-500 text-sm">No inspections yet</div>
      ) : (
        <ResponsiveContainer width="100%" height={200} minWidth={0}>
          <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} tick={{ fill: '#94a3b8' }} interval="preserveStartEnd" />
            <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 100]} tick={{ fill: '#94a3b8' }} tickFormatter={v => `${v}%`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', color: '#f8fafc', borderRadius: 8 }}
              itemStyle={{ color: '#34d399' }}
              formatter={v => [`${v}%`, 'Pass Rate']}
            />
            {/* 80% reference line — common industrial SLA */}
            <ReferenceLine y={80} stroke="#f59e0b" strokeDasharray="4 4" strokeWidth={1} label={{ value: '80%', position: 'right', fill: '#f59e0b', fontSize: 10 }} />
            <Line type="monotone" dataKey="passRate" stroke="#34d399" strokeWidth={2.5}
              dot={false} activeDot={{ r: 5, fill: '#34d399' }} name="Pass Rate" isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
};

export default PassFailTrend;