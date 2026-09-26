from src.matcher import evaluate_jobs_with_gemini
from src.reporter import generate_daily_report
from src.scraper import fetch_google_jobs, fetch_linkedin_jobs
from src.storage import prepare_jobs


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

    print("\n[3/3] Fetching Google Jobs...")
    google_jobs = fetch_google_jobs()
    all_jobs.extend(google_jobs)
    print(f"  ├─ Retrieved {len(google_jobs)} jobs from Google Jobs")

    all_jobs.sort(key=lambda job: job.get("Priority", 99))

    nigeria_count = sum(job.get("Market") == "Nigeria" for job in all_jobs)
    remote_count = sum(
        job.get("Market") == "International Remote" for job in all_jobs
    )

    print(f"\nTotal raw jobs collected: {len(all_jobs)}")
    print(f"  ├─ Nigeria priority jobs: {nigeria_count}")
    print(f"  └─ International remote jobs: {remote_count}")

    jobs_df = prepare_jobs(all_jobs)

    if jobs_df is not None:
        analyzed_df = evaluate_jobs_with_gemini(jobs_df)
        if analyzed_df is not None:
            generate_daily_report(analyzed_df)

    print("--- Pipeline Execution Complete ---")


if __name__ == "__main__":
    run_pipeline()
