from src.scraper import fetch_google_jobs, fetch_linkedin_jobs
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
        "Solar Data Analytics Engineer",
    ]

    all_jobs = []

    print("--- Starting AI Job Assistant Pipeline ---")

    # 1. Primary market: Nigeria. These jobs are collected first and receive
    # priority 1 so downstream processing sees local opportunities first.
    print("\n[1/3] Fetching LinkedIn Nigeria Jobs...")
    for keyword in target_keywords:
        jobs = fetch_linkedin_jobs(
            keyword=keyword,
            location="Nigeria",
            max_results=30,
            market="Nigeria",
        )
        all_jobs.extend(jobs)
        print(f"  ├─ Retrieved {len(jobs)} Nigeria jobs for '{keyword}'")

    # 2. Secondary market: international remote. Limit this pool so it does
    # not dominate the Nigerian opportunities.
    print("\n[2/3] Fetching LinkedIn International Remote Jobs...")
    for keyword in target_keywords:
        jobs = fetch_linkedin_jobs(
            keyword=keyword,
            location="Remote",
            max_results=10,
            market="International Remote",
            remote_only=True,
        )
        all_jobs.extend(jobs)
        print(
            f"  ├─ Retrieved {len(jobs)} international remote jobs "
            f"for '{keyword}'"
        )

    # 3. Google Jobs follows the same Nigeria-first / remote-second strategy.
    print("\n[3/3] Fetching Google Jobs...")
    google_jobs = fetch_google_jobs()
    all_jobs.extend(google_jobs)
    print(f"  ├─ Retrieved {len(google_jobs)} jobs from Google Jobs")

    # Nigeria jobs are always handed to storage/matching before secondary jobs.
    all_jobs.sort(key=lambda job: job.get("Priority", 99))

    nigeria_count = sum(job.get("Market") == "Nigeria" for job in all_jobs)
    remote_count = sum(
        job.get("Market") == "International Remote" for job in all_jobs
    )

    print(f"\nTotal raw jobs collected: {len(all_jobs)}")
    print(f"  ├─ Nigeria priority jobs: {nigeria_count}")
    print(f"  └─ International remote jobs: {remote_count}")

    batch_file_path = save_jobs_to_csv(all_jobs)

    if batch_file_path:
        analyzed_file_path = evaluate_jobs_with_gemini(batch_file_path)

        if analyzed_file_path:
            generate_daily_report(analyzed_file_path)

    print("--- Pipeline Execution Complete ---")


if __name__ == "__main__":
    run_pipeline()
