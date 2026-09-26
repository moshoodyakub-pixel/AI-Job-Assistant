import json
import re
import time

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

ENGINEERING_PROFILE = """
- Techno-economic optimization, hybrid system sizing, and mini-grid design.
- Power systems modeling, load flow, short circuit, and relay coordination using ETAP, HOMER Pro, and PVsyst.
- Python energy analytics using Pandas and NumPy for cleaning raw energy-log data and creating hourly time-series profiles.
- Geospatial mapping with QGIS and electrical schematic drafting in AutoCAD.
- Renewable-energy, solar, distribution-network, and power-system engineering experience.
""".strip()

# The current free-tier error reported a 5-request/minute Gemini quota.
# Ten jobs per request dramatically reduces API calls, and 15 seconds between
# requests keeps the client comfortably below that rate.
BATCH_SIZE = 10
MIN_REQUEST_INTERVAL_SECONDS = 15
MAX_RETRIES = 3


def _clean_value(value, max_chars=None):
    if pd.isna(value):
        text = ""
    else:
        text = str(value).strip()

    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n[Description truncated]"
    return text


def _retry_delay_from_error(exc, default_seconds=60):
    """Extract Gemini's suggested retry delay from a 429 error when present."""
    message = str(exc)

    patterns = [
        r"Please retry in\s+([0-9.]+)s",
        r"retryDelay['\"]?\s*:\s*['\"]([0-9.]+)s",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            try:
                return max(float(match.group(1)) + 2, MIN_REQUEST_INTERVAL_SECONDS)
            except ValueError:
                pass

    return max(default_seconds, MIN_REQUEST_INTERVAL_SECONDS)


def _wait_for_rate_limit(last_request_time):
    """Ensure successive Gemini calls stay safely under the request/minute cap."""
    if last_request_time is None:
        return

    elapsed = time.monotonic() - last_request_time
    remaining = MIN_REQUEST_INTERVAL_SECONDS - elapsed
    if remaining > 0:
        print(f"  Rate-limit pacing: waiting {remaining:.1f}s before next Gemini request...")
        time.sleep(remaining)


def _build_job_payload(row, job_id):
    description = _clean_value(row.get("Description"), max_chars=4000)
    if not description:
        description = (
            "No job description was captured by the source. Evaluate conservatively "
            "using the available metadata and lower confidence where appropriate."
        )

    return {
        "job_id": job_id,
        "title": _clean_value(row.get("Title")) or "Unknown Title",
        "company": _clean_value(row.get("Company")) or "Unknown Company",
        "actual_location": _clean_value(row.get("Location")) or "Location not provided",
        "search_location": _clean_value(row.get("SearchLocation")) or "Not recorded",
        "market": _clean_value(row.get("Market")) or "Not classified",
        "work_arrangement": _clean_value(row.get("WorkArrangement")) or "Unspecified",
        "source": _clean_value(row.get("Source")) or "Unknown source",
        "description": description,
    }


def _build_batch_prompt(job_payloads):
    jobs_json = json.dumps(job_payloads, ensure_ascii=False, indent=2)

    return f"""
Act as an expert technical recruiter in renewable energy, electrical power systems, solar, and mini-grid engineering.

CANDIDATE PROFILE
{ENGINEERING_PROFILE}

You will evaluate MULTIPLE job listings in one request.

JOB LISTINGS
{jobs_json}

For every job_id supplied above, return exactly one evaluation.

Rules:
1. Rate each job from 1 to 10, where 10 is an excellent fit.
2. Evaluate the complete listing, not just the title.
3. Give the strongest weight to actual responsibilities, required technical skills, engineering discipline, seniority, and location/work arrangement.
4. Do not assume a generic word such as "network" means electrical power. Distinguish telecom/IT networking from power/distribution networks using the description and company context.
5. Penalize roles that are mainly mechanical, sales, business development, software/IT, telecom, or another discipline unless the listing clearly overlaps the candidate's power/renewable-energy expertise.
6. If the description is missing or vague, do not invent requirements. State that confidence is lower.
7. Keep each reasoning concise and evidence-based.
8. Preserve the exact integer job_id so the results can be matched back to the correct job.
"""


def evaluate_jobs_with_gemini(jobs_df):
    """
    Evaluate all jobs from an in-memory DataFrame.

    Jobs are evaluated in batches rather than one API request per job. This
    reduces API usage substantially and prevents the free-tier 5 RPM quota from
    being exhausted during normal runs. No CSV is written to disk.
    """
    if jobs_df is None or jobs_df.empty:
        print("No jobs available for AI matching.")
        return None

    print("\n--- Starting AI Job Matching ---")
    df = jobs_df.copy().reset_index(drop=True)

    try:
        client = genai.Client()
    except Exception as exc:
        print(f"Failed to initialize Gemini Client. Check your API key. Error: {exc}")
        return None

    total_jobs = len(df)
    total_batches = (total_jobs + BATCH_SIZE - 1) // BATCH_SIZE
    analyzed_jobs = []
    last_request_time = None

    print(
        f"Evaluating ALL {total_jobs} jobs in {total_batches} Gemini batch(es) "
        f"of up to {BATCH_SIZE} jobs each...\n"
    )

    response_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "job_id": {"type": "INTEGER"},
                "match_score": {"type": "INTEGER"},
                "reasoning": {"type": "STRING"},
            },
            "required": ["job_id", "match_score", "reasoning"],
        },
    }

    for batch_number, start in enumerate(range(0, total_jobs, BATCH_SIZE), start=1):
        batch_df = df.iloc[start : start + BATCH_SIZE]
        payloads = [
            _build_job_payload(row, int(job_id))
            for job_id, row in batch_df.iterrows()
        ]
        prompt = _build_batch_prompt(payloads)

        result_data = None
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            _wait_for_rate_limit(last_request_time)

            try:
                print(
                    f"Batch {batch_number}/{total_batches}: sending "
                    f"{len(payloads)} job(s) to Gemini (attempt {attempt})..."
                )
                last_request_time = time.monotonic()

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                        response_schema=response_schema,
                    ),
                )

                parsed = json.loads(response.text)
                if not isinstance(parsed, list):
                    raise ValueError("Gemini batch response was not a JSON array.")

                result_data = parsed
                break

            except Exception as exc:
                last_error = exc
                is_rate_limit = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)

                if attempt >= MAX_RETRIES:
                    break

                if is_rate_limit:
                    wait_seconds = _retry_delay_from_error(exc)
                    print(
                        f"  Gemini rate limit reached. Waiting {wait_seconds:.1f}s "
                        f"before retry {attempt + 1}/{MAX_RETRIES}..."
                    )
                else:
                    wait_seconds = max(5 * attempt, MIN_REQUEST_INTERVAL_SECONDS)
                    print(
                        f"  Gemini batch attempt {attempt} failed: {exc}\n"
                        f"  Retrying in {wait_seconds:.1f}s..."
                    )

                time.sleep(wait_seconds)

        if result_data is None:
            print(
                f"Batch {batch_number}/{total_batches} could not be analyzed after "
                f"{MAX_RETRIES} attempts: {last_error}"
            )
            # Keep these jobs in the final report instead of silently dropping them.
            for job_id, row in batch_df.iterrows():
                analyzed_jobs.append(
                    {
                        "Title": _clean_value(row.get("Title")) or "Unknown Title",
                        "Company": _clean_value(row.get("Company")) or "Unknown Company",
                        "Location": _clean_value(row.get("Location")) or "Location not provided",
                        "SearchLocation": _clean_value(row.get("SearchLocation")) or "Not recorded",
                        "Market": _clean_value(row.get("Market")) or "Not classified",
                        "Priority": row.get("Priority", 99),
                        "WorkArrangement": _clean_value(row.get("WorkArrangement")) or "Unspecified",
                        "Source": _clean_value(row.get("Source")) or "Unknown source",
                        "Description": _clean_value(row.get("Description")),
                        "Match Score": 0,
                        "Reasoning": "AI evaluation unavailable because the Gemini API request failed after retries.",
                        "Link": _clean_value(row.get("Link")),
                    }
                )
            continue

        results_by_id = {}
        for item in result_data:
            try:
                results_by_id[int(item.get("job_id"))] = item
            except (TypeError, ValueError, AttributeError):
                continue

        for job_id, row in batch_df.iterrows():
            item = results_by_id.get(int(job_id), {})

            try:
                score = int(item.get("match_score", 0))
            except (TypeError, ValueError):
                score = 0

            if score:
                score = max(1, min(10, score))

            reasoning = str(item.get("reasoning", "")).strip()
            if not reasoning:
                reasoning = "Gemini did not return an evaluation for this job in the batch."

            analyzed_jobs.append(
                {
                    "Title": _clean_value(row.get("Title")) or "Unknown Title",
                    "Company": _clean_value(row.get("Company")) or "Unknown Company",
                    "Location": _clean_value(row.get("Location")) or "Location not provided",
                    "SearchLocation": _clean_value(row.get("SearchLocation")) or "Not recorded",
                    "Market": _clean_value(row.get("Market")) or "Not classified",
                    "Priority": row.get("Priority", 99),
                    "WorkArrangement": _clean_value(row.get("WorkArrangement")) or "Unspecified",
                    "Source": _clean_value(row.get("Source")) or "Unknown source",
                    "Description": _clean_value(row.get("Description")),
                    "Match Score": score,
                    "Reasoning": reasoning,
                    "Link": _clean_value(row.get("Link")),
                }
            )

            print(
                f"[{job_id + 1}/{total_jobs}] Analyzed: "
                f"{_clean_value(row.get('Title')) or 'Unknown Title'} -> {score}/10"
            )

    if not analyzed_jobs:
        return None

    results_df = pd.DataFrame(analyzed_jobs)
    results_df["Priority"] = pd.to_numeric(
        results_df["Priority"], errors="coerce"
    ).fillna(99)
    results_df = results_df.sort_values(
        by=["Priority", "Match Score"], ascending=[True, False]
    ).reset_index(drop=True)

    successful_count = int((results_df["Match Score"] > 0).sum())
    print(
        f"\nAI Matching complete! {successful_count}/{total_jobs} jobs received "
        "an AI score."
    )
    print("Analyzed results kept in memory only; no CSV was saved.")
    return results_df
