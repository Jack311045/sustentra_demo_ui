import argparse
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import boto3
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")

if not S3_BUCKET:
    raise RuntimeError("Missing S3_BUCKET in .env")

s3 = boto3.client("s3", region_name=AWS_REGION)
textract = boto3.client("textract", region_name=AWS_REGION)
openai_client = OpenAI()


def upload_to_s3(local_path: Path) -> str:
    key = f"uploads/{local_path.name}"
    s3.upload_file(str(local_path), S3_BUCKET, key)
    print(f"[S3] Uploaded to s3://{S3_BUCKET}/{key}")
    return key


def start_textract_job(s3_key: str) -> str:
    response = textract.start_document_analysis(
        DocumentLocation={
            "S3Object": {
                "Bucket": S3_BUCKET,
                "Name": s3_key,
            }
        },
        FeatureTypes=["TABLES"],
    )
    job_id = response["JobId"]
    print(f"[Textract] Started job: {job_id}")
    return job_id


def wait_for_textract(job_id: str) -> None:
    while True:
        response = textract.get_document_analysis(JobId=job_id)
        status = response["JobStatus"]
        print(f"[Textract] Status: {status}")

        if status == "SUCCEEDED":
            return

        if status == "FAILED":
            raise RuntimeError("Textract job failed")

        time.sleep(3)


def get_all_textract_blocks(job_id: str) -> list[dict]:
    blocks = []
    next_token = None

    while True:
        kwargs = {"JobId": job_id}
        if next_token:
            kwargs["NextToken"] = next_token

        response = textract.get_document_analysis(**kwargs)
        blocks.extend(response.get("Blocks", []))
        next_token = response.get("NextToken")

        if not next_token:
            break

    return blocks


def escape_md_cell(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def get_child_text(block: dict, block_map: dict) -> str:
    texts = []

    for rel in block.get("Relationships", []):
        if rel.get("Type") != "CHILD":
            continue

        for child_id in rel.get("Ids", []):
            child = block_map.get(child_id)
            if not child:
                continue

            if child.get("BlockType") == "WORD":
                texts.append(child.get("Text", ""))

            elif child.get("BlockType") == "SELECTION_ELEMENT":
                if child.get("SelectionStatus") == "SELECTED":
                    texts.append("[x]")
                else:
                    texts.append("[ ]")

    return " ".join(texts).strip()


def table_to_markdown(table_block: dict, block_map: dict) -> str:
    cells = []

    for rel in table_block.get("Relationships", []):
        if rel.get("Type") != "CHILD":
            continue

        for child_id in rel.get("Ids", []):
            child = block_map.get(child_id)
            if child and child.get("BlockType") == "CELL":
                cells.append(child)

    if not cells:
        return ""

    max_row = max(cell.get("RowIndex", 1) for cell in cells)
    max_col = max(cell.get("ColumnIndex", 1) for cell in cells)

    grid = [["" for _ in range(max_col)] for _ in range(max_row)]

    for cell in cells:
        row = cell.get("RowIndex", 1) - 1
        col = cell.get("ColumnIndex", 1) - 1
        text = get_child_text(cell, block_map)
        grid[row][col] = escape_md_cell(text)

    grid = [row for row in grid if any(cell.strip() for cell in row)]

    if not grid:
        return ""

    header = grid[0]
    separator = ["---"] * len(header)
    body = grid[1:]

    md_lines = []
    md_lines.append("| " + " | ".join(header) + " |")
    md_lines.append("| " + " | ".join(separator) + " |")

    for row in body:
        md_lines.append("| " + " | ".join(row) + " |")

    return "\n".join(md_lines)


def textract_blocks_to_markdown(blocks: list[dict]) -> str:
    block_map = {block["Id"]: block for block in blocks if "Id" in block}

    lines_by_page = defaultdict(list)
    tables_by_page = defaultdict(list)

    for block in blocks:
        page = block.get("Page", 1)

        if block.get("BlockType") == "LINE" and block.get("Text"):
            lines_by_page[page].append(block["Text"])

        elif block.get("BlockType") == "TABLE":
            table_md = table_to_markdown(block, block_map)
            if table_md:
                tables_by_page[page].append(table_md)

    pages = sorted(set(lines_by_page.keys()) | set(tables_by_page.keys()))
    md_parts = []

    for page in pages:
        md_parts.append(f"# Page {page}\n")

        if lines_by_page.get(page):
            md_parts.append("## Extracted Text\n")
            for line in lines_by_page[page]:
                md_parts.append(line)
            md_parts.append("")

        if tables_by_page.get(page):
            md_parts.append("## Extracted Tables\n")
            for i, table_md in enumerate(tables_by_page[page], start=1):
                md_parts.append(f"### Table {i}\n")
                md_parts.append(table_md)
                md_parts.append("")

    return "\n".join(md_parts)


def extract_json_from_text(text: str) -> dict:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    return json.loads(text)


def fill_evidence_json(markdown_text: str, evidence_library: dict) -> dict:
    prompt = f"""
You are an evidence intake and document extraction assistant.

You are given:
1. OCR Markdown extracted from one uploaded document.
2. A local evidence type library JSON.

The evidence type library JSON is the source of truth. Do not rely on outside ESG knowledge unless needed to understand common document wording.

Your task:
1. Read evidence_library["evidence_types"].
2. Match the uploaded document to exactly one best evidence type.
3. Copy the matched evidence type metadata from the library.
4. Use the matched evidence type's "minimum_j2_acceptance_fields" as the required extraction fields.
5. Extract values from the OCR Markdown for those required fields.
6. Do not invent missing values.
7. Use null for missing values.
8. If a required field is missing, include it in "missing_required_fields".
9. Recommend an acceptance status using only evidence_library["allowed_acceptance_statuses"].
10. Include short source snippets from the Markdown when possible.
11. Return ONLY valid JSON. No markdown fences, no explanation, no comments.

Important:
- This must work for any evidence type in the library, not just natural gas bills.
- Do not hardcode field names from the sample document.
- Do not assume every document is a utility bill.
- The output keys should be stable, but the required field names inside "minimum_required_field_values" must come from the matched evidence type's "minimum_j2_acceptance_fields".
- This is first-pass classification/extraction only, not a final audit conclusion.

Return JSON in this exact shape:
{{
  "source_document_type_guess": "",
  "matched_evidence_type": {{
    "evidence_type_id": null,
    "evidence_type_name": null,
    "default_data_type": null,
    "expected_evidence_role": null,
    "default_regulatory_category": null,
    "expected_assertions": [],
    "minimum_j2_acceptance_fields": [],
    "common_gap_triggers": [],
    "downstream_activity_allowed_by_default": null
  }},
  "match_confidence": "high | medium | low",
  "match_reason": "",
  "minimum_required_field_values": {{
    "FIELD_NAME_FROM_LIBRARY": {{
      "value": null,
      "source_snippet": null
    }}
  }},
  "additional_extracted_fields": {{
    "FIELD_NAME_NOT_REQUIRED_BUT_USEFUL": {{
      "value": null,
      "source_snippet": null
    }}
  }},
  "missing_required_fields": [],
  "detected_gap_triggers": [],
  "acceptance_status_recommendation": {{
    "status": null,
    "label": null,
    "reason": ""
  }},
  "auditor_review_note": ""
}}

Evidence type library JSON:
{json.dumps(evidence_library, indent=2)}

OCR Markdown:
{markdown_text}
"""

    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )

    raw_output = response.output_text.strip()
    return extract_json_from_text(raw_output), raw_output

