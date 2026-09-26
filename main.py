from src.matcher import evaluate_jobs_with_gemini
from src.reporter import generate_daily_report
from src.scraper import fetch_google_jobs, fetch_linkedin_jobs
from src.storage import prepare_jobs


NIGERIA_KEYWORDS = [
    "Solar Engineer",
    "Electrical Engineer",
    "Renewable Energy Engineer",
    "Power Systems Engineer",
    "Solar PV Engineer",
    "Mini-Grid Engineer",
    "Electrical Design Engineer",
    "Project Engineer Solar",
    "Operations Maintenance Engineer Solar",
    "Energy Analyst",
    "Distribution Engineer",
    "Energy Systems Engineer",
]

# Search Nigeria nationally plus the main hiring hubs. Duplicates are removed
# later in memory, so broader geographic coverage is more valuable here.
NIGERIA_SEARCH_LOCATIONS = [
    "Nigeria",
    "Lagos, Nigeria",
    "Abuja, Nigeria",
    "Ogun, Nigeria",
    "Port Harcourt, Nigeria",
]

# Keep international remote as a small fallback only.
REMOTE_FALLBACK_KEYWORDS = [
    "Power Systems Engineer",
    "Renewable Energy Engineer",
    "Solar Engineer",
]


def _looks_relevant_before_ai(job):
    """
    Cheap rule-based screening before Gemini.

    This removes obvious off-discipline results that would waste limited API
    quota, while keeping broad electrical/energy roles for Gemini to judge.
    """
    title = str(job.get("Title", "")).lower()
    description = str(job.get("Description", "")).lower()
    combined = f"{title} {description}"

    strong_reject_terms = [
        "mechanical engineer",
        "business development",
        "sales manager",
        "sales officer",
        "network & it",
        "it support",
        "software engineer",
        "frontend",
        "backend",
        "pcb design",
        "physical design engineer",
        "ic design engineer",
        "silicon",
    ]

    relevant_terms = [
        "solar",
        "renewable",
        "electrical",
        "power system",
        "power systems",
        "mini-grid",
        "minigrid",
        "microgrid",
        "grid",
        "bess",
        "energy",
        "distribution",
        "substation",
        "etap",
        "pvsyst",
        "homer",
    ]

    if any(term in combined for term in strong_reject_terms):
        return False

    return any(term in combined for term in relevant_terms)


def run_pipeline():
    all_jobs = []

    print("--- Starting AI Job Assistant Pipeline ---")

    print("\n[1/3] Fetching LinkedIn Nigeria Jobs...")
    for location in NIGERIA_SEARCH_LOCATIONS:
        for keyword in NIGERIA_KEYWORDS:
            jobs = fetch_linkedin_jobs(
                keyword=keyword,
                location=location,
                max_results=10,
                market="Nigeria",
            )
            all_jobs.extend(jobs)
            if jobs:
                print(
                    f"  ├─ Retrieved {len(jobs)} job(s) for '{keyword}' "
                    f"in {location}"
                )

    print("\n[2/3] Fetching limited International Remote fallback...")
    remote_jobs = []
    for keyword in REMOTE_FALLBACK_KEYWORDS:
        jobs = fetch_linkedin_jobs(
            keyword=keyword,
            location="Remote",
            max_results=2,
            market="International Remote",
            remote_only=True,
        )
        remote_jobs.extend(jobs)
        if jobs:
            print(
                f"  ├─ Retrieved {len(jobs)} remote fallback job(s) "
                f"for '{keyword}'"
            )

    # Hard cap so international remote can never dominate the run.
    all_jobs.extend(remote_jobs[:6])

    print("\n[3/3] Fetching Google Jobs (Nigeria-first)...")
    google_jobs = fetch_google_jobs(include_international_remote=False)
    all_jobs.extend(google_jobs)
    print(f"  ├─ Retrieved {len(google_jobs)} jobs from Google Jobs")

    raw_count = len(all_jobs)
    nigeria_count = sum(job.get("Market") == "Nigeria" for job in all_jobs)
    remote_count = sum(
        job.get("Market") == "International Remote" for job in all_jobs
    )

    print(f"\nTotal raw jobs collected: {raw_count}")
    print(f"  ├─ Nigeria priority jobs: {nigeria_count}")
    print(f"  └─ International remote fallback jobs: {remote_count}")

    relevant_jobs = [job for job in all_jobs if _looks_relevant_before_ai(job)]
    filtered_count = raw_count - len(relevant_jobs)
    if filtered_count:
        print(
            f"Pre-AI relevance filter removed {filtered_count} obviously "
            "off-discipline job(s)."
        )

    # Always prioritize Nigeria before the remote fallback.
    relevant_jobs.sort(key=lambda job: job.get("Priority", 99))

    jobs_df = prepare_jobs(relevant_jobs)

    if jobs_df is not None:
        analyzed_df = evaluate_jobs_with_gemini(jobs_df)
        if analyzed_df is not None:
            generate_daily_report(analyzed_df)

    print("--- Pipeline Execution Complete ---")


if __name__ == "__main__":
    run_pipeline()
