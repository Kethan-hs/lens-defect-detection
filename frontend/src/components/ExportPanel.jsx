import React, { useState } from 'react';
import { exportCSV, exportPDF } from '../api/client';

const ExportPanel = () => {
  const [loading, setLoading] = useState(false);

  const handleExport = (type) => {
    setLoading(true);
    try {
      if (type === 'csv') exportCSV();
      if (type === 'pdf') exportPDF();
    } finally {
      setTimeout(() => setLoading(false), 1000);
    }
  };

  return (
    <div className="bg-slate-800 p-3 sm:p-4 rounded-xl shadow-lg border border-slate-700">
      <h2 className="text-lg sm:text-xl font-bold text-slate-100 mb-3 sm:mb-4">Export Reports</h2>
      <div className="flex flex-col gap-3">
        <button
          onClick={() => handleExport('csv')}
          disabled={loading}
          className="flex items-center justify-center gap-2 w-full py-3 sm:py-2.5 bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-400 disabled:opacity-50 text-white rounded-lg font-medium transition-colors text-sm sm:text-base min-h-[44px]"
        >
          📄 Download CSV Log
        </button>
        <button
          onClick={() => handleExport('pdf')}
          disabled={loading}
          className="flex items-center justify-center gap-2 w-full py-3 sm:py-2.5 bg-slate-700 hover:bg-slate-600 active:bg-slate-500 disabled:opacity-50 text-white border border-slate-600 rounded-lg font-medium transition-colors text-sm sm:text-base min-h-[44px]"
        >
          📊 Download PDF Summary
        </button>
      </div>
    </div>
  );
};

export default ExportPanel;
