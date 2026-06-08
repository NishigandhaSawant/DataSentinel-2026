"""
DataSentinel — Unsupervised Graph Autoencoder (GAE) for Lineage Drift
Detects upstream ETL pipeline failures (e.g., broken JOINs, schema drift) 
by analyzing the topological graph structure of the dataset.

IEEE Novelty: Pure PyTorch implementation of Graph Convolutional Networks (GCN) 
with Inner-Product Decoding to quantify structural provenance decay.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import pandas as pd
import json
import os
from utils import logger, _BACKEND_DIR

# The persistent baseline for our graph topology
BASELINE_GRAPH_PATH = os.path.join(_BACKEND_DIR, "data", "baseline_lineage_graph.json")

class GCNLayer(nn.Module):
    """
    Custom Graph Convolutional Layer.
    Performs message passing between connected feature nodes.
    """
    def __init__(self, in_features: int, out_features: int):
        super(GCNLayer, self).__init__()
        self.weight = nn.Parameter(torch.FloatTensor(in_features, out_features))
        nn.init.xavier_uniform_(self.weight)

    def forward(self, x: torch.Tensor, adj: torch.Tensor):
        # Add self-loops (A_tilde = A + I)
        I = torch.eye(adj.size(0), device=adj.device)
        A_tilde = adj + I
        
        # Degree matrix normalization (D_tilde^-1/2)
        D_tilde = torch.sum(A_tilde, dim=1)
        D_tilde_inv_sqrt = torch.pow(D_tilde, -0.5)
        D_tilde_inv_sqrt[torch.isinf(D_tilde_inv_sqrt)] = 0.0
        D_mat = torch.diag(D_tilde_inv_sqrt)
        
        # Symmetrical normalization: D^(-1/2) * A * D^(-1/2)
        norm_adj = torch.matmul(torch.matmul(D_mat, A_tilde), D_mat)
        
        # Graph Convolution: A_norm * X * W
        support = torch.matmul(x, self.weight)
        output = torch.matmul(norm_adj, support)
        return output

class GraphAutoEncoder(nn.Module):
    """
    Encodes the graph topology into a latent space, then attempts to reconstruct
    the adjacency matrix via inner dot-product.
    """
    def __init__(self, num_features: int, hidden_dim: int = 16, latent_dim: int = 8):
        super(GraphAutoEncoder, self).__init__()
        self.gcn1 = GCNLayer(num_features, hidden_dim)
        self.gcn2 = GCNLayer(hidden_dim, latent_dim)

    def encode(self, x: torch.Tensor, adj: torch.Tensor):
        hidden = F.relu(self.gcn1(x, adj))
        latent = self.gcn2(hidden, adj) # Linear activation for the latent space
        return latent

    def decode(self, z: torch.Tensor):
        # Inner-product decoder: A_hat = sigmoid(Z * Z^T)
        adj_hat = torch.matmul(z, z.t())
        return torch.sigmoid(adj_hat)

    def forward(self, x: torch.Tensor, adj: torch.Tensor):
        z = self.encode(x, adj)
        return self.decode(z)

def build_empirical_adjacency(df: pd.DataFrame, threshold: float = 0.1) -> np.ndarray:
    """
    In the absence of a live Airflow/dbt hook, we approximate the ETL pipeline's 
    structural lineage by building a feature co-occurrence/correlation graph.
    If a JOIN breaks upstream, this topology will instantly collapse.
    """
    # Use absolute correlation as edge weights
    corr_matrix = df.corr().abs().fillna(0).values
    # Keep the actual correlation values for edges above the threshold to preserve topology weights
    adj_matrix = np.where(corr_matrix > threshold, corr_matrix, 0.0)
    # Remove self-loops for the raw representation
    np.fill_diagonal(adj_matrix, 0.0)
    return adj_matrix

def train_gae_and_score(adj_matrix: np.ndarray, feature_matrix: np.ndarray, epochs: int = 50) -> float:
    """
    Trains the Graph Autoencoder to reconstruct the topology.
    Returns the final Reconstruction Error (Structural Drift Score).
    """
    torch.manual_seed(42) # Ensure deterministic training for comparable baseline/current scores
    
    num_nodes = adj_matrix.shape[0]
    num_features = feature_matrix.shape[1]
    
    adj_tensor = torch.FloatTensor(adj_matrix)
    x_tensor = torch.FloatTensor(feature_matrix)
    
    model = GraphAutoEncoder(num_features=num_features)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    
    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        adj_hat = model(x_tensor, adj_tensor)
        
        # Binary Cross Entropy Loss between true topology and reconstructed topology
        loss = F.binary_cross_entropy(adj_hat, adj_tensor)
        loss.backward()
        optimizer.step()
        
    model.eval()
    with torch.no_grad():
        final_adj_hat = model(x_tensor, adj_tensor)
        # Calculate Mean Absolute Error (MAE) of the topology reconstruction
        structural_error = torch.mean(torch.abs(adj_tensor - final_adj_hat)).item()
        
    return float(structural_error)

def evaluate_lineage_drift(df: pd.DataFrame, numeric_cols: list[str]) -> dict:
    """
    Compares the current structural graph against the historical baseline.
    """
    if len(numeric_cols) < 3:
        return {"status": "skipped", "reason": "Not enough numeric features for graph modeling."}
        
    logger.info("Constructing ETL Lineage Graph Topology...")
    pandas_df = df[numeric_cols].copy().fillna(0)
    
    # 1. Build Current Graph
    current_adj = build_empirical_adjacency(pandas_df)
    
    # Node features: Let's use simple statistical moments as the feature vectors [Mean, Variance, Skew]
    node_features = np.column_stack([
        pandas_df.mean().values,
        pandas_df.var().values,
        pandas_df.skew().fillna(0).values
    ])
    # Normalize node features
    node_features = np.nan_to_num((node_features - node_features.mean(axis=0)) / (node_features.std(axis=0) + 1e-8))

    # 2. Score the Current Topology
    current_structural_error = train_gae_and_score(current_adj, node_features)
    
    # 3. Compare with Baseline
    drift_detected = False
    baseline_error = 0.0
    # Generate a schema-specific baseline filename so different datasets don't collide
    import hashlib
    schema_string = ",".join(sorted(numeric_cols))
    schema_hash = hashlib.md5(schema_string.encode('utf-8')).hexdigest()[:12]
    dataset_baseline_path = os.path.join(os.path.dirname(BASELINE_GRAPH_PATH), f"baseline_stats_{schema_hash}.json")

    os.makedirs(os.path.dirname(dataset_baseline_path), exist_ok=True)
    if os.path.exists(dataset_baseline_path):
        try:
            with open(dataset_baseline_path, "r") as f:
                baseline_data = json.load(f)
                baseline_error = baseline_data.get("structural_error", 0.0)
                
            # Drift is detected if the reconstruction error deviates significantly
            # (either spikes, or drops because the topology collapsed and became simpler)
            if abs(current_structural_error - baseline_error) / max(baseline_error, 1e-5) > 0.10:
                drift_detected = True
                logger.warning("LINEAGE DRIFT DETECTED: Upstream topology collapsed! (Error: %.4f vs Baseline: %.4f)", current_structural_error, baseline_error)
        except Exception as e:
            logger.error("Failed to read baseline graph: %s", e)
            
    # Save current as new baseline if no baseline exists
    if not os.path.exists(dataset_baseline_path) or baseline_error == 0.0:
        logger.info("Saving initial ETL Lineage Graph baseline for this schema.")
        with open(dataset_baseline_path, "w") as f:
            json.dump({"structural_error": current_structural_error}, f)
            
    return {
        "status": "success",
        "drift_detected": drift_detected,
        "current_structural_error": round(current_structural_error, 4),
        "baseline_structural_error": round(baseline_error, 4),
        "topology_nodes": len(numeric_cols),
        "topology_edges": int(np.sum(current_adj))
    }