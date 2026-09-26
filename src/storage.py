import re

import pandas as pd


def _normalise_text(value):
    text = "" if pd.isna(value) else str(value).strip().lower()
    return re.sub(r"\s+", " ", text)


def _dedupe_key(row):
    """
    Prefer a real URL as the duplicate key. If a source does not provide a
    usable URL, fall back to title + company + location.
    """
    link = _normalise_text(row.get("Link"))
    if link and link not in {"n/a", "#", "none"}:
        return f"url::{link}"

    title = _normalise_text(row.get("Title"))
    company = _normalise_text(row.get("Company"))
    location = _normalise_text(row.get("Location"))
    return f"job::{title}|{company}|{location}"


def prepare_jobs(jobs):
    """
    Prepare scraped jobs entirely in memory.

    No CSV files, master database, reports, or historical job records are
    written to disk. Duplicate removal therefore applies only to the current
    run.
    """
    if not jobs:
        print("No raw jobs collected.")
        return None

    df = pd.DataFrame(jobs)
    if df.empty:
        print("No raw jobs collected.")
        return None

    df["_dedupe_key"] = df.apply(_dedupe_key, axis=1)
    initial_count = len(df)
    df = df.drop_duplicates(subset=["_dedupe_key"], keep="first").copy()
    df.drop(columns=["_dedupe_key"], inplace=True)

    duplicates_filtered = initial_count - len(df)
    if duplicates_filtered:
        print(f"Filtered {duplicates_filtered} duplicate job(s) from this run.")

    if "Priority" in df.columns:
        df["Priority"] = pd.to_numeric(df["Priority"], errors="coerce").fillna(99)
        df = df.sort_values(by="Priority", ascending=True)

    df.reset_index(drop=True, inplace=True)

    print(f"Prepared {len(df)} unique job(s) in memory. Nothing was saved to disk.")
    return df
