/* ─── Imports ────────────────────────────────────────────────────────────────────────────── */

import { useState, useEffect, useRef, useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { ModuleRegistry, AllCommunityModule } from 'ag-grid-community';
import { Download, Edit3, AlertCircle, Loader2, BrainCircuit, Check, X, AlertTriangle, CheckCircle, Network } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '@/services/api.service';
import type { SessionDataResponse, AnomalyRow } from '@/types/api';

import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';

/* ─── Initialization & Types ─────────────────────────────────────────────────────────────── */

ModuleRegistry.registerModules([AllCommunityModule]);

export interface ReviewEditProps {
  sessionId: string;
}

export interface ColumnDef {
  field: string;
  sortable: boolean;
  filter: boolean;
}

type ActiveLearningRow = AnomalyRow & { _originalIndex: number };

/* ─── Component ──────────────────────────────────────────────────────────────────────────── */

/**
 * ReviewEdit component displays the Active Learning Queue (Uncertainty Sampling)
 * alongside a spreadsheet-like view of the cleaned dataset for final export.
 */
export default function ReviewEdit({ sessionId }: ReviewEditProps): React.JSX.Element {
  const [rowData, setRowData] = useState<Record<string, unknown>[]>([]);
  const [activeQueue, setActiveQueue] = useState<ActiveLearningRow[]>([]);
  const [totalRows, setTotalRows] = useState<number>(0);
  const [columnDefs, setColumnDefs] = useState<ColumnDef[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const gridRef = useRef<AgGridReact>(null);

  useEffect(() => {
    if (!sessionId) return;

    const fetchData = async () => {
      try {
        setIsLoading(true);

        // Fetch BOTH Raw Data (for Active Learning) and Cleaned Data (for AG Grid) concurrently
        const [rawRes, cleanRes] = await Promise.all([
          api.get<SessionDataResponse>(`/api/data/${sessionId}`),
          api.get<SessionDataResponse>(`/api/data/${sessionId}?is_cleaned=true`).catch(() => null) // Catch if not cleaned yet
        ]);

        // Process Active Learning Queue (from Raw Data)
        if (rawRes.data && rawRes.data.data) {
          const ambiguous = rawRes.data.data
            .map((r, i) => ({ ...r, _originalIndex: i }))
            .filter((r) => r.is_anomaly && r.Uncertainty_Score !== undefined)
            .sort((a, b) => (b.Uncertainty_Score || 0) - (a.Uncertainty_Score || 0));
          setActiveQueue(ambiguous);
        }

        // Process AG Grid (from Cleaned Data)
        if (cleanRes && cleanRes.data && cleanRes.data.data.length > 0) {
          const cleanData = cleanRes.data.data;
          const total = cleanRes.data.total_rows || cleanData.length;
          setColumnDefs(
            Object.keys(cleanData[0]).map((key) => ({
              field: key,
              sortable: true,
              filter: true,
            }))
          );
          setRowData(cleanData);
          setTotalRows(total);
        } else {
          setErrorMsg(
            'No cleaned data available for the grid. Complete the Cleaning step first, or note that your cleaning method may have removed all rows.'
          );
        }
      } catch (err: unknown) {
        const axiosErr = err as {
          response?: { data?: { error?: string; detail?: string } };
          message?: string;
        };
        const detail =
          axiosErr.response?.data?.error ||
          axiosErr.response?.data?.detail ||
          axiosErr.message ||
          'Failed to load dataset.';
        setErrorMsg(`Could not load the dataset: ${detail}`);
        console.error('ReviewEdit: Failed to load data', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [sessionId]);

  const defaultColDef = useMemo(
    () => ({ flex: 1, minWidth: 120, resizable: true, editable: true }),
    []
  );

  const handleDownload = () => {
    gridRef.current?.api.exportDataAsCsv({ fileName: 'DataSentinel_Cleaned.csv' });
  };

  const handleFeedback = async (originalIndex: number, label: 1 | 0) => {
    try {
      await api.post(`/api/feedback/${sessionId}`, { row_index: originalIndex, label });
      // Remove the reviewed item from the UI queue
      setActiveQueue((prev) => prev.filter((r) => r._originalIndex !== originalIndex));
    } catch (e) {
      console.error("Feedback submission failed", e);
    }
  };

  if (isLoading) {
    return (
      <div className="w-full mt-6 flex flex-col items-center justify-center h-64 border border-neutral-800 rounded-2xl bg-[#0A0A0A]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500 mb-4" />
        <p className="text-neutral-400">Loading Active Learning Module & Dataset...</p>
      </div>
    );
  }

  return (
    <div className="w-full mt-6 space-y-8">

      {/* ── ACTIVE LEARNING MODULE ── */}
      <div className="w-full space-y-4">
        <div className="mb-4">
          <h2 className="text-xl font-black text-white flex items-center gap-2">
            <BrainCircuit className="text-purple-500 w-6 h-6" />
            Active Learning Human-in-the-Loop
          </h2>
          <p className="text-neutral-400 text-sm mt-1">
            Uncertainty Sampling: The AI has identified these anomalies as sitting closest to the mathematical decision boundary. Your review tunes the threshold.
          </p>
        </div>

        <AnimatePresence>
          {activeQueue.slice(0, 3).map((row) => {
            const uScore = row.Uncertainty_Score || 0;
            const isCritical = uScore > 0.8;

            return (
              <motion.div
                key={row._originalIndex}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
                className={`bg-neutral-900/50 border ${isCritical ? 'border-purple-500/50 shadow-[0_0_15px_rgba(168,85,247,0.1)]' : 'border-neutral-800'} p-5 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-4`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2">
                    <span className={`px-2 py-1 text-[10px] font-bold uppercase tracking-widest rounded-md ${isCritical ? 'bg-purple-500/20 text-purple-400' : 'bg-neutral-800 text-neutral-400'}`}>
                      {isCritical ? 'High Uncertainty' : 'Medium Uncertainty'}
                    </span>
                    <span className="text-xs text-neutral-500 font-mono">U-Score: {uScore.toFixed(4)}</span>
                  </div>

                  <p className="text-sm text-neutral-300 mb-3 leading-relaxed">
                    <span className="font-bold text-white">AI Reason:</span> {row.AI_Reason || "Complex borderline anomaly."}
                  </p>

                  {row.SHAP_Payload && (
                    <div className="mb-3 bg-blue-500/10 border border-blue-500/20 p-2.5 rounded-lg flex items-start gap-2">
                      <Network className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-[10px] font-bold text-blue-400 uppercase tracking-wider mb-0.5">Causal Root Cause (NOTEARS DAG)</p>
                        <p className="text-xs text-blue-200 leading-relaxed font-mono">
                          {row.SHAP_Payload.replace(/[{}"']/g, '').replace(/,/g, ' | ')}
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="bg-black/40 border border-white/5 p-2 rounded-lg text-xs text-neutral-400 font-mono overflow-x-auto whitespace-nowrap">
                    {JSON.stringify(
                      Object.fromEntries(
                        Object.entries(row).filter(([k]) =>
                          !["is_anomaly", "AI_Reason", "Threat_Score", "Uncertainty_Score", "SHAP_Payload", "Counterfactual_Payload", "lof_score", "_originalIndex"].includes(k)
                        ).slice(0, 5)
                      )
                    ).replace(/[{}]/g, '')}
                  </div>
                </div>

                <div className="flex md:flex-col gap-2 shrink-0 w-full md:w-auto">
                  <button
                    onClick={() => handleFeedback(row._originalIndex, 1)}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 text-xs font-bold rounded-lg transition-colors"
                  >
                    <AlertTriangle className="w-3.5 h-3.5" /> Confirm Anomaly
                  </button>
                  <button
                    onClick={() => handleFeedback(row._originalIndex, 0)}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 text-xs font-bold rounded-lg transition-colors"
                  >
                    <Check className="w-3.5 h-3.5" /> False Positive
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {activeQueue.length === 0 && (
          <div className="text-center py-8 text-emerald-500 bg-emerald-500/5 rounded-xl border border-emerald-500/20">
            <CheckCircle className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="font-bold text-sm">No Ambiguous Cases Detected</p>
            <p className="text-xs opacity-80 mt-1">The system is highly confident in the current decision boundaries.</p>
          </div>
        )}
      </div>

      {/* ── AG GRID EDITOR ── */}
      {errorMsg ? (
        <div className="w-full bg-red-500/10 border border-red-900/50 p-6 rounded-2xl flex items-start text-red-400">
          <AlertCircle className="w-6 h-6 mr-3 shrink-0" />
          <div>
            <h3 className="font-bold text-lg mb-1">Grid Load Failed</h3>
            <p className="text-sm">{errorMsg}</p>
          </div>
        </div>
      ) : (
        <div className="w-full">
          <div className="flex justify-between items-center bg-neutral-900 border border-neutral-800 p-4 rounded-t-2xl">
            <div className="flex items-center text-sm text-neutral-400">
              <Edit3 className="w-4 h-4 mr-2" />
              Double-click any cell to manually edit before exporting.{' '}
              {rowData.length < totalRows
                ? `(Previewing ${rowData.length} of ${totalRows} rows)`
                : `(${totalRows} rows)`}
            </div>
            <button
              onClick={handleDownload}
              className="flex items-center px-4 py-2 bg-green-500 text-black text-sm font-medium rounded-lg hover:bg-green-400 transition-colors"
            >
              <Download className="w-4 h-4 mr-2" /> Download Final CSV
            </button>
          </div>

          <div
            className="ag-theme-alpine-dark w-full h-[500px] border-x border-b border-neutral-800 rounded-b-2xl overflow-hidden"
            data-lenis-prevent
          >
            <AgGridReact
              ref={gridRef}
              theme="legacy"
              rowData={rowData}
              columnDefs={columnDefs}
              defaultColDef={defaultColDef}
              pagination={true}
              paginationPageSize={100}
            />
          </div>
        </div>
      )}
    </div>
  );
}