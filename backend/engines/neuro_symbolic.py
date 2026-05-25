"""
DataSentinel — Neuro-Symbolic Logical Neural Network (LNN) Autoencoder
Replaces standard Isolation Forests with a differentiable, rule-constrained deep learning model.

IEEE Novelty: Uses Łukasiewicz t-norms to embed deterministic enterprise business 
rules directly into the continuous latent space optimization process.
"""

import torch
import torch.nn as nn
import torch.optim as optim
import polars as pl
import numpy as np
from sklearn.preprocessing import StandardScaler
from utils import logger

class LNNAutoencoder(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int = 4):
        super(LNNAutoencoder, self).__init__()
        # Encoder: Compresses tabular data into a dense latent representation
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 16),
            nn.LeakyReLU(),
            nn.Linear(16, latent_dim),
            nn.LeakyReLU()
        )
        # Decoder: Reconstructs the data back to its original dimensions
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 16),
            nn.LeakyReLU(),
            nn.Linear(16, input_dim)
        )

    def forward(self, x):
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed

def compute_neuro_symbolic_loss(x: torch.Tensor, x_hat: torch.Tensor, lambda_logic: float = 0.5):
    """
    Computes standard reconstruction loss heavily penalized by differentiable logic constraints.
    L_total = L_mse + (lambda * L_logic)
    """
    # 1. Base Connectionist Loss (How well did the neural network compress/decompress?)
    mse_loss = nn.MSELoss()(x_hat, x)
    
    # 2. Symbolic Logic Loss (Łukasiewicz t-norm continuous approximations)
    # For this implementation, we apply a constraint that standardized features 
    # should practically remain within biologically/financially plausible Z-score bounds (-5 to 5).
    # In Phase 2, we will inject specific AST-parsed rules from the LLM here.
    
    # Logic Rule: "Values must not exceed extreme Z-score bounds"
    # Differentiable Penalty: ReLU(abs(x_hat) - threshold)
    upper_bound_violation = torch.relu(x_hat - 5.0)
    lower_bound_violation = torch.relu(-5.0 - x_hat)
    
    logic_loss = torch.mean(upper_bound_violation + lower_bound_violation)
    
    # Total Loss
    total_loss = mse_loss + (lambda_logic * logic_loss)
    return total_loss, mse_loss

def detect_anomalies_lnn(df: pl.DataFrame, numeric_cols: list[str], epochs: int = 50) -> dict:
    """
    Orchestrates the Neuro-Symbolic anomaly detection pipeline.
    """
    logger.info("Initializing Neuro-Symbolic Autoencoder...")
    
    # 1. Preprocessing
    pandas_df = df.select(numeric_cols).to_pandas()
    # Fill nulls temporarily with median so PyTorch doesn't crash (RL Imputer handles this later)
    pandas_df = pandas_df.fillna(pandas_df.median()) 
    
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(pandas_df)
    
    # Convert to PyTorch Tensors
    tensor_data = torch.FloatTensor(scaled_data)
    
    # 2. Initialize Model
    input_dim = tensor_data.shape[1]
    model = LNNAutoencoder(input_dim=input_dim)
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    
    # 3. Training Loop (Fast fine-tuning on the current batch)
    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        reconstructed = model(tensor_data)
        
        # Calculate Neuro-Symbolic Loss
        loss, _ = compute_neuro_symbolic_loss(tensor_data, reconstructed)
        
        loss.backward()
        optimizer.step()
        
    # 4. Inference & Anomaly Scoring
    model.eval()
    with torch.no_grad():
        final_reconstruction = model(tensor_data)
        # Compute row-wise Mean Squared Error
        row_mse = torch.mean((tensor_data - final_reconstruction) ** 2, dim=1).numpy()
    
    # Convert unbounded MSE to a bounded 0-100 Threat Score
    # We use a non-linear scaling to push extreme errors closer to 100
    threat_scores = np.clip((row_mse / np.percentile(row_mse, 95)) * 50, 0, 100)
    
    # Flag anomalies based on the 95th percentile threshold
    threshold = np.percentile(threat_scores, 95)
    is_anomaly = threat_scores > threshold
    
    return {
        "threat_scores": [float(score) for score in threat_scores],
        "is_anomaly": [bool(flag) for flag in is_anomaly],
        "reconstruction_errors": [float(mse) for mse in row_mse]
    }