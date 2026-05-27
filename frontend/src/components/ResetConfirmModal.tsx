"use client";

import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, RefreshCw, X, ArrowLeft } from "lucide-react";

interface ResetConfirmModalProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  isResetting: boolean;
}

export default function ResetConfirmModal({
  isOpen,
  onConfirm,
  onCancel,
  isResetting,
}: ResetConfirmModalProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            key="reset-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-[9998] bg-black/70 backdrop-blur-md"
            onClick={!isResetting ? onCancel : undefined}
          />

          {/* Modal */}
          <motion.div
            key="reset-modal"
            initial={{ opacity: 0, scale: 0.88, y: 24 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.88, y: 24 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="fixed inset-0 z-[9999] flex items-center justify-center p-6 pointer-events-none"
          >
            <div className="pointer-events-auto w-full max-w-md">
              <div className="relative bg-neutral-950 border border-white/10 rounded-[2rem] p-8 shadow-[0_0_80px_rgba(239,68,68,0.15),0_0_0_1px_rgba(239,68,68,0.1)] overflow-hidden">

                {/* Ambient glow */}
                <div className="absolute -top-16 left-1/2 -translate-x-1/2 w-48 h-48 bg-red-500/20 rounded-full blur-[60px] pointer-events-none" />
                <div className="absolute -bottom-12 -right-12 w-40 h-40 bg-orange-500/10 rounded-full blur-[50px] pointer-events-none" />

                {/* Close button */}
                {!isResetting && (
                  <button
                    onClick={onCancel}
                    className="absolute top-5 right-5 w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 transition-colors flex items-center justify-center text-neutral-400 hover:text-white"
                    aria-label="Cancel reset"
                  >
                    <X size={14} />
                  </button>
                )}

                {/* Icon */}
                <div className="relative z-10 flex flex-col items-center text-center">
                  <motion.div
                    animate={isResetting ? { rotate: 360 } : { rotate: [0, -8, 8, -8, 0] }}
                    transition={
                      isResetting
                        ? { duration: 1, repeat: Infinity, ease: "linear" }
                        : { duration: 0.5, delay: 0.2 }
                    }
                    className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(239,68,68,0.15)]"
                  >
                    {isResetting ? (
                      <RefreshCw size={28} className="text-red-400" />
                    ) : (
                      <AlertTriangle size={28} className="text-red-400" />
                    )}
                  </motion.div>

                  <h2 className="text-2xl font-black tracking-tight text-white mb-2">
                    {isResetting ? "Resetting Session…" : "Reset & Start Over?"}
                  </h2>

                  {!isResetting && (
                    <p className="text-neutral-400 text-sm leading-relaxed mb-8 max-w-xs">
                      This will permanently delete all data associated with your current session — including your uploaded dataset, detection results, cleaning operations, insights, and any exports. You&apos;ll be returned to the landing page to start fresh.
                    </p>
                  )}

                  {isResetting && (
                    <p className="text-neutral-500 text-sm mt-2 mb-8">
                      Purging session data and redirecting…
                    </p>
                  )}

                  {/* Destructive items list */}
                  {!isResetting && (
                    <ul className="w-full text-left space-y-2 mb-8 bg-white/[0.02] border border-white/5 rounded-2xl p-4">
                      {[
                        "Uploaded dataset & file",
                        "Anomaly detection results",
                        "AI insights & analysis",
                        "Cleaning & comparison data",
                        "Query history",
                        "Visualization data",
                        "Export & quality reports",
                      ].map((item) => (
                        <li key={item} className="flex items-center gap-2.5 text-xs text-neutral-400">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-500/60 shrink-0" />
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}

                  {/* Action Buttons */}
                  {!isResetting && (
                    <div className="w-full flex flex-col gap-3">
                      <button
                        id="reset-confirm-btn"
                        onClick={onConfirm}
                        className="w-full py-3.5 rounded-xl font-bold text-sm tracking-wide text-white bg-gradient-to-r from-red-600 to-red-500 hover:from-red-500 hover:to-red-400 transition-all shadow-[0_4px_20px_rgba(239,68,68,0.3)] hover:shadow-[0_4px_30px_rgba(239,68,68,0.5)] active:scale-95 flex items-center justify-center gap-2"
                      >
                        <RefreshCw size={15} />
                        Yes, Reset Everything
                      </button>
                      <button
                        id="reset-cancel-btn"
                        onClick={onCancel}
                        className="w-full py-3.5 rounded-xl font-bold text-sm tracking-wide text-neutral-300 bg-white/5 hover:bg-white/10 border border-white/5 hover:border-white/10 transition-all active:scale-95 flex items-center justify-center gap-2"
                      >
                        <ArrowLeft size={15} />
                        Keep Working
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
