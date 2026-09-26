import pandas as pd

from src.matcher import evaluate_jobs_with_gemini
from src.reporter import generate_daily_report
from src.scraper import fetch_google_jobs, fetch_linkedin_jobs
from src.storage import prepare_jobs


# Use common Nigerian job titles rather than highly specialised portfolio wording.
# One nationwide search is enough; searching the same title again for Lagos,
# Abuja, Ogun, etc. mostly returns duplicates and causes unnecessary requests.
NIGERIA_KEYWORDS = [
    "Solar Engineer",
    "Electrical Engineer",
    "Renewable Energy Engineer",
    "Power Systems Engineer",
    "Solar PV Engineer",
    "Mini-Grid Engineer",
    "Electrical Design Engineer",
    "Distribution Engineer",
    "Energy Analyst",
]

# Remote is only a fallback if the Nigeria search does not produce enough
# relevant local opportunities.
REMOTE_FALLBACK_KEYWORDS = [
    "Power Systems Engineer",
    "Renewable Energy Engineer",
]

MAX_AI_JOBS = 20
MIN_LOCAL_JOBS_BEFORE_REMOTE = 12
MAX_REMOTE_FALLBACK_JOBS = 4


def _pre_ai_relevance_score(job):
    """Cheap local ranking so Gemini only sees the strongest engineering jobs."""
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
        "solar pv": 8,
        "solar": 6,
        "mini-grid": 8,
        "minigrid": 8,
        "microgrid": 8,
        "power systems": 8,
        "power system": 8,
        "electrical": 5,
        "renewable": 6,
        "distribution": 6,
        "substation": 6,
        "bess": 6,
        "grid": 4,
        "energy analyst": 5,
        "energy": 3,
        "etap": 6,
        "pvsyst": 6,
        "homer": 6,
        "design engineer": 3,
        "project engineer": 3,
        "operations": 2,
        "maintenance": 2,
    }

    score = sum(weight for term, weight in weighted_terms.items() if term in combined)

    # Nigerian jobs should always outrank the international fallback.
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

    # ------------------------------------------------------------------
    # 1. Nigeria only: one nationwide search for each useful job title.
    # ------------------------------------------------------------------
    print("\n[1/3] Fetching LinkedIn Nigeria Jobs...")
    local_jobs = []

    for keyword in NIGERIA_KEYWORDS:
        jobs = fetch_linkedin_jobs(
            keyword=keyword,
            location="Nigeria",
            max_results=8,
            market="Nigeria",
        )
        local_jobs.extend(jobs)
        print(f"  ├─ Retrieved {len(jobs)} job(s) for '{keyword}' in Nigeria")

    # ------------------------------------------------------------------
    # 2. Google Jobs: Nigeria only.
    # ------------------------------------------------------------------
    print("\n[2/3] Fetching Google Jobs (Nigeria)...")
    google_jobs = fetch_google_jobs(include_international_remote=False)
    local_jobs.extend(google_jobs)
    print(f"  ├─ Retrieved {len(google_jobs)} Nigeria job(s) from Google Jobs")

    ranked_local_jobs, removed_local = _filter_and_rank(local_jobs)
    if removed_local:
        print(
            f"Pre-AI relevance filter removed {removed_local} obviously "
            "off-discipline local job(s)."
        )

    local_df = prepare_jobs(ranked_local_jobs)
    if local_df is None or local_df.empty:
        print("No relevant Nigeria jobs were available for analysis.")
        return

    if "PreAI Score" in local_df.columns:
        local_df = local_df.sort_values(
            by=["PreAI Score"], ascending=False
        ).reset_index(drop=True)

    local_unique_count = len(local_df)
    print(f"Relevant unique Nigeria jobs available: {local_unique_count}")

    # ------------------------------------------------------------------
    # 3. Remote fallback only when local supply is genuinely small.
    # ------------------------------------------------------------------
    remote_df = None
    if local_unique_count < MIN_LOCAL_JOBS_BEFORE_REMOTE:
        print("\n[3/3] Nigeria pool is small; fetching limited remote fallback...")
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
            print(
                f"  ├─ Retrieved {len(jobs)} remote fallback job(s) "
                f"for '{keyword}'"
            )

        ranked_remote_jobs, removed_remote = _filter_and_rank(remote_jobs)
        if removed_remote:
            print(
                f"Pre-AI relevance filter removed {removed_remote} off-discipline "
                "remote job(s)."
            )

        remote_df = prepare_jobs(ranked_remote_jobs)
        if remote_df is not None and not remote_df.empty:
            if "PreAI Score" in remote_df.columns:
                remote_df = remote_df.sort_values(
                    by=["PreAI Score"], ascending=False
                ).reset_index(drop=True)
            remote_df = remote_df.head(MAX_REMOTE_FALLBACK_JOBS)
    else:
        print("\n[3/3] Skipping international remote search: enough Nigeria jobs found.")

    # Cap the AI workload. With Gemini batching at 10 jobs/request, 20 jobs
    # means at most two normal API calls per run.
    nigeria_cap = MAX_AI_JOBS
    selected_local_df = local_df.head(nigeria_cap)

    if remote_df is not None and not remote_df.empty:
        remaining_slots = max(0, MAX_AI_JOBS - len(selected_local_df))
        selected_remote_df = remote_df.head(remaining_slots)
        jobs_df = pd.concat(
            [selected_local_df, selected_remote_df], ignore_index=True
        )
    else:
        jobs_df = selected_local_df.reset_index(drop=True)

    nigeria_count = int((jobs_df["Market"] == "Nigeria").sum())
    remote_count = int((jobs_df["Market"] == "International Remote").sum())

    print("\nFinal AI analysis queue:")
    print(f"  ├─ Nigeria jobs: {nigeria_count}")
    print(f"  ├─ International remote jobs: {remote_count}")
    print(f"  └─ Total sent to Gemini: {len(jobs_df)} (hard cap: {MAX_AI_JOBS})")

    analyzed_df = evaluate_jobs_with_gemini(jobs_df)
    if analyzed_df is not None:
        generate_daily_report(analyzed_df)

    print("--- Pipeline Execution Complete ---")


if __name__ == "__main__":
    run_pipeline()
