"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { UploadCloud, AlertOctagon, ArrowRight, ShieldCheck, Terminal, Zap, CheckCircle, Brain } from "lucide-react";
import { AxiosError } from "axios";
import api from "@/services/api.service";
import type { UploadResponse } from "@/types/api";

interface SampleDataset {
  filename: string;
  name: string;
  rows: number;
  anomalies: number;
  description: string;
  icon: string;
}

// ── Components ──
import HeroLanding from "@/components/landing/HeroLanding";
import NeuralCore from "@/components/landing/NeuralCore";
import AmbientAurora from "@/components/landing/AmbientAurora";
import PIIModal from "@/components/pii-modal";
import type { PIIFinding } from "@/components/pii-modal/PIIModal";

// ── Custom High-Tech Loader Animation ──
const QuantumLoader = () => (
  <div className="relative w-5 h-5 flex items-center justify-center shrink-0">
    <motion.div
      className="absolute inset-0 border-2 border-cyan-500/20 border-t-cyan-400 rounded-full"
      animate={{ rotate: 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
    />
    <motion.div
      className="absolute inset-[3px] border-2 border-purple-500/20 border-b-purple-400 rounded-full"
      animate={{ rotate: -360 }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
    />
    <div className="w-1 h-1 bg-cyan-300 rounded-full animate-pulse shadow-[0_0_8px_#67e8f9]" />
  </div>
);

export default function Home() {
  const router = useRouter();

  // ── State Management ──
  const [isUploading, setIsUploading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadedBytes, setUploadedBytes] = useState<{ loaded: number, total: number } | null>(null);

  const [processingStatus, setProcessingStatus] = useState<string>("");
  const [statusHistory, setStatusHistory] = useState<string[]>([]);

  const [contractErrors, setContractErrors] = useState<string[] | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [piiFindings, setPiiFindings] = useState<PIIFinding[]>([]);
  const [showPIIModal, setShowPIIModal] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [samples, setSamples] = useState<SampleDataset[]>([]);

  useEffect(() => {
    api.get('/api/samples').then(res => setSamples(res.data.samples)).catch(console.error);
  }, []);

  const formatMB = (bytes: number) => (bytes / (1024 * 1024)).toFixed(1);

  const pollStatus = async (sid: string) => {
    try {
      const res = await api.get(`/api/status/${sid}`);
      const data = res.data;
      if (data.status === "completed") {
         checkPiiAndProceed(sid);
      } else if (data.status === "error") {
         setUploadError(data.error);
         setIsUploading(false);
         setUploadProgress(0);
      } else {
         setStatusHistory(prev => {
           const last = prev[prev.length - 1];
           if (last !== data.status && data.status) {
             const newHistory = [...prev, data.status];
             return newHistory.slice(-3);
           }
           return prev;
         });
         if (data.status) setProcessingStatus(data.status);
         setTimeout(() => pollStatus(sid), 1000);
      }
    } catch (e) {
      setTimeout(() => pollStatus(sid), 1000);
    }
  };

  const checkPiiAndProceed = async (sid: string) => {
    try {
      const piiRes = await api.get(`/api/pii-scan/${sid}`);
      if (piiRes.data.pii_detected) { 
        setPiiFindings(piiRes.data.findings); 
        setShowPIIModal(true); 
      }
      else { 
        router.push(`/${sid}/detect`); 
      }
    } catch {
      router.push(`/${sid}/detect`);
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
      setStatusHistory([]);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) await processUpload(e.target.files[0]);
  };

  const processUpload = async (uploadFile: File) => {
    setIsUploading(true); setUploadError(null); setContractErrors(null);
    setUploadProgress(0); setUploadedBytes(null); setStatusHistory([]);
    setProcessingStatus("");

    const formData = new FormData(); formData.append("file", uploadFile);

    try {
      const response = await api.post<UploadResponse>("/api/upload/", formData, {
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percentCompleted);
            setUploadedBytes({ loaded: progressEvent.loaded, total: progressEvent.total });

            if (percentCompleted === 100) {
              setProcessingStatus("File transferred. Server digesting dataset payload...");
            }
          }
        },
      });

      const sid = response.data.session_id; setSessionId(sid);
      pollStatus(sid);

    } catch (err: unknown) {
      const axiosErr = err as AxiosError<{ error?: string; errors?: string[] }>;
      if (axiosErr.response?.status === 400 && axiosErr.response?.data?.errors?.length) setContractErrors(axiosErr.response.data.errors);
      else setUploadError(axiosErr.response?.data?.error || "Unknown error occurred");
      setIsUploading(false); setUploadProgress(0);
    }
  };

  const loadSample = async (filename: string) => {
    setIsUploading(true); setUploadError(null); setContractErrors(null); setStatusHistory([]);
    setUploadProgress(100);
    setProcessingStatus("File transferred. Server digesting dataset payload...");

    try {
      const response = await api.post<UploadResponse>(`/api/load-sample/${filename}`);
      const sid = response.data.session_id; setSessionId(sid);
      pollStatus(sid);

    } catch (err: unknown) {
      const axiosErr = err as AxiosError<{ error?: string; errors?: string[] }>;
      if (axiosErr.response?.status === 400 && axiosErr.response?.data?.errors?.length) setContractErrors(axiosErr.response.data.errors);
      else setUploadError(axiosErr.response?.data?.error || "Unknown error occurred");
      setIsUploading(false); setUploadProgress(0);
    }
  };

  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (uploadProgress / 100) * circumference;

  return (
    <main className="min-h-screen bg-black text-white flex flex-col font-sans selection:bg-purple-500 selection:text-white overflow-clip">
      <motion.header
        initial={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed top-0 left-0 w-full p-6 z-50 flex justify-between items-center mix-blend-difference pointer-events-none"
      >
        <div className="text-xl font-black tracking-tighter">DATA<span className="text-purple-500">SENTINEL</span></div>
      </motion.header>

      <AnimatePresence mode="wait">
        <motion.div
          key="landing"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.5 } }}
          className="w-full"
        >
          <HeroLanding />

          <div className="relative w-full bg-black text-white py-32 px-6 md:px-12 lg:px-24 max-w-[1400px] mx-auto flex flex-col md:flex-row items-start gap-12 lg:gap-24 border-t border-white/5">
            <NeuralCore />
            <div className="md:w-1/3 sticky top-32 pt-10 relative z-10">
              <h2 className="text-sm font-bold uppercase tracking-[0.2em] text-purple-500 mb-4 flex items-center gap-2">
                <Brain className="w-4 h-4" /> The Architecture
              </h2>
              <h3 className="text-4xl md:text-5xl lg:text-6xl font-black tracking-tight leading-[1.1] mb-6">
                Built for the <br /> Age of AI.
              </h3>
              <p className="text-neutral-400 text-lg md:text-xl font-medium leading-relaxed">
                Legacy tools buckle under modern data volume. DataSentinel fuses deterministic logic with Groq-accelerated AI to clean data at the speed of thought.
              </p>
            </div>
            <div className="md:w-2/3 flex flex-col gap-8 md:gap-12 pt-10 md:pt-32 pb-32 relative z-10">
              <motion.div initial={{ opacity: 0, y: 50 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} className="bg-neutral-900/40 border border-white/5 p-8 md:p-12 rounded-[2rem] hover:bg-neutral-900/60 hover:border-purple-500/30 transition-colors group backdrop-blur-sm">
                <div className="w-14 h-14 bg-rose-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform"><ShieldCheck className="w-7 h-7 text-rose-500" /></div>
                <h4 className="text-3xl font-bold mb-4 tracking-tight">Zero-Leak PII Vault</h4>
                <p className="text-neutral-400 text-lg leading-relaxed">Before a single byte is analyzed, our local edge-scanner identifies and cryptographically vaults personal identities. Your sensitive data never hits the cloud.</p>
              </motion.div>
              <motion.div initial={{ opacity: 0, y: 50 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} className="bg-neutral-900/40 border border-white/5 p-8 md:p-12 rounded-[2rem] hover:bg-neutral-900/60 hover:border-purple-500/30 transition-colors group backdrop-blur-sm">
                <div className="w-14 h-14 bg-emerald-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform"><Terminal className="w-7 h-7 text-emerald-500" /></div>
                <h4 className="text-3xl font-bold mb-4 tracking-tight">Neuro-Symbolic Logic</h4>
                <p className="text-neutral-400 text-lg leading-relaxed">We don&apos;t just guess. DataSentinel combines strict, dynamic mathematical rules with semantic AI evaluation to automatically reject impossible realities in your dataset.</p>
              </motion.div>
              <motion.div initial={{ opacity: 0, y: 50 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} className="bg-neutral-900/40 border border-white/5 p-8 md:p-12 rounded-[2rem] hover:bg-neutral-900/60 hover:border-purple-500/30 transition-colors group backdrop-blur-sm">
                <div className="w-14 h-14 bg-cyan-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform"><Zap className="w-7 h-7 text-cyan-500" /></div>
                <h4 className="text-3xl font-bold mb-4 tracking-tight">Groq LPU Acceleration</h4>
                <p className="text-neutral-400 text-lg leading-relaxed">Powered by Llama 3.3 70B running on Groq&apos;s Language Processing Units. Generate complex SQL queries, statistical profiles, and narrative insights in literal milliseconds.</p>
              </motion.div>
            </div>
          </div>

          <div className="relative w-full min-h-screen flex flex-col items-center justify-center py-24 px-4 border-t border-white/5">

            <AmbientAurora />

            <motion.div initial={{ opacity: 0, y: 50 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} className="w-full max-w-2xl flex flex-col items-center justify-center bg-neutral-900/40 backdrop-blur-3xl p-10 rounded-[2.5rem] border border-white/10 shadow-[0_0_100px_rgba(168,85,247,0.15)] relative z-10">
              <h1 className="text-4xl md:text-5xl font-black tracking-tighter mb-8 text-center">Flawless Data. <br /><span className="text-purple-500">Ready for Production.</span></h1>

              <div className={`w-full border border-dashed ${isUploading ? 'border-transparent bg-transparent' : 'border-white/20 bg-white/[0.02] hover:bg-white/[0.05] cursor-pointer hover:border-purple-500/50'} rounded-[2rem] p-8 min-h-[280px] transition-all duration-500 flex flex-col items-center justify-center group relative overflow-hidden`}
                onClick={() => !isUploading && fileInputRef.current?.click()}
              >
                <input type="file" className="hidden" accept=".csv,.xlsx,.xls,.json" ref={fileInputRef} onChange={handleFileChange} disabled={isUploading} />

                {isUploading ? (
                  <div className="flex flex-col items-center justify-center w-full h-full z-10">
                    <AnimatePresence mode="wait">
                      {uploadProgress < 100 ? (
                        <motion.div
                          key="uploading-ring"
                          initial={{ opacity: 0, scale: 0.9 }}
                          animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.9, filter: "blur(10px)" }}
                          className="flex flex-col items-center"
                        >
                          <div className="relative w-32 h-32 mb-6 flex items-center justify-center">
                            <svg className="absolute inset-0 w-full h-full transform -rotate-90">
                              <circle cx="64" cy="64" r={radius} className="stroke-neutral-800" strokeWidth="8" fill="transparent" />
                            </svg>
                            <svg className="absolute inset-0 w-full h-full transform -rotate-90 drop-shadow-[0_0_12px_rgba(34,211,238,0.4)]">
                              <motion.circle
                                cx="64" cy="64" r={radius}
                                className="stroke-cyan-400"
                                strokeWidth="8" fill="transparent"
                                strokeDasharray={circumference}
                                initial={{ strokeDashoffset: circumference }}
                                animate={{ strokeDashoffset }}
                                transition={{ ease: "linear", duration: 0.2 }}
                                strokeLinecap="round"
                              />
                            </svg>
                            <span className="text-3xl font-black text-cyan-400 font-mono tracking-tighter">{uploadProgress}%</span>
                          </div>
                          <p className="font-mono text-sm tracking-wide text-cyan-500">
                            {uploadedBytes ? `${formatMB(uploadedBytes.loaded)}MB / ${formatMB(uploadedBytes.total)}MB Transferred` : "Establishing Secure Uplink..."}
                          </p>
                        </motion.div>
                      ) : (
                        <motion.div
                          key="processing-terminal"
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="w-full bg-black/80 border border-cyan-900/50 rounded-xl p-6 shadow-[inset_0_0_30px_rgba(6,182,212,0.05)]"
                        >
                          <div className="flex items-center gap-3 mb-4 border-b border-cyan-900/30 pb-3">
                            <QuantumLoader />
                            <span className="text-sm font-bold uppercase tracking-widest text-cyan-400">Engine Telemetry</span>
                          </div>

                          <div className="space-y-2 mb-3 h-[70px] overflow-hidden flex flex-col justify-end relative">
                            {(statusHistory.length === 0 || processingStatus === "File transferred. Server digesting dataset payload...") && (
                              <motion.div
                                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                                className="absolute inset-0 flex flex-col justify-end pb-2 space-y-2 pointer-events-none"
                              >
                                <div className="h-1.5 w-3/4 bg-cyan-900/40 rounded animate-pulse" />
                                <div className="h-1.5 w-1/2 bg-cyan-900/40 rounded animate-pulse" style={{ animationDelay: '150ms' }} />
                                <div className="h-1.5 w-5/6 bg-cyan-900/40 rounded animate-pulse" style={{ animationDelay: '300ms' }} />
                              </motion.div>
                            )}

                            <AnimatePresence initial={false}>
                              {statusHistory.map((status, i) => (
                                <motion.p
                                  key={`${status}-${i}`}
                                  initial={{ opacity: 0, x: -10 }}
                                  animate={{ opacity: 0.5, x: 0 }}
                                  className="font-mono text-xs text-cyan-600 flex items-center relative z-10"
                                >
                                  <CheckCircle className="w-3.5 h-3.5 mr-2 shrink-0" /> <span className="truncate">{status}</span>
                                </motion.p>
                              ))}
                            </AnimatePresence>
                          </div>

                          <motion.p
                            key={processingStatus}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="font-mono text-sm text-cyan-300 flex items-center"
                          >
                            <span className="mr-2 text-cyan-500 animate-pulse">❯</span> <span className="truncate">{processingStatus}</span>
                          </motion.p>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ) : (
                  <div className="flex flex-col items-center">
                    <div className="p-4 bg-white/5 rounded-full mb-4 group-hover:bg-purple-500/20 transition-colors">
                      <UploadCloud className="w-8 h-8 text-neutral-300 group-hover:text-purple-400 transition-colors" />
                    </div>
                    <p className="text-xl font-medium mb-2 tracking-tight">Secure Upload</p>
                    <p className="text-sm text-neutral-500">Drop your CSV, JSON, or Excel file here.</p>
                  </div>
                )}

                {isUploading && uploadProgress < 100 && (
                  <motion.div
                    className="absolute inset-0 bg-cyan-500/5 pointer-events-none rounded-[2rem]"
                    animate={{ opacity: [0, 0.5, 0] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  />
                )}
              </div>

              {!isUploading && samples.length > 0 && (
                <div className="w-full mt-8 grid grid-cols-1 md:grid-cols-2 gap-3">
                  {samples.map((sample) => (
                    <div key={sample.filename} className="bg-white/[0.02] border border-white/5 p-4 rounded-2xl cursor-pointer hover:bg-white/[0.06] hover:border-white/10 transition-all flex items-center justify-between group/card" onClick={() => loadSample(sample.filename)}>
                      <div className="flex items-center gap-3"><span className="text-2xl">{sample.icon}</span><h4 className="font-medium text-sm text-neutral-200">{sample.name}</h4></div>
                      <ArrowRight size={14} className="text-neutral-600 group-hover/card:text-purple-500" />
                    </div>
                  ))}
                </div>
              )}
              {uploadError && (
                <div className="w-full mt-4 p-4 bg-red-500/10 border border-red-500/30 rounded-2xl text-center">
                  <p className="text-red-400 text-sm font-medium">{uploadError}</p>
                </div>
              )}
            </motion.div>
          </div>
        </motion.div>
      </AnimatePresence>

      <AnimatePresence>
        {contractErrors && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="bg-neutral-900 border border-red-500/30 rounded-3xl p-6 max-w-lg shadow-2xl">
              <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2"><AlertOctagon className="text-red-500" /> Data Contract Violation</h2>
              <ul className="space-y-2 mb-6">{contractErrors.map((e, i) => <li key={i} className="text-neutral-400 text-sm">{e}</li>)}</ul>
              <button onClick={() => setContractErrors(null)} className="w-full py-3 bg-neutral-800 hover:bg-neutral-700 transition-colors text-white font-bold rounded-xl">Acknowledge</button>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showPIIModal && piiFindings.length > 0 && sessionId && (
          <PIIModal sessionId={sessionId} findings={piiFindings} onDismiss={() => { setShowPIIModal(false); router.push(`/${sessionId}/detect`); }} onPseudonymised={() => { setShowPIIModal(false); router.push(`/${sessionId}/detect`); }} />
        )}
      </AnimatePresence>
    </main>
  );
}