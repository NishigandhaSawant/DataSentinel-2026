"use client";
import React, { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import api from "@/services/api.service";
import { API_BASE } from "@/constants/config";
import type { InsightsDashboardResponse } from "@/types/api";

interface SessionContextType {
  sessionId: string;
  cachedInsights: InsightsDashboardResponse | null;
  setCachedInsights: (data: InsightsDashboardResponse | null) => void;
  recommendedMethod: string;
  setRecommendedMethod: (method: string) => void;
  cleaningRationale: string;
  setCleaningRationale: (rationale: string) => void;
}

const SessionContext = createContext<SessionContextType | null>(null);

export function SessionProvider({ children, sessionId }: { children: React.ReactNode; sessionId: string }) {
  const [cachedInsights, setCachedInsights] = useState<InsightsDashboardResponse | null>(null);
  const [recommendedMethod, setRecommendedMethod] = useState<string>('quarantine');
  const [cleaningRationale, setCleaningRationale] = useState<string>('');

  const router = useRouter();

  useEffect(() => {
    // Fetch initial status to get recommendation and rationale
    api.get(`/api/status/${sessionId}`).then(res => {
        const result = res.data?.result;
        if (result) {
            if (result.recommended_cleaning) setRecommendedMethod(result.recommended_cleaning);
            if (result.cleaning_rationale) setCleaningRationale(result.cleaning_rationale);
        }
    }).catch((err) => {
        if (err.response?.status === 404) {
            window.location.href = "/";
        }
    });
  }, [sessionId, router]);

  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "Are you sure you want to leave? Your progress will be lost.";
      return e.returnValue;
    };

    const handleUnload = () => {
      // Use sendBeacon for fire-and-forget deletion before tab closes or reloads
      navigator.sendBeacon(`${API_BASE}/api/session/${sessionId}/delete`);
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    window.addEventListener("unload", handleUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      window.removeEventListener("unload", handleUnload);
    };
  }, [sessionId]);

  return (
    <SessionContext.Provider value={{ sessionId, cachedInsights, setCachedInsights, recommendedMethod, setRecommendedMethod, cleaningRationale, setCleaningRationale }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used within SessionProvider");
  return context;
}