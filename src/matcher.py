import json
import os
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


def _clean_value(value, max_chars=None):
    """Convert DataFrame values to safe prompt text and optionally truncate them."""
    if pd.isna(value):
        text = ""
    else:
        text = str(value).strip()

    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n[Description truncated]"
    return text


def evaluate_jobs_with_gemini(batch_file_path):
    if not batch_file_path or not os.path.exists(batch_file_path):
        print("No valid batch file provided for AI matching.")
        return None

    print("\n--- Starting AI Job Matching ---")
    df = pd.read_csv(batch_file_path)

    if df.empty:
        print("The batch file contains no jobs to evaluate.")
        return None

    try:
        client = genai.Client()
    except Exception as exc:
        print(f"Failed to initialize Gemini Client. Check your API key. Error: {exc}")
        return None

    analyzed_jobs = []
    total_jobs = len(df)
    print(f"Evaluating ALL {total_jobs} jobs using Gemini 2.5 Flash...\n")

    for position, (_, row) in enumerate(df.iterrows(), start=1):
        title = _clean_value(row.get("Title")) or "Unknown Title"
        company = _clean_value(row.get("Company")) or "Unknown Company"
        location = _clean_value(row.get("Location")) or "Location not provided"
        search_location = _clean_value(row.get("SearchLocation")) or "Not recorded"
        market = _clean_value(row.get("Market")) or "Not classified"
        work_arrangement = _clean_value(row.get("WorkArrangement")) or "Unspecified"
        source = _clean_value(row.get("Source")) or "Unknown source"
        description = _clean_value(row.get("Description"), max_chars=7000)
        link = _clean_value(row.get("Link"))

        if not description:
            description = "No job description was captured by the source. Evaluate conservatively using the available metadata and lower confidence where appropriate."

        prompt = f"""
Act as an expert technical recruiter in renewable energy, electrical power systems, solar, and mini-grid engineering.

CANDIDATE PROFILE
{ENGINEERING_PROFILE}

JOB LISTING
Title: {title}
Company: {company}
Actual location: {location}
Search location used to discover it: {search_location}
Market bucket: {market}
Work arrangement: {work_arrangement}
Source: {source}
Description:
{description}

Evaluate the COMPLETE listing above, not just the title.

Rules:
1. Rate the match from 1 to 10, where 10 is an excellent fit.
2. Give the strongest weight to actual responsibilities, required technical skills, engineering discipline, seniority, and location/work arrangement.
3. Do not assume a generic word such as "network" means electrical power; distinguish telecom/IT networking from power/distribution networks using the description and company context.
4. Penalize roles that are mainly mechanical, sales, business development, software/IT, telecom, or another discipline unless the description clearly overlaps the candidate's power/renewable-energy expertise.
5. If the description is missing or too vague, do not invent requirements. Explain that the score has lower confidence.
6. Keep the reasoning concise and evidence-based.
"""

        result_data = None
        last_error = None

        for attempt in range(1, 4):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                        response_schema={
                            "type": "OBJECT",
                            "properties": {
                                "match_score": {"type": "INTEGER"},
                                "reasoning": {"type": "STRING"},
                            },
                            "required": ["match_score", "reasoning"],
                        },
                    ),
                )
                result_data = json.loads(response.text)
                break
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    wait_seconds = attempt * 2
                    print(
                        f"  Gemini attempt {attempt} failed for '{title}'. "
                        f"Retrying in {wait_seconds}s..."
                    )
                    time.sleep(wait_seconds)

        if result_data is None:
            print(f"Error analyzing {title}: {last_error}")
            continue

        try:
            score = int(result_data.get("match_score", 0))
        except (TypeError, ValueError):
            score = 0
        score = max(1, min(10, score)) if score else 0
        reasoning = str(result_data.get("reasoning", "")).strip()

        analyzed_jobs.append(
            {
                "Title": title,
                "Company": company,
                "Location": location,
                "SearchLocation": search_location,
                "Market": market,
                "Priority": row.get("Priority", 99),
                "WorkArrangement": work_arrangement,
                "Source": source,
                "Description": _clean_value(row.get("Description")),
                "Match Score": score,
                "Reasoning": reasoning,
                "Link": link,
            }
        )

        print(
            f"[{position}/{total_jobs}] Analyzed: {title} at {company} "
            f"({location}) -> Score: {score}/10"
        )

        # Small pause reduces burst-rate errors when processing a large batch.
        time.sleep(0.5)

    if not analyzed_jobs:
        return None

    results_df = pd.DataFrame(analyzed_jobs)
    results_df["Priority"] = pd.to_numeric(
        results_df["Priority"], errors="coerce"
    ).fillna(99)

    # Nigeria/primary-market jobs remain ahead of secondary international jobs,
    # while the best matches are ranked first inside each market bucket.
    results_df = results_df.sort_values(
        by=["Priority", "Match Score"],
        ascending=[True, False],
    )

    output_file = batch_file_path.replace(".csv", "_analyzed.csv")
    results_df.to_csv(output_file, index=False)

    print(
        f"\nAI Matching complete! Evaluated {len(results_df)} of {total_jobs} jobs."
    )
    print(f"Ranked jobs saved to: {output_file}")
    return output_file
