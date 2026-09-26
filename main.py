from src.scraper import fetch_linkedin_jobs, fetch_google_jobs
from src.storage import save_jobs_to_csv
from src.matcher import evaluate_jobs_with_gemini
from src.reporter import generate_daily_report

def run_pipeline():
    target_keywords = [
        "Mini-Grid Design Engineer",
        "Power Systems Modeler",
        "Renewable Energy Consultant",
        "Microgrid Design Engineer",
        "Power Systems Network Engineer",
        "Renewable Energy Modeling Engineer",
        "Solar Data Analytics Engineer"
    ]
    
    target_locations = [
        "Nigeria",
        "Remote"
    ]
    
    all_jobs = []

    print("--- Starting AI Job Assistant Pipeline ---")
    
    # 1. Scrape LinkedIn Listings
    print("\n[1/2] Fetching LinkedIn Jobs...")
    for keyword in target_keywords:
        for location in target_locations:
            jobs = fetch_linkedin_jobs(keyword=keyword, location=location)
            all_jobs.extend(jobs)
            print(f"  ├─ Retrieved {len(jobs)} jobs for '{keyword}' in {location}")

    # 2. Scrape Google Jobs Listings via SerpApi
    print("\n[2/2] Fetching Google Jobs...")
    google_jobs = fetch_google_jobs()
    all_jobs.extend(google_jobs)
    print(f"  ├─ Retrieved {len(google_jobs)} jobs from Google Jobs")

    print(f"\nTotal raw jobs collected: {len(all_jobs)}")
    
    # Save raw results and get the batch file path
    batch_file_path = save_jobs_to_csv(all_jobs)
    
    # Hand off the batch file to the AI matcher
    if batch_file_path:
        analyzed_file_path = evaluate_jobs_with_gemini(batch_file_path)
        
        # Hand off the analyzed file to the reporter
        if analyzed_file_path:
            generate_daily_report(analyzed_file_path)
    
    print("--- Pipeline Execution Complete ---")

if __name__ == "__main__":
    run_pipeline()
