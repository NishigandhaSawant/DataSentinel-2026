"""
DataSentinel — Causal Discovery Root Cause Analysis (RCA)
Replaces marginal SHAP values with continuous DAG optimization (NOTEARS).

IEEE Novelty: Uses PyTorch to formulate structure learning as a continuous 
optimization problem, forcing a DAG topology via the matrix exponential trace.
Traces anomalies upstream to their true causal origin rather than correlating symptoms.
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import json
from utils import logger

class NOTEARS_MLP(nn.Module):
    """
    A PyTorch implementation of continuous DAG discovery.
    Learns an adjacency matrix W while enforcing acyclicity.
    """
    def __init__(self, d: int):
        super(NOTEARS_MLP, self).__init__()
        # The learnable adjacency matrix (d x d)
        self.W = nn.Parameter(torch.zeros(d, d))
        
    def forward(self, x):
        # Apply mask to ensure no self-loops (diagonal = 0)
        mask = torch.eye(self.W.shape[0], device=self.W.device).bool()
        W_masked = self.W.masked_fill(mask, 0.0)
        return torch.matmul(x, W_masked)

def compute_dag_penalty(W: torch.Tensor) -> torch.Tensor:
    """
    The mathematical core of NOTEARS.
    A matrix W is a DAG if and only if trace(exp(W * W)) - d == 0.
    """
    d = W.shape[0]
    W_squared = W * W
    # Matrix exponential
    E = torch.matrix_exp(W_squared)
    h = torch.trace(E) - d
    return h

def learn_causal_graph(df: pd.DataFrame, max_epochs=200, lambda_l1=0.01) -> np.ndarray:
    """
    Fits the Causal DAG using gradient descent.
    Optimized for performance: Downsamples to 10,000 rows max if dataset is large.
    """
    if len(df) > 10000:
        df_train = df.sample(n=10000, random_state=42)
    else:
        df_train = df
        
    X = torch.FloatTensor(df_train.values)
    d = X.shape[1]
    
    model = NOTEARS_MLP(d)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    
    model.train()
    for epoch in range(max_epochs):
        optimizer.zero_grad()
        X_hat = model(X)
        
        # 1. Reconstruction Loss (MSE)
        loss_mse = 0.5 / X.shape[0] * torch.sum((X_hat - X) ** 2)
        
        # 2. Sparsity Penalty (L1)
        loss_l1 = lambda_l1 * torch.sum(torch.abs(model.W))
        
        # 3. Acyclicity Penalty (The DAG constraint)
        mask = torch.eye(d, device=model.W.device).bool()
        W_masked = model.W.masked_fill(mask, 0.0)
        h = compute_dag_penalty(W_masked)
        
        # We heavily penalize any cycles (h > 0)
        loss = loss_mse + loss_l1 + (10.0 * h * h)
        
        loss.backward()
        optimizer.step()

    # Extract the final learned adjacency matrix
    with torch.no_grad():
        mask = torch.eye(d).bool()
        W_final = model.W.masked_fill(mask, 0.0).numpy()
        
    # Threshold out weak causal links to create a sparse DAG
    W_final[np.abs(W_final) < 0.2] = 0.0
    return W_final

def generate_causal_payloads(encoded_df: pd.DataFrame, anomaly_indices: list, stats: dict) -> list:
    """
    Replaces SHAP extraction. 
    Builds the causal graph, looks at anomalous rows, and traces deviations upstream.
    """
    if encoded_df.empty or not anomaly_indices:
        return ["[]"] * len(encoded_df)
        
    logger.info("Initializing Continuous Causal Discovery (NOTEARS) for RCA...")
    
    # 1. Learn the global DAG from the dataset
    feature_names = encoded_df.columns.tolist()
    
    # Normalize data for stable gradients
    norm_df = (encoded_df - encoded_df.mean()) / (encoded_df.std().replace(0, 1))
    W_dag = learn_causal_graph(norm_df)
    
    logger.info("Causal DAG compiled. Tracing root causes for %d anomalies...", len(anomaly_indices))
    
    payloads = ["[]"] * len(encoded_df)
    
    for idx in anomaly_indices:
        row = encoded_df.iloc[idx]
        
        # Calculate raw deviations (Z-scores) for this row
        deviations = {}
        for i, col in enumerate(feature_names):
            if stats.get(col, {}).get("std", 0) > 0:
                z = abs((row[col] - stats[col]["mean"]) / stats[col]["std"])
                deviations[i] = z
            else:
                deviations[i] = 0.0
                
        # RCA Logic: A feature's True Root Cause Importance is its own deviation 
        # PLUS the deviations of all the downstream nodes it causally influences.
        root_cause_scores = []
        for i, col in enumerate(feature_names):
            if deviations[i] < 1.0: # Skip normal features
                continue
                
            # How much does feature `i` causally influence other anomalous features?
            outbound_causal_strength = 0.0
            for j in range(len(feature_names)):
                if W_dag[i, j] != 0 and deviations[j] > 1.0:
                    outbound_causal_strength += abs(W_dag[i, j]) * deviations[j]
                    
            # Total score = Own Deviation + Downstream Blast Radius
            total_rca_score = deviations[i] + outbound_causal_strength
            
            root_cause_scores.append({
                "feature": col,
                "impact": float(total_rca_score) # Named 'impact' to maintain UI compatibility with SHAP
            })
            
        # Sort by causal root score (highest first) and keep top 3
        root_cause_scores.sort(key=lambda x: x["impact"], reverse=True)
        payloads[idx] = json.dumps(root_cause_scores[:3])
        
    return payloads