import os
import json
import pandas as pd
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables (API Key) from .env
load_dotenv()

def evaluate_jobs_with_gemini(batch_file_path):
    if not batch_file_path or not os.path.exists(batch_file_path):
        print("No valid batch file provided for AI matching.")
        return None

    print(f"\n--- Starting AI Job Matching ---")
    df = pd.read_csv(batch_file_path)
    
    # Initialize Google GenAI client
    try:
        client = genai.Client()
    except Exception as e:
        print(f"Failed to initialize Gemini Client. Check your API key. Error: {e}")
        return None
        
    analyzed_jobs = []
    
    # To test the pipeline quickly, we will evaluate just the first 5 jobs.
    # Once you confirm this works, you can remove the .head(5) to process the entire batch.
    sample_df = df.head(5) 

    print(f"Evaluating {len(sample_df)} jobs using Gemini 2.5 Flash...\n")

    for index, row in sample_df.iterrows():
        title = row.get('Title', 'Unknown Title')
        company = row.get('Company', 'Unknown Company')
        link = row.get('Link', '')
        
        # We define a recruiter persona targeted exactly to your technical stack
        prompt = f"""
        Act as an expert technical recruiter in the renewable energy and power systems sector.
        Evaluate the following job listing for an engineer with expertise in:
        - Techno-economic optimization, hybrid system sizing, and mini-grid design.
        - Power systems modeling, load flow, short circuit, and relay coordination using ETAP, HOMER Pro, and PVsyst.
        - Python energy analytics, using Pandas and NumPy to clean raw energy log data into hourly time-series profiles.
        - Geospatial mapping with QGIS and electrical schematic drafting in AutoCAD.

        Job Title: {title}
        Company: {company}
        
        Rate this job on a scale of 1 to 10 for how well it matches this specific engineering profile.
        Briefly explain your reasoning.
        """
        
        try:
            # Send the prompt and force the API to return a strict JSON schema
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "match_score": {"type": "INTEGER"},
                            "reasoning": {"type": "STRING"}
                        },
                        "required": ["match_score", "reasoning"]
                    }
                )
            )
            
            # Parse the structured JSON response
            result_data = json.loads(response.text)
            score = result_data.get("match_score", 0)
            reasoning = result_data.get("reasoning", "")
            
            analyzed_jobs.append({
                "Title": title,
                "Company": company,
                "Match Score": score,
                "Reasoning": reasoning,
                "Link": link
            })
            print(f"Analyzed: {title} at {company} -> Score: {score}/10")
            
        except Exception as e:
            print(f"Error analyzing {title}: {e}")
            
    # Save the analyzed results to a new file
    if analyzed_jobs:
        results_df = pd.DataFrame(analyzed_jobs)
        # Sort so the highest-scoring jobs sit at the top of the CSV
        results_df = results_df.sort_values(by="Match Score", ascending=False)
        
        output_file = batch_file_path.replace(".csv", "_analyzed.csv")
        results_df.to_csv(output_file, index=False)
        
        print(f"\nAI Matching complete! Ranked jobs saved to: {output_file}")
        
        # Return the final file path to be picked up by reporter.py
        return output_file 
        
    return None
