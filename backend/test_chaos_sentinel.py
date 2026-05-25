import pandas as pd
import numpy as np
import requests
import json
import time

API_URL = "http://localhost:8000/api"
HEADERS = {"Authorization": "Bearer YOUR_DS_API_KEY"} # Adjust if auth is enabled

def generate_clean_synthetic_data(num_rows=1000):
    print("Generating clean demographic/financial baseline dataset...")
    np.random.seed(42)
    age = np.random.normal(35, 10, num_rows).clip(18, 90)
    # Perfectly correlated structural rule: Income is roughly 1500 * Age + noise
    income = (1500 * age) + np.random.normal(0, 5000, num_rows)
    tax_paid = (0.20 * income) + np.random.normal(0, 500, num_rows)
    
    df = pd.DataFrame({
        "Patient_ID": [f"USR_{i:04d}" for i in range(num_rows)],
        "Age": age,
        "Income": income,
        "Tax_Paid": tax_paid
    })
    return df

def inject_chaos(df):
    print("Injecting adversarial permutations into dataset...")
    df_chaos = df.copy()
    
    # Anomaly 1: Neuro-Symbolic / SBVR violation (Impossible row value)
    df_chaos.at[10, "Age"] = -15 
    
    # Anomaly 2: Covariate Shift (Subtle boundary push)
    df_chaos.at[50, "Age"] = 42.0
    df_chaos.at[50, "Income"] = 120000.0 # Way too high for a 42-year-old in this distribution
    
    # Anomaly 3: Upstream ETL Pipeline Failure (Topological Lineage Collapse)
    # We break the physical correlation loop between Income and Tax Paid for a chunk of data
    # (Simulating a failed SQL JOIN or corrupted column shift upstream)
    df_chaos.loc[500:1000, "Tax_Paid"] = np.random.normal(500, 50, 500)
    
    return df_chaos

def run_pipeline_test():
    # 1. Save clean baseline data to create baseline graph & stats
    df_clean = generate_clean_synthetic_data()
    df_clean.to_csv("test_baseline.csv", index=False)
    
    # 2. Save mutated data to evaluate advanced detectors
    df_chaos = inject_chaos(df_clean)
    df_chaos.to_csv("test_chaos.csv", index=False)
    
    print("\n--- STAGE 1: Uploading Clean Data to establish system baseline ---")
    with open("test_baseline.csv", "rb") as f:
        res_base = requests.post(f"{API_URL}/upload/", files={"file": f}, headers=HEADERS).json()
    base_session = res_base["session_id"]
    print(f"Baseline Session Created: {base_session}")
    
    # Trigger insights once to build the initial GAE network structure and baseline json files
    requests.get(f"{API_URL}/insights/{base_session}", headers=HEADERS)
    time.sleep(2) # Allow threads to sync down
    
    print("\n--- STAGE 2: Uploading Chaos Data to trigger advanced features ---")
    with open("test_chaos.csv", "rb") as f:
        res_chaos = requests.post(f"{API_URL}/upload/?algorithm=lnn_autoencoder", files={"file": f}, headers=HEADERS).json()
    chaos_session = res_chaos["session_id"]
    print(f"Chaos Session Created: {chaos_session}")
    
    print("\n--- STAGE 3: Fetching Deep Architectural Insights ---")
    insights = requests.get(f"{API_URL}/insights/{chaos_session}", headers=HEADERS).json()
    
    print("\n=== SYSTEM VERIFICATION LOG ===")
    print(f"Detected Domain: {insights['domain_detected']}")
    print(f"Calculated Human Trust Score (HTS): {insights['trust_metrics']['trust_score']}%")
    print(f"GAE Graph Structure: {insights['lineage_topology']['topology_nodes']} Nodes / {insights['lineage_topology']['topology_edges']} Edges")
    print(f"ETL Lineage Collapse Status: {insights['lineage_topology']['drift_detected']}")
    print(f"Current Structural Error: {insights['lineage_topology'].get('current_structural_error')}")
    print(f"Baseline Structural Error: {insights['lineage_topology'].get('baseline_structural_error')}")
    
    print("\n--- STAGE 4: Triggering Reinforcement Learning Remediation Loop ---")
    clean_res = requests.post(f"{API_URL}/clean/{chaos_session}?action=impute", headers=HEADERS).json()
    print("ReClean Agent Execution Summary:")
    print(json.dumps(clean_res["reclean_report"], indent=2))

if __name__ == "__main__":
    run_pipeline_test()