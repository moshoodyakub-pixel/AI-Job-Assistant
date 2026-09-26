import html
import os
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd


def _safe_text(value, default=""):
    if pd.isna(value):
        value = default
    return html.escape(str(value))


def _safe_link(value):
    if pd.isna(value):
        return "#"
    link = str(value).strip()
    parsed = urlparse(link)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return html.escape(link, quote=True)
    return "#"


def generate_daily_report(analyzed_csv_path):
    if not analyzed_csv_path or not os.path.exists(analyzed_csv_path):
        print("No analyzed data found to generate a report.")
        return

    print("\n--- Generating Daily HTML Dashboard ---")
    df = pd.read_csv(analyzed_csv_path)

    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    report_filename = f"Job_Report_{date_str}.html"
    report_path = os.path.join(reports_dir, report_filename)

    nigeria_count = int((df.get("Market", pd.Series(dtype=str)) == "Nigeria").sum()) if "Market" in df.columns else 0
    remote_count = int((df.get("Market", pd.Series(dtype=str)) == "International Remote").sum()) if "Market" in df.columns else 0

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Daily Job Intelligence Report</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 40px; line-height: 1.6; }}
            h1 {{ color: #2c3e50; border-bottom: 3px solid #2980b9; padding-bottom: 10px; }}
            .summary {{ margin-bottom: 30px; font-size: 1.05em; color: #555; }}
            .job-card {{ background: #fff; padding: 25px; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-left: 6px solid #2980b9; }}
            .job-header {{ display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 10px; }}
            .job-title {{ font-size: 1.4em; font-weight: bold; color: #2c3e50; }}
            .score {{ font-size: 1.3em; font-weight: bold; padding: 5px 12px; border-radius: 4px; color: white; white-space: nowrap; }}
            .company {{ font-size: 1.1em; font-style: italic; color: #7f8c8d; margin-bottom: 10px; }}
            .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px 20px; margin-bottom: 15px; font-size: 0.95em; color: #555; }}
            .tag {{ display: inline-block; padding: 3px 8px; border-radius: 4px; background: #eef3f7; }}
            .reasoning {{ background-color: #f8f9fa; padding: 15px; border-left: 4px solid #f39c12; font-size: 1em; color: #444; border-radius: 0 4px 4px 0; }}
            .apply-btn {{ display: inline-block; margin-top: 20px; padding: 12px 20px; background-color: #2980b9; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; transition: background 0.3s; }}
            .apply-btn:hover {{ background-color: #1a5276; }}
        </style>
    </head>
    <body>
        <h1>Daily Job Intelligence Report</h1>
        <div class="summary">
            <strong>Date:</strong> {date_str}<br>
            <strong>Total Roles Evaluated:</strong> {len(df)}<br>
            <strong>Nigeria Roles:</strong> {nigeria_count}<br>
            <strong>International Remote Roles:</strong> {remote_count}
        </div>
    """

    for _, row in df.iterrows():
        title = _safe_text(row.get("Title"), "Unknown Title")
        company = _safe_text(row.get("Company"), "Unknown Company")
        location = _safe_text(row.get("Location"), "Location not provided")
        market = _safe_text(row.get("Market"), "Not classified")
        work_arrangement = _safe_text(row.get("WorkArrangement"), "Unspecified")
        source = _safe_text(row.get("Source"), "Unknown source")
        reasoning = _safe_text(row.get("Reasoning"), "No reasoning provided.")
        link = _safe_link(row.get("Link", "#"))
        score = row.get("Match Score", 0)

        try:
            score_val = int(float(score))
        except (ValueError, TypeError):
            score_val = 0

        if score_val >= 7:
            score_color = "#27ae60"
        elif score_val >= 4:
            score_color = "#f39c12"
        else:
            score_color = "#e74c3c"

        html_content += f"""
        <div class="job-card" style="border-left-color: {score_color};">
            <div class="job-header">
                <div class="job-title">{title}</div>
                <div class="score" style="background-color: {score_color};">{score_val}/10</div>
            </div>
            <div class="company">{company}</div>
            <div class="meta">
                <div><strong>Location:</strong> {location}</div>
                <div><strong>Market:</strong> <span class="tag">{market}</span></div>
                <div><strong>Work Arrangement:</strong> {work_arrangement}</div>
                <div><strong>Source:</strong> {source}</div>
            </div>
            <div class="reasoning"><strong>AI Evaluation:</strong><br>{reasoning}</div>
            <a href="{link}" class="apply-btn" target="_blank" rel="noopener noreferrer">View Application</a>
        </div>
        """

    html_content += """
    </body>
    </html>
    """

    with open(report_path, "w", encoding="utf-8") as file:
        file.write(html_content)

    print(f"Report successfully generated at: {report_path}")

    if hasattr(os, "startfile"):
        os.startfile(report_path)
