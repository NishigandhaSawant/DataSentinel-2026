/* ─────────────────────────────────────────────────────────────
   DataSentinel — Shared TypeScript Interfaces
   Replaces pervasive `any` types across all components.
   ───────────────────────────────────────────────────────────── */

export interface UploadResponse {
  status: string;
  session_id: string;
  total_rows: number;
  anomaly_count: number;
  recommendation: string;
  recommended_cleaning: string;
  cleaning_rationale: string;
  parquet_path: string;
}

export interface AnomalyRow {
  is_anomaly: boolean;
  AI_Reason: string;
  Threat_Score: number;
  Uncertainty_Score?: number; // <-- NEW: For Active Learning
  SHAP_Payload?: string;
  Counterfactual_Payload?: string;
  lof_score?: number;
  lstm_anomaly_score?: number;
  ecod_score?: number;
  [key: string]: unknown;
}

export interface DriftedFeature {
  feature: string;
  ks_stat: number;
  p_value: number;
}

export interface DriftReport {
  drifted_features: DriftedFeature[];
  baseline_present: boolean;
}

export interface SessionDataResponse {
  data: AnomalyRow[];
  total_anomalies: number;
  total_rows: number;
  drift_report?: DriftReport;
  recommendation?: string;
}

export interface CleanResponse {
  status: string;
  action_taken: string;
  original_rows: number;
  new_total: number;
}

export interface CompareResponse {
  is_dropped: boolean;
  original: Record<string, unknown>[];
  cleaned: Record<string, unknown>[];
  count: number;
}

// ── New Insights Dashboard Types ─────────────────────────────

export interface InsightsSummary {
  total_rows: number;
  total_columns: number;
  numeric_columns: number;
  text_columns: number;
  date_columns: number;
  anomaly_count: number;
  anomaly_rate: number;
  health_score: number;
}

export interface ColumnProfile {
  name: string;
  type: "numeric" | "text";
  // Numeric fields
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  median?: number | null;
  std?: number | null;
  skewness?: number | null;
  outlier_count?: number;
  // Text fields
  unique_values?: number;
  // Common
  null_count: number;
  null_pct: number;
}

export interface MissingDataEntry {
  column: string;
  null_count: number;
  null_pct: number;
}

export interface CorrelationEntry {
  col_a: string;
  col_b: string;
  value: number;
}

export interface AnomalyDistEntry {
  column: string;
  anomaly_count: number;
}

// NEW: Lineage Topology Interface
export interface LineageTopology {
  status: string;
  drift_detected: boolean;
  current_structural_error: number;
  baseline_structural_error: number;
  topology_nodes: number;
  topology_edges: number;
  reason?: string;
}

// NEW: Human Trust Score Metrics
export interface TrustMetrics {
  trust_score: number;
  components: {
    fpr_penalty: number;
    causal_faithfulness: number;
    rl_confidence: number;
  };
}

export interface InsightsDashboardResponse {
  summary: InsightsSummary;
  column_profiles: ColumnProfile[];
  missing_data_map: MissingDataEntry[];
  type_breakdown: { numeric: number; text: number; date: number };
  top_correlations: CorrelationEntry[];
  anomaly_distribution: AnomalyDistEntry[];
  ai_narrative: string[];
  lineage_topology?: LineageTopology;
  trust_metrics?: TrustMetrics; // <-- NEW: Attached to insights
  sbvr_rules?: string[]; // <-- NEW: SBVR constraints
}

export interface VizData {
  columns: string[];
  categorical_columns: string[];
  global_raw_hist: { bin: string; count: number }[];
  global_clean_hist: { bin: string; count: number }[];
  clean_sample: Record<string, unknown>[];
  correlation: { features: string[]; matrix: number[][] } | null;
  categorical_data: {
    column: string;
    top_values: { label: string; count: number }[];
  }[];
  health_score: number;
}


export interface QuarantineResponse {
  data: AnomalyRow[];
  count: number;
}