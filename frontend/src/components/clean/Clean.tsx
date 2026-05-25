/* ─── Imports ────────────────────────────────────────────────────────────────────────────── */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Trash2,
  Scissors,
  CheckCircle,
  Loader2,
  Shield,
  EyeOff,
  Activity,
  X,
  AlertTriangle,
  Download,
  Info,
  Sparkles,
  Brain, // Added for RL Impute
} from 'lucide-react';
import api from '@/services/api.service';
import type { AnomalyRow, QuarantineResponse } from '@/types/api';

/* ─── Types & Constants ──────────────────────────────────────────────────────────────────── */

export interface CleanProps {
  sessionId: string;
  onComplete: () => void;
  recommendedMethod?: string;
  cleaningRationale?: string;
}

// Added new interfaces for RL Telemetry mapping
interface RecleanReport {
  state: string;
  action_taken: string;
  reward: number;
}

export interface CleanResponse {
  status: string;
  action_taken: string;
  original_rows: number;
  new_total: number;
  rows_delta: number;
  pii_cols_scrubbed: string[];
  reclean_report?: Record<string, RecleanReport>;
  total_reward?: number;
  error?: string;
}

const CLEANING_METHODS = [
  {
    id: 'quarantine',
    icon: Shield,
    title: 'Quarantine Protocol',
    techDesc: 'Moves anomalies to a secure audit file. Leaves main dataset perfectly clean.',
    analogy: 'The Evidence Room',
    simpleDesc: 'Safely removes bad data and locks it in a secure Vault for later review.',
    color: 'text-blue-400',
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    btnHover: 'hover:bg-blue-600',
  },
  {
    id: 'winsorize',
    icon: Scissors,
    title: 'Smart Winsorization',
    techDesc: 'Caps extreme numerical outliers to the 95th percentile. Prevents data loss.',
    analogy: 'The Speed Limit',
    simpleDesc: 'Caps crazy, impossible numbers (like a $10,000 toothbrush) at a normal maximum.',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
    btnHover: 'hover:bg-purple-600',
  },
  {
    id: 'mask',
    icon: EyeOff,
    title: 'Categorical Masking',
    techDesc: 'Overwrites malicious or anomalous text strings with [REDACTED] tags.',
    analogy: "The Censor's Marker",
    simpleDesc: 'Protects database by crossing out malicious text with a [REDACTED] tag.',
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    btnHover: 'hover:bg-yellow-600',
  },
  {
    id: 'impute',
    icon: Brain, // Swapped to Brain to reflect the RL AI
    title: 'Autonomous RL Imputation',
    techDesc: 'ReClean MDP Agent: Dynamically selects KNN, Mean, or Median based on Q-Learning states to maximize downstream variance.',
    analogy: 'The AI Surgeon',
    simpleDesc: 'Uses Reinforcement Learning to autonomously decide the best way to heal corrupted data without destroying it.',
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/30',
    btnHover: 'hover:bg-emerald-600',
  },
  {
    id: 'drop',
    icon: Trash2,
    title: 'Hard Drop',
    techDesc: 'Permanently deletes anomalous rows. Destructive but ensures strict data integrity.',
    analogy: 'The Bouncer',
    simpleDesc: 'Permanently deletes the corrupted row. Only use if data is 100% useless junk.',
    color: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    btnHover: 'hover:bg-red-600',
  },
];

/* ─── Helpers ────────────────────────────────────────────────────────────────────────────── */

const escapeCsvCell = (val: unknown): string => {
  const strValue = val === null || val === undefined ? '' : String(val);
  const needsQuoting = strValue.includes(',') || strValue.includes('"') || strValue.includes('\n');
  return needsQuoting ? `"${strValue.replace(/"/g, '""')}"` : strValue;
};

const downloadAuditCsv = (auditData: AnomalyRow[]) => {
  if (auditData.length === 0) return;
  const headers = Object.keys(auditData[0] || {}).map(escapeCsvCell).join(',');
  const rows = auditData.map((row) =>
    Object.values(row).map(escapeCsvCell).join(',')
  );
  const csvContent = [headers, ...rows].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'quarantine_audit.csv';
  link.click();
  URL.revokeObjectURL(url);
};

/* ─── Components ─────────────────────────────────────────────────────────────────────────── */

function QuarantineVaultModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const [auditData, setAuditData] = useState<AnomalyRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchVault = async () => {
      try {
        const res = await api.get<QuarantineResponse>(`/api/quarantine/${sessionId}`);
        setAuditData(res.data.data || []);
      } catch (err) {
        console.error('Failed to fetch quarantine vault', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchVault();
  }, [sessionId]);

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="flex flex-col items-center justify-center h-64">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin mb-4" />
          <p className="text-neutral-400 font-medium">Decrypting Vault Records...</p>
        </div>
      );
    }
    if (auditData.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center h-64 text-neutral-500">
          <CheckCircle className="w-12 h-12 mb-2 opacity-50" />
          <p>Vault is empty. No anomalies quarantined.</p>
        </div>
      );
    }
    return (
      <table className="w-full text-left border-collapse">
        <thead className="bg-[#111] sticky top-0 z-10 border-b border-neutral-800">
          <tr>
            <th className="p-4 text-xs font-bold text-neutral-400 uppercase tracking-wider">Threat Level</th>
            <th className="p-4 text-xs font-bold text-neutral-400 uppercase tracking-wider w-1/3">AI Justification</th>
            <th className="p-4 text-xs font-bold text-neutral-400 uppercase tracking-wider">Raw Data Fragment</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800/50">
          {auditData.map((row, i) => (
            <tr key={i} className="hover:bg-neutral-900/50 transition-colors">
              <td className="p-4">
                <div className="flex items-center">
                  <AlertTriangle className={`w-4 h-4 mr-2 ${row.Threat_Score > 80 ? 'text-red-500' : 'text-yellow-500'}`} />
                  <span className={`font-bold ${row.Threat_Score > 80 ? 'text-red-400' : 'text-yellow-400'}`}>
                    {row.Threat_Score}%
                  </span>
                </div>
              </td>
              <td className="p-4 text-sm text-neutral-300 leading-relaxed border-l border-neutral-800/50 bg-[#111111]/30">
                {row.AI_Reason || 'Complex mathematical anomaly detected.'}
              </td>
              <td className="p-4 text-xs text-neutral-500 font-mono overflow-hidden">
                {JSON.stringify(
                  Object.fromEntries(
                    Object.entries(row)
                      .filter(([k]) => !['is_anomaly', 'AI_Reason', 'Threat_Score'].includes(k))
                      .slice(0, 3)
                  )
                ).substring(0, 60)}...
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-[#0A0A0A] border border-neutral-800 rounded-2xl shadow-2xl w-full max-w-6xl max-h-[85vh] flex flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between p-6 border-b border-neutral-800 bg-[#050505]">
          <div className="flex items-center">
            <Shield className="w-6 h-6 text-blue-400 mr-3" />
            <div>
              <h2 className="text-xl font-bold text-white">Quarantine Vault Audit Log</h2>
              <p className="text-xs text-neutral-500">Viewing isolated anomalies removed from the main pipeline.</p>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            <button
              onClick={() => downloadAuditCsv(auditData)}
              disabled={auditData.length === 0}
              className="flex items-center text-xs font-bold text-neutral-300 hover:text-white bg-neutral-800 hover:bg-neutral-700 px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              <Download className="w-4 h-4 mr-2" />
              Export Audit CSV
            </button>
            <button onClick={onClose} className="p-2 text-neutral-500 hover:text-white transition-colors">
              <X className="w-6 h-6" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-0" data-lenis-prevent>
          {renderContent()}
        </div>
      </motion.div>
    </div>
  );
}

/**
 * Clean component for sanitizing datasets with anomalies.
 * Allows user to choose a cleaning method like Quarantine, Masking, RL Impute, etc.
 */
export default function Clean({
  sessionId,
  onComplete,
  recommendedMethod = 'quarantine',
  cleaningRationale,
}: CleanProps): React.JSX.Element {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [result, setResult] = useState<CleanResponse | null>(null); // Replaced successMsg with full result payload
  const [showVault, setShowVault] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleClean = async (action: string) => {
    setLoadingAction(action);
    setErrorMsg(null);
    try {
      const res = await api.post<CleanResponse>(`/api/clean/${sessionId}?action=${action}`);
      if (res.data.error) {
        setErrorMsg(res.data.error);
      } else {
        setResult(res.data);
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
        'An unknown error occurred during cleaning.';
      console.error('DataSentinel: Clean failed —', detail);
      setErrorMsg(`Cleaning failed: ${detail}`);
    } finally {
      setLoadingAction(null);
    }
  };

  // SUCCESS / RESULTS SCREEN
  if (result) {
    const isRL = result.action_taken === "impute" && result.reclean_report;

    return (
      <div className="w-full mt-6 space-y-6">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="p-6 bg-green-500/10 border border-green-500/20 rounded-2xl flex items-start gap-4"
        >
          <CheckCircle className="w-10 h-10 text-green-400 shrink-0" />
          <div>
            <h3 className="text-2xl font-bold text-white mb-2">Dataset Successfully Sanitized</h3>
            <p className="text-green-400/80">
              Action executed: <span className="font-mono text-green-300 font-bold">{result.action_taken.toUpperCase()}</span>.
              Zero-leak PII scanner successfully reviewed the outgoing payload.
            </p>
          </div>
        </motion.div>

        {/* METRICS GRID */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="p-5 bg-neutral-900/60 border border-white/5 rounded-2xl backdrop-blur-xl">
            <p className="text-xs font-bold text-neutral-500 uppercase tracking-widest mb-2">Rows Preserved</p>
            <p className="text-3xl font-black text-white">{result.new_total.toLocaleString()}</p>
            <p className="text-xs text-neutral-400 mt-1">Out of {result.original_rows.toLocaleString()} original</p>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="p-5 bg-neutral-900/60 border border-white/5 rounded-2xl backdrop-blur-xl">
            <p className="text-xs font-bold text-neutral-500 uppercase tracking-widest mb-2">Rows Delta</p>
            <p className="text-3xl font-black text-rose-400">{result.rows_delta.toLocaleString()}</p>
            <p className="text-xs text-neutral-400 mt-1">Total volume shifted</p>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="p-5 bg-neutral-900/60 border border-white/5 rounded-2xl backdrop-blur-xl">
            <p className="text-xs font-bold text-neutral-500 uppercase tracking-widest mb-2">PII Columns Vaulted</p>
            <p className="text-3xl font-black text-cyan-400">{result.pii_cols_scrubbed?.length || 0}</p>
            <p className="text-xs text-neutral-400 mt-1">SHA-256 pseudonymised</p>
          </motion.div>
        </div>

        {/* RL TELEMETRY DASHBOARD */}
        {isRL && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="bg-neutral-900/60 border border-emerald-500/30 rounded-2xl p-6 backdrop-blur-xl"
          >
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-emerald-500/20 rounded-lg"><Brain className="w-5 h-5 text-emerald-400" /></div>
                <div>
                  <h3 className="text-lg font-bold text-white">ReClean RL Agent Telemetry</h3>
                  <p className="text-xs text-neutral-400">Markov Decision Process (MDP) Execution Log</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-neutral-500 uppercase tracking-widest">Episode Reward</p>
                <p className="text-2xl font-black text-emerald-400 font-mono">{result.total_reward?.toFixed(4)}</p>
              </div>
            </div>

            <div className="space-y-3">
              {Object.entries(result.reclean_report!).filter(([k]) => k !== "info" && k !== "total_reward").map(([col, report], i) => {
                const isHighReward = report.reward > 0.8;
                const isMedReward = report.reward > 0.5 && report.reward <= 0.8;
                return (
                  <motion.div key={col} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 + (i * 0.1) }} className="grid grid-cols-4 gap-4 items-center bg-black/40 border border-white/5 rounded-xl p-4">
                    <div className="col-span-1">
                      <p className="text-xs text-neutral-500">Feature</p>
                      <p className="text-sm font-bold text-white truncate">{col}</p>
                    </div>
                    <div className="col-span-1 border-l border-white/10 pl-4">
                      <p className="text-xs text-neutral-500">Agent State</p>
                      <p className="text-sm font-mono text-cyan-400">{report.state}</p>
                    </div>
                    <div className="col-span-1 border-l border-white/10 pl-4">
                      <p className="text-xs text-neutral-500">Action Policy</p>
                      <p className="text-sm font-mono text-emerald-400">{report.action_taken}</p>
                    </div>
                    <div className="col-span-1 border-l border-white/10 pl-4 text-right">
                      <p className="text-xs text-neutral-500">KS-Reward</p>
                      <p className={`text-lg font-black font-mono ${isHighReward ? "text-emerald-400" : isMedReward ? "text-yellow-400" : "text-red-400"}`}>
                        +{report.reward.toFixed(4)}
                      </p>
                    </div>
                  </motion.div>
                );
              })}
            </div>
            <p className="text-xs text-neutral-500 mt-4 italic">
              * Reward is formulated as the inverse Kolmogorov-Smirnov distance (1.0 - KS Stat). Higher rewards mean the downstream data distribution was perfectly preserved.
            </p>
          </motion.div>
        )}

        <div className="flex justify-end pt-4 space-x-4">
          <button
            onClick={() => setShowVault(true)}
            className="px-6 py-3 bg-neutral-800 hover:bg-neutral-700 text-white font-bold rounded-xl transition-colors border border-neutral-700 flex items-center"
          >
            <Shield className="w-5 h-5 mr-2 text-blue-400" />
            Open Quarantine Vault
          </button>
          <button
            onClick={onComplete}
            className="px-6 py-3 bg-green-600 hover:bg-green-500 text-white font-bold rounded-xl transition-colors flex items-center"
          >
            Continue to Export →
          </button>
        </div>

        <AnimatePresence>
          {showVault && <QuarantineVaultModal sessionId={sessionId} onClose={() => setShowVault(false)} />}
        </AnimatePresence>
      </div>
    );
  }

  // DEFAULT / SELECTION SCREEN
  return (
    <div className="w-full mt-6">
      {cleaningRationale && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 p-6 bg-blue-500/10 border border-blue-500/30 rounded-2xl flex items-start shadow-[0_0_30px_rgba(59,130,246,0.1)]"
        >
          <Sparkles className="w-8 h-8 text-blue-400 mr-4 shrink-0 mt-1" />
          <div>
            <h3 className="text-lg font-bold text-white mb-1">
              AI Recommended Action: {recommendedMethod.charAt(0).toUpperCase() + recommendedMethod.slice(1)}
            </h3>
            <p className="text-blue-200 text-sm leading-relaxed">{cleaningRationale}</p>
          </div>
        </motion.div>
      )}

      {errorMsg && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 p-5 bg-red-500/10 border border-red-500/30 rounded-2xl flex items-start"
        >
          <AlertTriangle className="w-6 h-6 text-red-400 mr-3 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="text-sm font-bold text-red-400 mb-1">Operation Failed</h3>
            <p className="text-red-300/80 text-sm leading-relaxed">{errorMsg}</p>
          </div>
          <button onClick={() => setErrorMsg(null)} className="p-1 text-red-400 hover:text-white transition-colors ml-4">
            <X className="w-4 h-4" />
          </button>
        </motion.div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 perspective-[1000px]">
        {CLEANING_METHODS.map((method) => {
          const Icon = method.icon;
          const isRecommended = method.id === recommendedMethod;
          return (
            <div key={method.id} className="group relative w-full h-[280px] [perspective:1000px]">
              <div className="w-full h-full transition-transform duration-500 [transform-style:preserve-3d] group-hover:[transform:rotateY(180deg)]">

                {/* FRONT OF CARD */}
                <div className={`absolute inset-0 [backface-visibility:hidden] group-hover:pointer-events-none bg-neutral-900 border ${isRecommended ? 'border-blue-500/50 shadow-[0_0_20px_rgba(59,130,246,0.2)]' : 'border-neutral-800'} p-8 rounded-2xl flex flex-col`}>
                  {isRecommended && (
                    <div className="absolute top-0 right-0 bg-blue-500 text-white text-xs font-bold px-4 py-1.5 rounded-bl-lg rounded-tr-xl uppercase tracking-wider z-10 shadow-lg">
                      AI Pick
                    </div>
                  )}
                  <div className="flex items-center justify-between mb-6">
                    <div className={`w-12 h-12 ${method.bg} rounded-xl flex items-center justify-center`}>
                      <Icon className={`w-6 h-6 ${method.color}`} />
                    </div>
                    <div className="flex items-center text-neutral-500 text-xs">
                      <Info className="w-4 h-4 mr-1" /> Hover to learn
                    </div>
                  </div>
                  <h3 className="text-xl font-semibold mb-2">{method.title}</h3>
                  <p className="text-neutral-400 text-sm flex-1">{method.techDesc}</p>
                </div>

                {/* BACK OF CARD */}
                <div className={`absolute inset-0 [backface-visibility:hidden] [transform:rotateY(180deg)] pointer-events-none group-hover:pointer-events-auto bg-neutral-800 border ${method.border} p-8 rounded-2xl flex flex-col justify-between`}>
                  <div>
                    <div className="flex items-center mb-3">
                      <Icon className={`w-5 h-5 mr-2 ${method.color}`} />
                      <h3 className={`text-lg font-bold ${method.color}`}>&quot;{method.analogy}&quot;</h3>
                    </div>
                    <p className="text-white text-sm leading-relaxed">{method.simpleDesc}</p>
                  </div>
                  <button
                    onClick={() => handleClean(method.id)}
                    disabled={!!loadingAction}
                    className={`w-full py-3 mt-4 text-white font-bold rounded-lg transition-colors flex justify-center items-center shadow-lg ${isRecommended ? 'bg-blue-600 hover:bg-blue-500' : `bg-neutral-900 ${method.btnHover}`}`}
                  >
                    {loadingAction === method.id ? (
                      <Loader2 className="w-5 h-5 animate-spin" />
                    ) : (
                      `Apply ${method.id.charAt(0).toUpperCase() + method.id.slice(1)}`
                    )}
                  </button>
                </div>

              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Exports ────────────────────────────────────────────────────────────────────────────── */