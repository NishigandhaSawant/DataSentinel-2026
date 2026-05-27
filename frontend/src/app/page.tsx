"use client";

import { useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence, useScroll, useTransform } from "framer-motion";
import { ShieldCheck, Terminal, Zap, Brain, ArrowRight } from "lucide-react";

// ── Components ──
import HeroLanding from "@/components/landing/HeroLanding";
import NeuralCore from "@/components/landing/NeuralCore";

const ScrollyTellingFinale = () => {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  // Using 300vh for a smoother, faster scroll experience through the finale
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ["start start", "end end"] });
  
  // Stage 1: The Ambient Ignition
  const glowOpacity = useTransform(scrollYProgress, [0, 0.4], [0, 1]);
  const glowScale = useTransform(scrollYProgress, [0, 0.4], [0.5, 1.2]);
  
  // Stage 2: The Core Ring
  const ringOpacity = useTransform(scrollYProgress, [0.2, 0.5], [0, 1]);
  const ringScale = useTransform(scrollYProgress, [0.2, 0.8], [0.8, 1]);
  const ringRotate = useTransform(scrollYProgress, [0, 1], [0, 180]);
  
  // Stage 3: The Statement
  const textOpacity = useTransform(scrollYProgress, [0.5, 0.7, 0.9], [0, 1, 0]);
  const textY = useTransform(scrollYProgress, [0.5, 0.7], [30, 0]);
  
  // Stage 4: The CTA Reveal
  const ctaOpacity = useTransform(scrollYProgress, [0.85, 0.95], [0, 1]);
  const ctaScale = useTransform(scrollYProgress, [0.85, 0.95], [0.8, 1]);
  const ctaY = useTransform(scrollYProgress, [0.85, 0.95], [20, 0]);
  
  return (
    <div ref={containerRef} className="h-[300vh] w-full relative bg-black border-t border-white/5">
      <div className="sticky top-0 h-screen w-full flex items-center justify-center overflow-hidden">
        
        {/* The Ambient Ignition */}
        <motion.div 
          style={{ opacity: glowOpacity, scale: glowScale }}
          className="absolute w-[60vw] h-[60vw] max-w-[800px] max-h-[800px] bg-gradient-to-tr from-purple-600/20 via-cyan-500/10 to-transparent blur-[120px] rounded-full pointer-events-none"
        />

        {/* The Core Ring */}
        <motion.div 
          style={{ opacity: ringOpacity, scale: ringScale, rotate: ringRotate }}
          className="absolute w-[24rem] h-[24rem] rounded-full border border-white/10 shadow-[inset_0_0_60px_rgba(255,255,255,0.02),0_0_60px_rgba(168,85,247,0.05)] flex items-center justify-center pointer-events-none"
        >
           <div className="w-full h-full rounded-full border-t border-cyan-400/30" />
           <div className="absolute w-[80%] h-[80%] rounded-full border-b border-purple-500/30" />
        </motion.div>

        {/* The Statement */}
        <motion.div 
          style={{ opacity: textOpacity, y: textY }}
          className="absolute flex flex-col items-center justify-center pointer-events-none"
        >
           <h2 className="text-6xl md:text-8xl font-black tracking-tighter text-transparent bg-clip-text bg-gradient-to-b from-white to-white/40 text-center leading-[1.1]">
             Absolute <br /> Clarity.
           </h2>
           <p className="mt-8 text-cyan-400 font-mono tracking-[0.3em] uppercase text-sm drop-shadow-[0_0_10px_rgba(34,211,238,0.5)]">
             DataSentinel Online
           </p>
        </motion.div>
        
        {/* CTA Button */}
        <motion.div style={{ opacity: ctaOpacity, scale: ctaScale, y: ctaY }} className="absolute z-50 flex items-center justify-center">
           <button 
             onClick={() => {
               const newSession = crypto.randomUUID();
               router.push(`/${newSession}/upload`);
             }}
             className="group relative px-12 py-6 bg-white text-black font-black text-2xl tracking-tighter rounded-full overflow-hidden transition-transform hover:scale-105 flex items-center gap-4 shadow-[0_0_60px_rgba(255,255,255,0.3)]"
           >
             <span className="relative z-10 flex items-center gap-3">
               Enter the Workspace 
               <ArrowRight className="w-7 h-7 group-hover:translate-x-1 transition-transform" />
             </span>
             <div className="absolute inset-0 bg-gradient-to-r from-cyan-100 to-purple-100 opacity-0 group-hover:opacity-100 transition-opacity" />
           </button>
        </motion.div>

      </div>
    </div>
  );
};

export default function Home() {
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
              <div className="bg-neutral-900/40 border border-white/5 p-8 md:p-12 rounded-[2rem] hover:bg-neutral-900/60 hover:border-purple-500/30 transition-colors group backdrop-blur-sm shadow-xl">
                <div className="w-14 h-14 bg-rose-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform"><ShieldCheck className="w-7 h-7 text-rose-500" /></div>
                <h4 className="text-3xl font-bold mb-4 tracking-tight">Zero-Leak PII Vault</h4>
                <p className="text-neutral-400 text-lg leading-relaxed">Before a single byte is analyzed, our local edge-scanner identifies and cryptographically vaults personal identities. Your sensitive data never hits the cloud.</p>
              </div>
              <div className="bg-neutral-900/40 border border-white/5 p-8 md:p-12 rounded-[2rem] hover:bg-neutral-900/60 hover:border-purple-500/30 transition-colors group backdrop-blur-sm shadow-xl">
                <div className="w-14 h-14 bg-emerald-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform"><Terminal className="w-7 h-7 text-emerald-500" /></div>
                <h4 className="text-3xl font-bold mb-4 tracking-tight">Neuro-Symbolic Logic</h4>
                <p className="text-neutral-400 text-lg leading-relaxed">We don&apos;t just guess. DataSentinel combines strict, dynamic mathematical rules with semantic AI evaluation to automatically reject impossible realities in your dataset.</p>
              </div>
              <div className="bg-neutral-900/40 border border-white/5 p-8 md:p-12 rounded-[2rem] hover:bg-neutral-900/60 hover:border-purple-500/30 transition-colors group backdrop-blur-sm shadow-xl">
                <div className="w-14 h-14 bg-cyan-500/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform"><Zap className="w-7 h-7 text-cyan-500" /></div>
                <h4 className="text-3xl font-bold mb-4 tracking-tight">Groq LPU Acceleration</h4>
                <p className="text-neutral-400 text-lg leading-relaxed">Powered by Llama 3.3 70B running on Groq&apos;s Language Processing Units. Generate complex SQL queries, statistical profiles, and narrative insights in literal milliseconds.</p>
              </div>
            </div>
          </div>

          <ScrollyTellingFinale />

        </motion.div>
      </AnimatePresence>
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes shimmer {
          100% {
            transform: translateX(100%);
          }
        }
      `}} />
    </main>
  );
}