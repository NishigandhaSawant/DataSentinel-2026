"use client";
import React, { createContext, useContext, useState, useEffect } from "react";
import api from "@/services/api.service";
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

  useEffect(() => {
    // Fetch initial status to get recommendation and rationale
    api.get(`/api/status/${sessionId}`).then(res => {
        const result = res.data?.result;
        if (result) {
            if (result.recommended_cleaning) setRecommendedMethod(result.recommended_cleaning);
            if (result.cleaning_rationale) setCleaningRationale(result.cleaning_rationale);
        }
    }).catch(() => {});
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