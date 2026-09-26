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
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _is_nigeria_location(location):
    normalised = _normalise_location(location)
    return any(term in normalised for term in NIGERIA_LOCATION_TERMS)


def _classify_market(actual_location, requested_market):
    if _is_nigeria_location(actual_location):
        return "Nigeria", 1

    if requested_market == "International Remote":
        return "International Remote", 2

    return requested_market, 1 if requested_market == "Nigeria" else 3


def _extract_linkedin_location(card):
    location_tag = card.select_one(".job-search-card__location")
    if location_tag is None:
        location_tag = card.select_one("span[class*='location']")

    if location_tag is None:
        return "Location not provided"

    return location_tag.get_text(" ", strip=True)


def fetch_linkedin_jobs(
    keyword,
    location="Nigeria",
    max_results=20,
    market="Nigeria",
    remote_only=False,
):
    """
    Scrape public LinkedIn job listings from the last 24 hours.

    `Location` is the actual location shown on the LinkedIn card, while
    `SearchLocation` records the search geography used to discover the role.
    `max_results` is enforced exactly so remote fallback searches cannot flood
    the pipeline.
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

    while start < max_results and len(jobs) < max_results:
        params = {
            "keywords": keyword,
            "location": location,
            "f_TPR": "r86400",
            "start": start,
        }

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
            if len(jobs) >= max_results:
                break

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


def fetch_google_jobs(api_key=None, include_international_remote=False, remote_limit=5):
    """
    Search Google Jobs with Nigeria as the default and dominant market.

    The Nigeria query intentionally uses common employer titles/phrases rather
    than highly specialised portfolio terminology. International remote results
    are only fetched when the caller explicitly requests a fallback.
    """
    key = api_key or os.getenv("SERPAPI_KEY")
    if not key:
        print(
            "  └─ [SerpApi Warning] SERPAPI_KEY not found in environment "
            "or .env file."
        )
        return []

    nigeria_query = (
        '("Solar Engineer" OR "Electrical Engineer" OR "Renewable Energy Engineer" '
        'OR "Power Systems Engineer" OR "Solar PV Engineer" OR "Mini-Grid Engineer" '
        'OR "Electrical Design Engineer" OR "Project Engineer" OR "O&M Engineer" '
        'OR "Energy Analyst" OR "Distribution Engineer" OR "Energy Systems Engineer") '
        '(solar OR renewable OR power OR electrical OR grid OR energy OR BESS)'
    )

    remote_query = (
        '("Power Systems Engineer" OR "Renewable Energy Engineer" OR "Solar Engineer") '
        '(solar OR renewable OR grid OR energy) "Remote"'
    )

    searches = [
        (
            "Nigeria",
            "Nigeria",
            {
                "engine": "google_jobs",
                "q": nigeria_query,
                "location": "Nigeria",
                "hl": "en",
                "api_key": key,
            },
            None,
        )
    ]

    if include_international_remote:
        searches.append(
            (
                "International Remote",
                "Remote",
                {
                    "engine": "google_jobs",
                    "q": remote_query,
                    "ltype": "1",
                    "hl": "en",
                    "api_key": key,
                },
                remote_limit,
            )
        )

    google_jobs = []

    for requested_market, search_location, params, result_limit in searches:
        try:
            print(f"  ├─ Querying Google Jobs ({requested_market})...")
            search = GoogleSearch(params)
            results = search.get_dict().get("jobs_results", [])

            if result_limit is not None:
                results = results[:result_limit]

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
