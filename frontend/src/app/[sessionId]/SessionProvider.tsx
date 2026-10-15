"use client";
import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import api from "@/services/api.service";
import { API_BASE } from "@/constants/config";
import type { InsightsDashboardResponse } from "@/types/api";
import ResetConfirmModal from "@/components/ResetConfirmModal";

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

// ── sessionStorage key helpers ────────────────────────────────────────────────
const reloadFlagKey = (id: string) => `ds_reload_${id}`;

export function SessionProvider({ children, sessionId }: { children: React.ReactNode; sessionId: string }) {
  const [cachedInsights, setCachedInsights] = useState<InsightsDashboardResponse | null>(null);
  const [recommendedMethod, setRecommendedMethod] = useState<string>('quarantine');
  const [cleaningRationale, setCleaningRationale] = useState<string>('');

  // Reset modal state (used for F5 / Ctrl+R keyboard intercept)
  const [showResetModal, setShowResetModal] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  const router = useRouter();

  // ── STEP 1: On mount — check for a reload flag set by a previous beforeunload ──
  // If the flag is present it means the user used the browser's refresh button
  // (or closed and came back). The beacon fired on unload already deleted the
  // session data, so we just redirect straight to the landing page.
  useEffect(() => {
    const flagKey = reloadFlagKey(sessionId);
    if (typeof window !== 'undefined' && sessionStorage.getItem(flagKey)) {
      sessionStorage.removeItem(flagKey);
      router.replace('/');
      return; // don't run any other setup
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally run only once on mount

  // ── STEP 2: Fetch initial status ──────────────────────────────────────────
  useEffect(() => {
    api.get(`/api/status/${sessionId}`).then(res => {
      const result = res.data?.result;
      if (result) {
        if (result.recommended_cleaning) setRecommendedMethod(result.recommended_cleaning);
        if (result.cleaning_rationale) setCleaningRationale(result.cleaning_rationale);
      }
    }).catch((err) => {
      if (err.response?.status === 404) {
        console.warn("Session status not found. It might be a new session or expired.");
      }
    });
  }, [sessionId]);

  // ── STEP 3: Full programmatic session reset (used by modal confirm) ───────
  const performReset = useCallback(async () => {
    setIsResetting(true);
    try {
      await api.post(`/api/session/${sessionId}/delete`).catch(() => {
        navigator.sendBeacon(`${API_BASE}/api/session/${sessionId}/delete`);
      });
    } catch {
      // Best-effort – still redirect
    } finally {
      // Clear in-memory state
      setCachedInsights(null);
      setRecommendedMethod('quarantine');
      setCleaningRationale('');
      // Remove the reload flag so we don't double-redirect
      sessionStorage.removeItem(reloadFlagKey(sessionId));
      router.replace('/');
    }
  }, [sessionId, router]);

  // ── STEP 4: Keyboard intercept — F5 / Ctrl+R / Cmd+R ─────────────────────
  // These are captured before the browser acts on them, so we can show our
  // custom modal instead of triggering a native reload.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isRefreshKey =
        e.key === 'F5' ||
        ((e.ctrlKey || e.metaKey) && (e.key === 'r' || e.key === 'R'));

      if (isRefreshKey) {
        e.preventDefault();
        e.stopPropagation();
        setShowResetModal(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
  }, []);

  // ── STEP 5: Browser toolbar button / address-bar reload / tab close ───────
  // We cannot show a custom modal for these — only the native browser dialog.
  // Strategy:
  //   - beforeunload: stamp a sessionStorage flag AND show the native warning.
  //   - unload: fire a beacon to delete the session server-side.
  //   - Next mount (Step 1 above): detect the flag → redirect to landing page.
  //
  // IMPORTANT: beforeunload also fires on Next.js client-side navigations (link
  // clicks, router.push). To avoid leaving a stale flag that Step 1 would
  // wrongly treat as a reload, we clear the flag:
  //   • on pagehide  — covers BFCache restores AND cancelled unloads
  //   • on popstate  — covers browser back/forward (client-side)
  //   • on visibilitychange — covers cancelled native reload dialogs
  useEffect(() => {
    const flagKey = reloadFlagKey(sessionId);

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Stamp the flag BEFORE the browser shows the dialog so it's always set
      // if the page is about to unload.
      sessionStorage.setItem(flagKey, '1');
      e.preventDefault();
      e.returnValue =
        'Are you sure you want to leave? Your session and all processed data will be permanently deleted.';
      return e.returnValue;
    };

    const handleUnload = () => {
      // Fire-and-forget — deletes session data on the server even if JS is
      // torn down mid-execution.
      navigator.sendBeacon(`${API_BASE}/api/session/${sessionId}/delete`);
    };

    // pagehide fires on every navigation (including client-side ones in some
    // browsers). Clear the flag here so it only survives a true hard reload
    // where the page is actually destroyed and re-created.
    const handlePageHide = () => {
      sessionStorage.removeItem(flagKey);
    };

    const handlePageShow = (e: PageTransitionEvent) => {
      // BFCache restore — page came back from cache. Clear flag.
      if (e.persisted) {
        sessionStorage.removeItem(flagKey);
      }
    };

    // Cleared when the user comes back to the tab after cancelling the dialog
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Only clear if the page is still mounted (user stayed)
        sessionStorage.removeItem(flagKey);
      }
    };

    // Clear the flag on client-side route transitions (popstate = back/forward)
    const handlePopState = () => {
      sessionStorage.removeItem(flagKey);
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('unload', handleUnload);
    window.addEventListener('pagehide', handlePageHide);
    window.addEventListener('pageshow', handlePageShow);
    window.addEventListener('popstate', handlePopState);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('unload', handleUnload);
      window.removeEventListener('pagehide', handlePageHide);
      window.removeEventListener('pageshow', handlePageShow);
      window.removeEventListener('popstate', handlePopState);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [sessionId]);

  // ── Modal handlers ─────────────────────────────────────────────────────────
  const handleConfirmReset = () => performReset();
  const handleCancelReset = () => { if (!isResetting) setShowResetModal(false); };

  return (
    <SessionContext.Provider value={{
      sessionId,
      cachedInsights,
      setCachedInsights,
      recommendedMethod,
      setRecommendedMethod,
      cleaningRationale,
      setCleaningRationale,
    }}>
      {children}

      {/* Global Reset Confirmation Modal
          Rendered at the provider level → present on every session page. */}
      <ResetConfirmModal
        isOpen={showResetModal}
        onConfirm={handleConfirmReset}
        onCancel={handleCancelReset}
        isResetting={isResetting}
      />
    </SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error('useSession must be used within SessionProvider');
  return context;
}