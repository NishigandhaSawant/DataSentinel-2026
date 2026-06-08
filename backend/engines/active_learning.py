"""
DataSentinel — Active Learning & Trust Quantification Engine
IEEE Novelty: 
1. Uncertainty Sampling: Prioritizes human review for anomalies sitting closest 
   to the hyperplane decision boundary, reducing alert fatigue.
2. Human Trust Score (HTS): A dynamic heuristic blending False Positive Rates, 
   Causal Faithfulness, and RL Action Acceptance.
"""

import os
import json
import numpy as np
import pandas as pd
from utils import logger, _BACKEND_DIR

def calculate_uncertainty_scores(inverted_scores: np.ndarray, threshold: float) -> np.ndarray:
    """
    Active Learning Uncertainty Sampling.
    Data points that are extremely anomalous (score >> threshold) or extremely 
    normal (score << threshold) have low uncertainty. 
    Points right on the boundary have maximum uncertainty (1.0).
    
    Math: U(x) = exp(-|score - threshold|)
    """
    # Calculate absolute distance to the decision boundary
    margin_distance = np.abs(inverted_scores - threshold)
    
    # Scale distance to prevent extreme exponential drops
    scale_factor = np.std(inverted_scores) if np.std(inverted_scores) > 0 else 1.0
    normalized_distance = margin_distance / scale_factor
    
    # Convert to an uncertainty score [0, 1] where 1 is sitting exactly on the threshold
    uncertainty_scores = np.exp(-normalized_distance)
    
    return np.round(uncertainty_scores, 4)

def compute_human_trust_score(session_id: str, causal_payloads: list) -> dict:
    """
    Calculates the Human Trust Score (HTS).
    HTS = α(1 - FPR) + β(Faithfulness) + γ(Feedback Retention)
    """
    alpha, beta, gamma = 0.4, 0.4, 0.2
    
    # 1. False Positive Rate (FPR) from persistent feedback log
    fpr = 0.05 # Default assumed FPR
    feedback_path = os.path.join(_BACKEND_DIR, "data", "feedback_log.jsonl")
    
    if os.path.exists(feedback_path):
        fp_count = 0
        total_reviews = 0
        try:
            with open(feedback_path, "r") as f:
                for line in f:
                    if not line.strip(): continue
                    entry = json.loads(line)
                    total_reviews += 1
                    if entry.get("label") == 0: # 0 means False Positive
                        fp_count += 1
            
            if total_reviews > 0:
                fpr = fp_count / total_reviews
        except Exception as e:
            logger.warning("Failed to read feedback log for HTS: %s", e)

    # 2. Causal Faithfulness
    # Faithfulness measures if the top causal features actually have high impact scores.
    # We average the relative impact of the top feature vs the rest of the features.
    faithfulness_scores = []
    for payload_str in causal_payloads:
        try:
            payload = json.loads(payload_str)
            if len(payload) > 0:
                top_impact = abs(payload[0]["impact"])
                total_impact = sum([abs(p["impact"]) for p in payload])
                if total_impact > 0:
                    faithfulness_scores.append(top_impact / total_impact)
        except Exception:
            continue
            
    avg_faithfulness = np.mean(faithfulness_scores) if faithfulness_scores else 0.85
    
    # 3. Feedback Retention (RL Acceptance)
    # How often does the user accept the RL Agent's recommended imputation?
    # For now, we query the Q-table to see how "confident" the agent is (max Q-value)
    q_table_path = os.path.join(_BACKEND_DIR, "sessions", session_id, "reclean_q_table.json")
    retention_score = 0.75 # Default
    
    if os.path.exists(q_table_path):
        try:
            with open(q_table_path, "r") as f:
                q_table = json.load(f)
                max_q_values = [max(actions.values()) for actions in q_table.values() if actions]
                if max_q_values:
                    # Normalize Q-values to a 0-1 scale to represent confidence
                    avg_q = np.mean(max_q_values)
                    retention_score = min(1.0, max(0.5, avg_q)) # Bound between 0.5 and 1.0
        except Exception:
            pass

    # Compute final HTS
    hts = (alpha * (1.0 - fpr)) + (beta * avg_faithfulness) + (gamma * retention_score)
    
    return {
        "trust_score": round(hts * 100, 1), # Scale 0-100
        "components": {
            "fpr_penalty": round((1.0 - fpr) * 100, 1),
            "causal_faithfulness": round(avg_faithfulness * 100, 1),
            "rl_confidence": round(retention_score * 100, 1)
        }
    }