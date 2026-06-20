import json
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()
client = OpenAI()

MARKDOWN_PATH = Path("data/outputs/sample-bill.md")
LIBRARY_PATH = Path("evidence_type_library.json")
OUTPUT_PATH = Path("data/outputs/filled_evidence_output.json")
RAW_OUTPUT_PATH = Path("data/outputs/llm_raw_output.txt")

MODEL = "gpt-5.4"  # Use the same model that worked in your connection test.


def extract_json_from_text(text: str) -> dict:
    """
    Try to parse model output as JSON.
    Handles cases where the model wraps JSON in ```json ... ```.
    """
    text = text.strip()

    # Remove markdown code fence if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text.strip()).strip()

    return json.loads(text)


def main():
    if not MARKDOWN_PATH.exists():
        raise FileNotFoundError(f"Missing Markdown file: {MARKDOWN_PATH}")

    if not LIBRARY_PATH.exists():
        raise FileNotFoundError(f"Missing evidence library: {LIBRARY_PATH}")

    markdown_text = MARKDOWN_PATH.read_text(encoding="utf-8")
    evidence_library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))

    prompt = f"""
You are an ESG evidence document extraction assistant.

You are given:
1. OCR Markdown extracted from one uploaded evidence document.
2. An evidence type library JSON based on Nora's ISSA 5000-first schema.

Your task:
- Match the document to the best evidence type in the evidence library.
- Extract only information explicitly present in the Markdown.
- Do not invent missing values.
- Use null for missing values.
- Preserve the original document wording where useful.
- Keep source snippets short.
- Return ONLY valid JSON. Do not include markdown, comments, or explanation.

Required output JSON shape:
{{
  "matched_evidence_type_id": null,
  "matched_evidence_type_name": null,
  "match_confidence": "high | medium | low",
  "match_reason": "",
  "extracted_fields": {{
    "customer_name": null,
    "service_address": null,
    "account_number": null,
    "meter_number": null,
    "bill_date": null,
    "billing_period_start": null,
    "billing_period_end": null,
    "usage_quantity": null,
    "usage_unit": null,
    "fuel_or_service_type": null,
    "amount_due": null,
    "total_current_charges": null,
    "raw_activity_data_summary": null
  }},
  "missing_required_fields": [],
  "source_snippets": [
    {{
      "field_name": "",
      "snippet": ""
    }}
  ]
}}

Evidence type library JSON:
{json.dumps(evidence_library, indent=2)}

OCR Markdown:
{markdown_text}
"""

    response = client.responses.create(
        model=MODEL,
        input=prompt,
    )

    raw_output = response.output_text.strip()

    RAW_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_OUTPUT_PATH.write_text(raw_output, encoding="utf-8")

    try:
        parsed = extract_json_from_text(raw_output)
    except Exception as e:
        print("The model output could not be parsed as JSON.")
        print(f"Raw output saved to: {RAW_OUTPUT_PATH}")
        print(f"Error: {e}")
        return

    OUTPUT_PATH.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

    print(f"Saved filled evidence JSON to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()