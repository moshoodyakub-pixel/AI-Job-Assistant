import os
import random
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from serpapi import GoogleSearch

load_dotenv()


def fetch_linkedin_jobs(keyword, location="Remote", max_results=30):
    """
    Scrapes public LinkedIn job listings with pagination, rate-limiting,
    error handling, and a 24-hour time filter.
    """
    formatted_keyword = keyword.replace(" ", "%20")
    formatted_location = location.replace(" ", "%20")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    jobs = []
    start = 0

    while start < max_results:
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={formatted_keyword}&location={formatted_location}&f_TPR=r86400&start={start}"

        delay = random.uniform(2.5, 4.5)
        time.sleep(delay)

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"  └─ [LinkedIn Warning] Request failed for '{keyword}' in {location} (page {start}): {e}")
            break

        soup = BeautifulSoup(response.text, "lxml")
        job_cards = soup.find_all("li")

        if not job_cards:
            break

        for card in job_cards:
            title_tag = card.find("h3", class_="base-search-card__title")
            company_tag = card.find("h4", class_="base-search-card__subtitle")
            link_tag = card.find("a", class_="base-card__full-link")

            if title_tag and company_tag and link_tag:
                jobs.append({
                    "Title": title_tag.get_text(strip=True),
                    "Company": company_tag.get_text(strip=True),
                    "Location": location,
                    "Link": link_tag.get("href", "").split("?")[0],
                    "Source": "LinkedIn",
                    "Description": ""
                })

        start += 10

    return jobs


def fetch_google_jobs(api_key=None):
    """
    Queries SerpApi for Google Jobs across two targeted segments:
    1. All on-site/hybrid/remote roles located in Nigeria.
    2. Strictly remote roles worldwide.
    """
    key = api_key or os.getenv("SERPAPI_KEY")
    if not key:
        print("  └─ [SerpApi Warning] SERPAPI_KEY not found in environment or .env file.")
        return []

    base_query = '("Mini-Grid" OR "Microgrid" OR "Solar") ("Power Systems Engineer" OR "Design" OR "ETAP" OR "HOMER Pro" OR "PVsyst")'
    google_jobs = []

    # 1. Nigeria Target (Local On-Site and Remote)
    params_nigeria = {
        "engine": "google_jobs",
        "q": base_query,
        "location": "Nigeria",
        "hl": "en",
        "api_key": key,
    }

    # 2. Global Remote Target (Enforced 'Remote' keyword + WFH filter)
    params_remote = {
        "engine": "google_jobs",
        "q": base_query + ' "Remote"',
        "ltype": "1",
        "hl": "en",
        "api_key": key,
    }

    searches = [
        ("Nigeria", params_nigeria),
        ("Global Remote", params_remote),
    ]

    for label, params in searches:
        try:
            print(f"  ├─ Querying Google Jobs ({label})...")
            search = GoogleSearch(params)
            results = search.get_dict().get("jobs_results", [])

            for item in results:
                # Resolve best available link
                link = item.get("share_link")
                if not link and item.get("apply_options"):
                    link = item["apply_options"][0].get("link")

                google_jobs.append({
                    "Title": item.get("title", "N/A"),
                    "Company": item.get("company_name", "N/A"),
                    "Location": item.get("location", label),
                    "Link": link or "N/A",
                    "Source": "Google Jobs",
                    "Description": item.get("description", "")
                })
        except Exception as e:
            print(f"  └─ [SerpApi Error] Failed fetching {label} jobs: {e}")

    return google_jobs


def fetch_all_jobs(linkedin_keywords=None, linkedin_locations=None):
    """
    Runs both scrapers and aggregates the results into a single clean list of dictionaries.
    """
    if linkedin_keywords is None:
        linkedin_keywords = ["Solar Engineer", "Power Systems Engineer"]
    if linkedin_locations is None:
        linkedin_locations = ["Nigeria", "Remote"]

    aggregated_jobs = []

    # 1. Fetch from LinkedIn
    print("[1/2] Scraping LinkedIn listings...")
    for loc in linkedin_locations:
        for kw in linkedin_keywords:
            print(f"  ├─ Scraping LinkedIn: '{kw}' in '{loc}'...")
            scraped = fetch_linkedin_jobs(kw, location=loc, max_results=20)
            aggregated_jobs.extend(scraped)

    # 2. Fetch from Google Jobs via SerpApi
    print("[2/2] Fetching Google Jobs listings...")
    g_jobs = fetch_google_jobs()
    aggregated_jobs.extend(g_jobs)

    print(f"Total raw jobs collected: {len(aggregated_jobs)}")
    return aggregated_jobs
