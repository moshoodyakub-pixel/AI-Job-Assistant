import os
import glob
import pandas as pd
from datetime import datetime

MASTER_FILE = os.path.join("data", "master_jobs.csv")

def load_existing_links():
    """
    Scans the data directory for existing CSV files and returns a set of all previously scraped job links.
    """
    seen_links = set()
    
    # Check all CSV files inside the data folder
    for file_path in glob.glob(os.path.join("data", "*.csv")):
        try:
            df = pd.read_csv(file_path)
            if 'Link' in df.columns:
                seen_links.update(df['Link'].dropna().tolist())
        except Exception:
            continue
            
    return seen_links

def save_jobs_to_csv(jobs, filename_prefix="linkedin_jobs"):
    """
    Saves ONLY new, unseen jobs to a master database and a timestamped batch file.
    """
    if not jobs:
        print("No raw jobs collected.")
        return None

    os.makedirs("data", exist_ok=True)

    # 1. Fetch all historically collected job links
    seen_links = load_existing_links()
    if seen_links:
        print(f"Database contains {len(seen_links)} historical job link(s).")

    # 2. Convert incoming raw jobs into a DataFrame and remove intra-batch duplicates
    df_new = pd.DataFrame(jobs)
    df_new.drop_duplicates(subset=['Link'], inplace=True)

    # 3. Filter out jobs that have already been saved in past runs
    initial_count = len(df_new)
    df_new = df_new[~df_new['Link'].isin(seen_links)]
    new_count = len(df_new)
    duplicates_filtered = initial_count - new_count

    if duplicates_filtered > 0:
        print(f"Filtered out {duplicates_filtered} duplicate job(s) from previous runs.")

    if df_new.empty:
        print("No new unique jobs found during this run.")
        return None

    # 4. Save timestamped batch file (contains ONLY new listings for the AI matcher)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_file_path = os.path.join("data", f"{filename_prefix}_{timestamp}.csv")
    df_new.to_csv(batch_file_path, index=False)

    # 5. Append new listings to master_jobs.csv
    if os.path.exists(MASTER_FILE):
        df_new.to_csv(MASTER_FILE, mode='a', header=False, index=False)
    else:
        df_new.to_csv(MASTER_FILE, index=False)

    print(f"Successfully saved {new_count} NEW unique job(s):")
    print(f"  └─ Batch file:  {batch_file_path}")
    print(f"  └─ Master record: {MASTER_FILE}")
    
    return batch_file_path
