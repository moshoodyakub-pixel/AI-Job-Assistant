import os
import pandas as pd
from datetime import datetime

def generate_daily_report(analyzed_csv_path):
    if not analyzed_csv_path or not os.path.exists(analyzed_csv_path):
        print("No analyzed data found to generate a report.")
        return

    print("\n--- Generating Daily HTML Dashboard ---")
    df = pd.read_csv(analyzed_csv_path)

    # Ensure the reports directory exists
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)

    # Create a timestamped HTML filename
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_filename = f"Job_Report_{date_str}.html"
    report_path = os.path.join(reports_dir, report_filename)

    # Build the HTML and CSS structure
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Daily Job Intelligence Report</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 40px; line-height: 1.6; }}
            h1 {{ color: #2c3e50; border-bottom: 3px solid #2980b9; padding-bottom: 10px; }}
            .summary {{ margin-bottom: 30px; font-size: 1.1em; color: #555; }}
            .job-card {{ background: #fff; padding: 25px; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-left: 6px solid #2980b9; }}
            .job-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
            .job-title {{ font-size: 1.4em; font-weight: bold; color: #2c3e50; }}
            .score {{ font-size: 1.3em; font-weight: bold; padding: 5px 12px; border-radius: 4px; color: white; }}
            .company {{ font-size: 1.1em; font-style: italic; color: #7f8c8d; margin-bottom: 15px; }}
            .reasoning {{ background-color: #f8f9fa; padding: 15px; border-left: 4px solid #f39c12; font-size: 1em; color: #444; border-radius: 0 4px 4px 0; }}
            .apply-btn {{ display: inline-block; margin-top: 20px; padding: 12px 20px; background-color: #2980b9; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; transition: background 0.3s; }}
            .apply-btn:hover {{ background-color: #1a5276; }}
        </style>
    </head>
    <body>
        <h1>Daily Job Intelligence Report</h1>
        <div class="summary"><strong>Date:</strong> {date_str} <br> <strong>Total Roles Evaluated:</strong> {len(df)}</div>
    """

    # Populate the HTML with job data
    for index, row in df.iterrows():
        title = row.get('Title', 'Unknown Title')
        company = row.get('Company', 'Unknown Company')
        score = row.get('Match Score', 0)
        reasoning = row.get('Reasoning', 'No reasoning provided.')
        link = row.get('Link', '#')

        # Safely convert score to integer for color coding
        try:
            score_val = int(float(score))
        except (ValueError, TypeError):
            score_val = 0

        # Dynamic color coding: Green for 7-10, Orange for 4-6, Red for 0-3
        if score_val >= 7:
            score_color = "#27ae60" # Green
        elif score_val >= 4:
            score_color = "#f39c12" # Orange
        else:
            score_color = "#e74c3c" # Red

        html_content += f"""
        <div class="job-card" style="border-left-color: {score_color};">
            <div class="job-header">
                <div class="job-title">{title}</div>
                <div class="score" style="background-color: {score_color};">{score_val}/10</div>
            </div>
            <div class="company">{company}</div>
            <div class="reasoning"><strong>AI Evaluation:</strong><br>{reasoning}</div>
            <a href="{link}" class="apply-btn" target="_blank">View Application</a>
        </div>
        """

    # Close HTML tags
    html_content += """
    </body>
    </html>
    """

    # Write out the HTML file
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Report successfully generated at: {report_path}")
    
    # Automatically open the HTML file in the default web browser
    os.startfile(report_path)
