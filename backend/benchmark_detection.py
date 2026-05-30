import time
import polars as pl
from engines.detection import process_and_detect

def run_benchmark():
    file_path = "data/creditcard.csv"
    print(f"Loading {file_path}...")
    start = time.time()
    try:
        df = pl.read_csv(file_path, infer_schema_length=30000)
    except Exception:
        import pandas as pd
        df = pl.from_pandas(pd.read_csv(file_path, low_memory=False))
    print(f"Loaded in {time.time() - start:.2f}s")
    
    print("Running process_and_detect...")
    start = time.time()
    
    # We will temporarily patch print to show timestamps
    import builtins
    original_print = builtins.print
    def ts_print(*args, **kwargs):
        original_print(f"[{time.time() - start:.2f}s]", *args, **kwargs)
    builtins.print = ts_print
    
    import uuid
    process_and_detect(file_path=file_path, df=df, session_id=str(uuid.uuid4()))
    
    builtins.print = original_print
    print(f"Total process_and_detect time: {time.time() - start:.2f}s")

if __name__ == "__main__":
    run_benchmark()
