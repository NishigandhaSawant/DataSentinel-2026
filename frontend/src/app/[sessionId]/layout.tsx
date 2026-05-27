"use client";
import { ShieldCheck, Trash2, Edit, BarChart, Brain, Terminal, ArrowRight, FileCheck, UploadCloud } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { use } from "react";
import AmbientAurora from "@/components/landing/AmbientAurora";
import { SessionProvider } from "./SessionProvider";

export default function SessionLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const pathname = usePathname();

  const steps = [
    { id: 'upload', icon: <UploadCloud size={16} />, label: 'Upload' },
    { id: 'detect', icon: <ShieldCheck size={16} />, label: 'Detection' },
    { id: 'insights', icon: <Brain size={16} />, label: 'Insights' },
    { id: 'clean', icon: <Trash2 size={16} />, label: 'Cleaning' },
    { id: 'compare', icon: <ArrowRight size={16} />, label: 'Compare' },
    { id: 'edit', icon: <Edit size={16} />, label: 'Edit' },
    { id: 'visualize', icon: <BarChart size={16} />, label: 'Visualizer' },
    { id: 'query', icon: <Terminal size={16} />, label: 'Query' },
    { id: 'report', icon: <FileCheck size={16} />, label: 'Quality Export' }
  ];

  return (
    <SessionProvider sessionId={sessionId}>
      <div className="min-h-screen bg-black text-white flex flex-col font-sans selection:bg-purple-500 selection:text-white overflow-clip relative">
        <AmbientAurora />
        
        {/* Navigation Bar */}
        <nav className="border-b border-white/5 bg-black/20 backdrop-blur-xl sticky top-0 z-50 p-4 flex justify-center space-x-2 md:space-x-4 overflow-x-auto">
          {steps.map((step) => {
            const isActive = pathname.includes(`/${step.id}`);
            return (
              <Link 
                key={step.id} 
                href={`/${sessionId}/${step.id}`}
                className={`flex items-center px-4 py-2 rounded-xl text-xs md:text-sm font-bold transition-all whitespace-nowrap ${isActive ? 'bg-white text-black shadow-lg' : 'text-neutral-500 hover:text-white hover:bg-neutral-900'}`}
              >
                <span className="mr-2">{step.icon}</span>{step.label}
              </Link>
            );
          })}
        </nav>
        
        {/* Main Content Area */}
        <div className="flex-1 flex flex-col items-center p-6 w-full max-w-6xl mx-auto relative z-10">
          {children}
        </div>
      </div>
    </SessionProvider>
  );
}