def run_pipeline(input_file: Path) -> None:
    if not input_file.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_file}")

    evidence_library_path = Path("evidence_type_library.json")
    if not evidence_library_path.exists():
        raise FileNotFoundError("Missing evidence_type_library.json in project root")

    output_dir = Path("data/outputs") / input_file.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Input] {input_file}")
    print(f"[Output folder] {output_dir}")

    s3_key = upload_to_s3(input_file)
    job_id = start_textract_job(s3_key)
    wait_for_textract(job_id)

    blocks = get_all_textract_blocks(job_id)

    raw_textract_output = {
        "source_file": str(input_file),
        "s3_bucket": S3_BUCKET,
        "s3_key": s3_key,
        "job_id": job_id,
        "blocks": blocks,
    }

    textract_json_path = output_dir / "textract_raw.json"
    textract_json_path.write_text(
        json.dumps(raw_textract_output, indent=2),
        encoding="utf-8",
    )
    print(f"[Saved] {textract_json_path}")

    markdown_text = textract_blocks_to_markdown(blocks)
    markdown_path = output_dir / f"{input_file.stem}.md"
    markdown_path.write_text(markdown_text, encoding="utf-8")
    print(f"[Saved] {markdown_path}")

    evidence_library = json.loads(evidence_library_path.read_text(encoding="utf-8"))

    filled_json, raw_llm_output = fill_evidence_json(
        markdown_text=markdown_text,
        evidence_library=evidence_library,
    )

    raw_llm_path = output_dir / "llm_raw_output.txt"
    raw_llm_path.write_text(raw_llm_output, encoding="utf-8")
    print(f"[Saved] {raw_llm_path}")

    filled_json_path = output_dir / "filled_evidence_output.json"
    filled_json_path.write_text(
        json.dumps(filled_json, indent=2),
        encoding="utf-8",
    )
    print(f"[Saved] {filled_json_path}")

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_file",
        help="Path to the input PDF/image document",
    )
    args = parser.parse_args()

    run_pipeline(Path(args.input_file))


if __name__ == "__main__":
    main()