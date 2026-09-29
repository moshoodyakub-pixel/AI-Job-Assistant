import pandas as pd

from src.matcher import evaluate_jobs_with_gemini
from src.reporter import generate_daily_report
from src.scraper import fetch_google_jobs, fetch_linkedin_jobs
from src.storage import prepare_jobs


# Common titles used by Nigerian solar, power and EPC employers.
NIGERIA_KEYWORDS = [
    "Solar Engineer",
    "Electrical Engineer",
    "Renewable Energy Engineer",
    "Power Systems Engineer",
    "Solar Design Engineer",
    "Solar Project Engineer",
    "Mini-Grid Engineer",
    "Electrical Design Engineer",
    "Electrical Project Engineer",
    "O&M Engineer Solar",
    "Distribution Engineer",
    "Energy Engineer",
]

REMOTE_FALLBACK_KEYWORDS = [
    "Power Systems Engineer",
    "Renewable Energy Engineer",
]

# Keep each daily report concise and keep Gemini usage low.
MAX_AI_JOBS = 15
MIN_LOCAL_JOBS_BEFORE_REMOTE = 8
MAX_REMOTE_FALLBACK_JOBS = 3


def _pre_ai_relevance_score(job):
    """Rank jobs cheaply before Gemini so the strongest local roles go first."""
    title = str(job.get("Title", "")).lower()
    description = str(job.get("Description", "")).lower()
    combined = f"{title} {description}"

    reject_terms = [
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
        "telecom",
    ]
    if any(term in combined for term in reject_terms):
        return -100

    weighted_terms = {
        "solar pv": 9,
        "solar": 7,
        "mini-grid": 9,
        "minigrid": 9,
        "microgrid": 9,
        "power systems": 9,
        "power system": 9,
        "electrical": 6,
        "renewable": 7,
        "distribution": 7,
        "substation": 7,
        "bess": 7,
        "grid": 5,
        "energy": 3,
        "etap": 7,
        "pvsyst": 7,
        "homer": 7,
        "design engineer": 4,
        "project engineer": 4,
        "deployment": 3,
        "operations": 3,
        "maintenance": 3,
    }

    score = sum(weight for term, weight in weighted_terms.items() if term in combined)

    if job.get("Market") == "Nigeria":
        score += 20

    return score


def _filter_and_rank(jobs):
    ranked = []
    removed = 0

    for job in jobs:
        score = _pre_ai_relevance_score(job)
        if score <= 0:
            removed += 1
            continue

        enriched = dict(job)
        enriched["PreAI Score"] = score
        ranked.append(enriched)

    ranked.sort(
        key=lambda job: (
            job.get("Priority", 99),
            -job.get("PreAI Score", 0),
        )
    )
    return ranked, removed


def run_pipeline():
    print("--- Starting AI Job Assistant Pipeline ---")

    # 1. Nigeria: search the last 7 days nationally. This gives enough local
    # jobs without repeating the same keyword across multiple Nigerian cities.
    print("\n[1/3] Fetching LinkedIn Nigeria Jobs (last 7 days)...")
    local_jobs = []

    for keyword in NIGERIA_KEYWORDS:
        jobs = fetch_linkedin_jobs(
            keyword=keyword,
            location="Nigeria",
            max_results=6,
            market="Nigeria",
            recency_days=7,
        )
        local_jobs.extend(jobs)
        print(f"  ├─ Retrieved {len(jobs)} job(s) for '{keyword}'")

    # 2. Google Jobs: Nigeria only.
    print("\n[2/3] Fetching Google Jobs (Nigeria)...")
    google_jobs = fetch_google_jobs(include_international_remote=False)
    local_jobs.extend(google_jobs)
    print(f"  ├─ Retrieved {len(google_jobs)} Nigeria job(s) from Google Jobs")

    ranked_local_jobs, removed_local = _filter_and_rank(local_jobs)
    if removed_local:
        print(
            f"Pre-AI filter removed {removed_local} clearly off-discipline local job(s)."
        )

    local_df = prepare_jobs(ranked_local_jobs)
    if local_df is None or local_df.empty:
        print("No relevant Nigeria jobs were available for analysis.")
        return

    if "PreAI Score" in local_df.columns:
        local_df = local_df.sort_values(
            by="PreAI Score", ascending=False
        ).reset_index(drop=True)

    local_unique_count = len(local_df)
    print(f"Relevant unique Nigeria jobs available: {local_unique_count}")

    # 3. Only use international remote as a fallback when Nigeria is unusually
    # quiet. Most normal runs should skip this stage entirely.
    remote_df = None
    if local_unique_count < MIN_LOCAL_JOBS_BEFORE_REMOTE:
        print("\n[3/3] Local pool is small; fetching limited remote fallback...")
        remote_jobs = []

        for keyword in REMOTE_FALLBACK_KEYWORDS:
            jobs = fetch_linkedin_jobs(
                keyword=keyword,
                location="Remote",
                max_results=2,
                market="International Remote",
                remote_only=True,
                recency_days=3,
            )
            remote_jobs.extend(jobs)
            print(f"  ├─ Retrieved {len(jobs)} remote job(s) for '{keyword}'")

        ranked_remote_jobs, _ = _filter_and_rank(remote_jobs)
        remote_df = prepare_jobs(ranked_remote_jobs)
        if remote_df is not None and not remote_df.empty:
            if "PreAI Score" in remote_df.columns:
                remote_df = remote_df.sort_values(
                    by="PreAI Score", ascending=False
                ).reset_index(drop=True)
            remote_df = remote_df.head(MAX_REMOTE_FALLBACK_JOBS)
    else:
        print("\n[3/3] Skipping international remote: enough Nigeria jobs found.")

    selected_local_df = local_df.head(MAX_AI_JOBS)

    if remote_df is not None and not remote_df.empty:
        remaining_slots = max(0, MAX_AI_JOBS - len(selected_local_df))
        jobs_df = pd.concat(
            [selected_local_df, remote_df.head(remaining_slots)],
            ignore_index=True,
        )
    else:
        jobs_df = selected_local_df.reset_index(drop=True)

    nigeria_count = int((jobs_df["Market"] == "Nigeria").sum())
    remote_count = int((jobs_df["Market"] == "International Remote").sum())

    print("\nFinal analysis queue:")
    print(f"  ├─ Nigeria jobs: {nigeria_count}")
    print(f"  ├─ International remote jobs: {remote_count}")
    print(f"  └─ Total ranked jobs: {len(jobs_df)} (hard cap: {MAX_AI_JOBS})")

    analyzed_df = evaluate_jobs_with_gemini(jobs_df)
    if analyzed_df is not None:
        generate_daily_report(analyzed_df)

    print("--- Pipeline Execution Complete ---")


if __name__ == "__main__":
    run_pipeline()
