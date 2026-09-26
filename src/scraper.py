import os
import random
import re
import time

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from serpapi import GoogleSearch

load_dotenv()


NIGERIA_LOCATION_TERMS = (
    "nigeria",
    "abuja",
    "fct",
    "lagos",
    "ogun",
    "kano",
    "kaduna",
    "rivers",
    "port harcourt",
    "oyo",
    "ibadan",
    "enugu",
    "anambra",
    "imo",
    "abia",
    "akwa ibom",
    "cross river",
    "delta",
    "edo",
    "ondo",
    "osun",
    "ekiti",
    "kwara",
    "kogi",
    "nasarawa",
    "niger state",
    "plateau",
    "benue",
    "bauchi",
    "gombe",
    "borno",
    "yobe",
    "adamawa",
    "taraba",
    "jigawa",
    "katsina",
    "kebbi",
    "sokoto",
    "zamfara",
    "ebonyi",
    "bayelsa",
)


def _normalise_location(value):
    """Return a compact, lowercase location string for matching."""
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _is_nigeria_location(location):
    """Best-effort check for Nigerian locations returned by job sources."""
    normalised = _normalise_location(location)
    return any(term in normalised for term in NIGERIA_LOCATION_TERMS)


def _classify_market(actual_location, requested_market):
    """
    Keep Nigerian jobs in the primary market even if they were discovered
    during a broader remote search. Everything else keeps the requested bucket.
    """
    if _is_nigeria_location(actual_location):
        return "Nigeria", 1

    if requested_market == "International Remote":
        return "International Remote", 2

    return requested_market, 1 if requested_market == "Nigeria" else 3


def _extract_linkedin_location(card):
    """Extract the location displayed on a LinkedIn public job card."""
    location_tag = card.select_one(".job-search-card__location")

    if location_tag is None:
        # Fallback for minor LinkedIn markup changes.
        location_tag = card.select_one("span[class*='location']")

    if location_tag is None:
        return "Location not provided"

    return location_tag.get_text(" ", strip=True)


def fetch_linkedin_jobs(
    keyword,
    location="Nigeria",
    max_results=30,
    market="Nigeria",
    remote_only=False,
):
    """
    Scrape public LinkedIn job listings with pagination, rate-limiting,
    error handling, and a 24-hour time filter.

    `Location` is the location shown on the LinkedIn job card. `SearchLocation`
    records the location used in the search so the two are never confused.
    """
    endpoint = (
        "https://www.linkedin.com/jobs-guest/jobs/api/"
        "seeMoreJobPostings/search"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 "
        "Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    jobs = []
    start = 0

    while start < max_results:
        params = {
            "keywords": keyword,
            "location": location,
            "f_TPR": "r86400",
            "start": start,
        }

        # LinkedIn's work-type filter: 2 = remote.
        if remote_only:
            params["f_WT"] = "2"

        time.sleep(random.uniform(2.5, 4.5))

        try:
            response = requests.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            print(
                f"  └─ [LinkedIn Warning] Request failed for '{keyword}' "
                f"in {location} (page {start}): {exc}"
            )
            break

        soup = BeautifulSoup(response.text, "lxml")
        job_cards = soup.find_all("li")

        if not job_cards:
            break

        for card in job_cards:
            title_tag = card.find("h3", class_="base-search-card__title")
            company_tag = card.find("h4", class_="base-search-card__subtitle")
            link_tag = card.find("a", class_="base-card__full-link")

            if not (title_tag and company_tag and link_tag):
                continue

            actual_location = _extract_linkedin_location(card)
            final_market, priority = _classify_market(actual_location, market)

            jobs.append(
                {
                    "Title": title_tag.get_text(strip=True),
                    "Company": company_tag.get_text(strip=True),
                    "Location": actual_location,
                    "SearchLocation": location,
                    "Market": final_market,
                    "Priority": priority,
                    "WorkArrangement": "Remote" if remote_only else "Unspecified",
                    "Link": link_tag.get("href", "").split("?")[0],
                    "Source": "LinkedIn",
                    "Description": "",
                }
            )

        start += 10

    return jobs


def fetch_google_jobs(api_key=None):
    """
    Query SerpApi for Google Jobs in priority order:
    1. Nigeria roles (primary market).
    2. Worldwide remote roles (secondary market).
    """
    key = api_key or os.getenv("SERPAPI_KEY")
    if not key:
        print(
            "  └─ [SerpApi Warning] SERPAPI_KEY not found in environment "
            "or .env file."
        )
        return []

    base_query = (
        '("Mini-Grid" OR "Microgrid" OR "Solar") '
        '("Power Systems Engineer" OR "Design" OR "ETAP" '
        'OR "HOMER Pro" OR "PVsyst")'
    )
    google_jobs = []

    params_nigeria = {
        "engine": "google_jobs",
        "q": base_query,
        "location": "Nigeria",
        "hl": "en",
        "api_key": key,
    }

    params_remote = {
        "engine": "google_jobs",
        "q": base_query + ' "Remote"',
        "ltype": "1",
        "hl": "en",
        "api_key": key,
    }

    searches = [
        ("Nigeria", "Nigeria", params_nigeria),
        ("International Remote", "Remote", params_remote),
    ]

    for requested_market, search_location, params in searches:
        try:
            print(f"  ├─ Querying Google Jobs ({requested_market})...")
            search = GoogleSearch(params)
            results = search.get_dict().get("jobs_results", [])

            for item in results:
                link = item.get("share_link")
                if not link and item.get("apply_options"):
                    link = item["apply_options"][0].get("link")

                actual_location = item.get("location") or "Location not provided"
                final_market, priority = _classify_market(
                    actual_location,
                    requested_market,
                )

                google_jobs.append(
                    {
                        "Title": item.get("title", "N/A"),
                        "Company": item.get("company_name", "N/A"),
                        "Location": actual_location,
                        "SearchLocation": search_location,
                        "Market": final_market,
                        "Priority": priority,
                        "WorkArrangement": (
                            "Remote"
                            if requested_market == "International Remote"
                            else "Unspecified"
                        ),
                        "Link": link or "N/A",
                        "Source": "Google Jobs",
                        "Description": item.get("description", ""),
                    }
                )
        except Exception as exc:
            print(
                f"  └─ [SerpApi Error] Failed fetching "
                f"{requested_market} jobs: {exc}"
            )

    return google_jobs


def fetch_all_jobs(linkedin_keywords=None):
    """Run both scrapers with Nigeria first and remote jobs second."""
    if linkedin_keywords is None:
        linkedin_keywords = ["Solar Engineer", "Power Systems Engineer"]

    aggregated_jobs = []

    print("[1/3] Scraping LinkedIn Nigeria listings...")
    for keyword in linkedin_keywords:
        scraped = fetch_linkedin_jobs(
            keyword,
            location="Nigeria",
            max_results=30,
            market="Nigeria",
        )
        aggregated_jobs.extend(scraped)

    print("[2/3] Scraping secondary LinkedIn remote listings...")
    for keyword in linkedin_keywords:
        scraped = fetch_linkedin_jobs(
            keyword,
            location="Remote",
            max_results=10,
            market="International Remote",
            remote_only=True,
        )
        aggregated_jobs.extend(scraped)

    print("[3/3] Fetching Google Jobs listings...")
    aggregated_jobs.extend(fetch_google_jobs())

    # Make local opportunities deterministic and first in downstream processing.
    aggregated_jobs.sort(key=lambda job: job.get("Priority", 99))

    print(f"Total raw jobs collected: {len(aggregated_jobs)}")
    return aggregated_jobs
