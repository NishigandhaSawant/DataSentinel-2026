"""
DataSentinel — Reinforcement Learning Remediation Optimizer (ReClean)
Replaces hardcoded data cleaning with an autonomous Q-Learning agent.

IEEE Novelty: Formulates data cleansing as a Markov Decision Process (MDP).
The agent selects imputation strategies (Actions) based on column statistics (State)
to maximize downstream data utility and variance preservation (Reward).
"""

import os
import json
import numpy as np
import polars as pl
import pandas as pd
from sklearn.impute import KNNImputer
from scipy.stats import ks_2samp
from utils import logger, _BACKEND_DIR

class ReCleanAgent:
    def __init__(self, session_id: str, epsilon=0.2, alpha=0.1, gamma=0.9):
        self.session_id = session_id
        self.q_table_path = os.path.join(_BACKEND_DIR, "sessions", session_id, "reclean_q_table.json")
        self.epsilon = epsilon  # Exploration rate
        self.alpha = alpha      # Learning rate
        self.gamma = gamma      # Discount factor
        
        # Actions: 0=Mean, 1=Median, 2=KNN(k=3)
        self.actions = [0, 1, 2] 
        self.q_table = self._load_q_table()

    def _load_q_table(self):
        if os.path.exists(self.q_table_path):
            try:
                with open(self.q_table_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_q_table(self):
        os.makedirs(os.path.dirname(self.q_table_path), exist_ok=True)
        with open(self.q_table_path, "w") as f:
            json.dump(self.q_table, f)

    def get_state(self, series: pd.Series) -> str:
        """
        Discretizes the column statistics into a State vector for the MDP.
        State definition: [Sparsity_Level, Skewness_Level]
        """
        null_pct = series.isna().sum() / len(series)
        
        # Discretize Sparsity
        if null_pct < 0.05: sparsity = "Low"
        elif null_pct < 0.20: sparsity = "Medium"
        else: sparsity = "High"

        # Discretize Skewness (using roughly > 1.0 as high skew)
        skew = series.skew()
        if pd.isna(skew): skewness = "Unknown"
        elif abs(skew) > 1.0: skewness = "High"
        else: skewness = "Low"

        return f"{sparsity}_{skewness}"

    def choose_action(self, state: str) -> int:
        """Epsilon-greedy action selection."""
        if state not in self.q_table:
            self.q_table[state] = {str(a): 0.0 for a in self.actions}

        # Explore: Try a random cleaning method
        if np.random.uniform(0, 1) < self.epsilon:
            return np.random.choice(self.actions)
        
        # Exploit: Choose the cleaning method with the highest historical reward
        valid_q_values = {k: v for k, v in self.q_table[state].items() if int(k) in self.actions}
        if not valid_q_values:
            return np.random.choice(self.actions)
        best_action = max(valid_q_values, key=valid_q_values.get)
        return int(best_action)

    def update_q_value(self, state: str, action: int, reward: float):
        """Standard Q-Learning Bellman update."""
        if state not in self.q_table:
            self.q_table[state] = {str(a): 0.0 for a in self.actions}
            
        current_q = self.q_table[state][str(action)]
        # Since this is a contextual bandit setup (1-step MDP), max future Q is 0
        new_q = current_q + self.alpha * (reward - current_q)
        self.q_table[state][str(action)] = new_q
        self._save_q_table()


def calculate_reward(original_series: pd.Series, cleaned_series: pd.Series, action: int) -> float:
    """
    IEEE Novelty: Reward function is the inverse of the Kolmogorov-Smirnov distance.
    We reward the agent for preserving the original statistical distribution.
    """
    orig_clean = original_series.dropna()
    if len(orig_clean) < 10 or len(cleaned_series) < 10:
        return 0.0  # Not enough data to judge

    # Calculate Distribution Shift (Lower is better)
    ks_stat, _ = ks_2samp(orig_clean, cleaned_series)
    
    # Reward is high if distribution is preserved (KS stat is close to 0)
    reward = 1.0 - ks_stat
        
    return float(reward)


def apply_rl_cleaning(df: pl.DataFrame, session_id: str) -> dict:
    """
    Iterates over anomalous columns, uses the RL agent to select the optimal
    cleaning strategy, applies it, calculates the reward, and learns.
    """
    logger.info("Initializing RL Autonomous Remediation Agent...")
    agent = ReCleanAgent(session_id)
    
    pandas_df = df.to_pandas()
    numeric_cols = pandas_df.select_dtypes(include=[np.number]).columns
    
    actions_taken = {}
    total_reward = 0.0
    
    action_map = {
        0: "Mean Imputation",
        1: "Median Imputation",
        2: "KNN Imputation (k=3)"
    }

    is_anomaly = pandas_df.get('is_anomaly', pd.Series([False]*len(pandas_df))).astype(bool)

    for col in numeric_cols:
        if col in ["is_anomaly", "Threat_Score"]:
            continue
            
        # Mask anomalous values to NaN so the RL agent can orchestrate repairs
        if is_anomaly.any():
            pandas_df.loc[is_anomaly, col] = np.nan
            
        null_count = pandas_df[col].isna().sum()
        if null_count == 0:
            continue # Skip clean columns
            
        state = agent.get_state(pandas_df[col])
        action = agent.choose_action(state)
        
        logger.info(f"RL Agent resolving '{col}' (State: {state}) -> Action: {action_map[action]}")
        
        original_series = pandas_df[col].copy()
        
        # Apply the chosen action
        if action == 0:
            pandas_df[col] = pandas_df[col].fillna(pandas_df[col].mean())
        elif action == 1:
            pandas_df[col] = pandas_df[col].fillna(pandas_df[col].median())
        elif action == 2:
            try:
                if pandas_df[col].isna().all():
                    raise ValueError("Column is entirely NaN, KNNImputer cannot fit.")
                imputer = KNNImputer(n_neighbors=3)
                pandas_df[col] = imputer.fit_transform(pandas_df[[col]])
            except Exception:
                pandas_df[col] = pandas_df[col].fillna(pandas_df[col].median()) # Fallback
            
        # Calculate Reward based on downstream utility
        reward = calculate_reward(original_series, pandas_df[col], action)
        total_reward += reward
        
        # Learn!
        agent.update_q_value(state, action, reward)
        actions_taken[col] = {
            "state": state,
            "action_taken": action_map[action],
            "reward": round(reward, 4)
        }
        
    logger.info(f"RL Remediation Complete. Total Episode Reward: {total_reward:.4f}")
    
    return {
        "cleaned_df": pl.from_pandas(pandas_df),
        "reclean_report": actions_taken,
        "total_reward": total_reward
    }