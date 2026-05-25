/* ─── Imports ────────────────────────────────────────────────────────────────────────────── */

import { useState, useEffect } from 'react';
import api from '@/services/api.service';
import type { AnomalyRow, DriftReport, SessionDataResponse } from '@/types/api';

/* ─── Hook ───────────────────────────────────────────────────────────────────────────────── */

/**
 * Custom hook to manage the anomaly detection data and feedback.
 *
 * Includes retry-with-backoff for 404 errors: the backend writes raw_data.parquet
 * synchronously inside process_and_detect, so a 404 immediately after upload
 * means the session ID hasn't propagated yet (race condition). We retry up to 5
 * times with exponential backoff (500 → 1000 → 2000 → 4000 → 4000 ms) before
 * showing a permanent error.
 *
 * @param {string} sessionId - The session identifier.
 * @returns {object} Detection state and handlers.
 */
export function useDetection(sessionId: string) {
  const [data, setData] = useState<AnomalyRow[]>([]);
  const [totalAnomalies, setTotalAnomalies] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [threshold, setThreshold] = useState<number>(0);
  const [minSliderBound, setMinSliderBound] = useState<number>(0);
  const [feedbackMap, setFeedbackMap] = useState<Record<number, 'correct' | 'incorrect'>>({});
  const [driftReport, setDriftReport] = useState<DriftReport | undefined>(undefined);
  const [recommendation, setRecommendation] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!sessionId) {
      setErrorMsg('Critical Error: Session ID is missing. Please refresh and try uploading again.');
      setIsLoading(false);
      return;
    }

    // Reset state on new session
    setData([]);
    setTotalAnomalies(0);
    setErrorMsg(null);
    setIsLoading(true);

    let cancelled = false;

    const fetchWithRetry = async (attemptsLeft: number, delayMs: number): Promise<void> => {
      try {
        // Fetch ALL anomalous rows — client-side threshold slider filters display.
        // Using only_anomalies=true previously caused the "0 anomalies" bug:
        // totalAnomalies was set from filtered data, not the actual anomaly count.
        const res = await api.get<SessionDataResponse>(
          `/api/data/${sessionId}?is_cleaned=false&only_anomalies=true`
        );

        if (cancelled) return;

        if (res.data && Array.isArray(res.data.data)) {
          setData(res.data.data);
          // Use total_anomalies from the backend — it counts ALL anomalies, not just the page
          setTotalAnomalies(res.data.total_anomalies || 0);
          setDriftReport(res.data.drift_report);
          setRecommendation(res.data.recommendation);

          const threatScores = res.data.data
            .map((r) => r.Threat_Score)
            .filter((s) => s !== undefined && s !== null) as number[];

          if (threatScores.length > 0) {
            // Start threshold at the LOWEST score so ALL anomalies are visible by default
            const lowestScore = Math.floor(Math.min(...threatScores));
            const boundedMin = Math.max(0, Math.min(lowestScore, 99));
            setMinSliderBound(boundedMin);
            setThreshold(boundedMin);
          }
        } else {
          throw new Error('Invalid data format received from the server.');
        }
      } catch (err: unknown) {
        if (cancelled) return;

        const axiosErr = err as {
          response?: { status?: number; data?: { error?: string; detail?: string } };
          message?: string;
        };

        const status = axiosErr.response?.status;

        // 404 = parquet may not be flushed yet → retry with backoff
        if (status === 404 && attemptsLeft > 0) {
          await new Promise((resolve) => setTimeout(resolve, delayMs));
          if (!cancelled) {
            return fetchWithRetry(attemptsLeft - 1, Math.min(delayMs * 2, 4000));
          }
          return;
        }

        // Permanent failure — surface a clear, actionable message
        const message =
          status === 404
            ? 'Detection results not found. The session may have expired — please re-upload your file.'
            : axiosErr.response?.data?.error ||
              axiosErr.response?.data?.detail ||
              axiosErr.message ||
              'Failed to load anomaly report.';

        setErrorMsg(message);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    // 5 retries, 500 ms initial delay (doubles each time, capped at 4 s)
    fetchWithRetry(5, 500);

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const submitFeedback = async (row: AnomalyRow, idx: number, isCorrect: boolean) => {
    try {
      await api.post('/api/feedback/', {
        session_id: sessionId,
        row_data: row,
        is_correct: isCorrect,
      });
      setFeedbackMap((prev) => ({ ...prev, [idx]: isCorrect ? 'correct' : 'incorrect' }));
    } catch (e) {
      console.error('Failed to submit feedback', e);
    }
  };

  return {
    data,
    totalAnomalies,
    isLoading,
    errorMsg,
    threshold,
    setThreshold,
    minSliderBound,
    feedbackMap,
    submitFeedback,
    driftReport,
    recommendation,
  };
}
