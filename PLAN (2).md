# PLAN.md — Sustentra J2 Evidence Intake OCR Prototype

## 0. Objective
Build a working prototype where a user uploads one sustainability evidence document and the system outputs a J2 Evidence Intake & Classification result using Nora's ISSA 5000-first schema.

The prototype should support this flow:

```text
Upload document
→ OCR / document parsing with AWS Textract
→ extract raw text, key-value pairs, tables, and source references
→ classify document using evidence_type_library.json
→ extract required fields for that evidence type
→ run deterministic J2 validation rules
→ output an auditor-review-ready table and JSON
```

This is Journey 2 evidence intake/classification. It is not final assurance, not final materiality conclusion, and not final emissions calculation.

---

## 1. Product requirements from Nora's J2 schema
The system must:

1. Classify each uploaded document into an evidence type and data type before extraction.
2. Assign one or more ISSA 5000 assertions when relevant.
3. Distinguish evidence role, such as primary activity evidence, supporting evidence, methodology evidence, comparative evidence, external evidence, claim evidence, or representation/remediation evidence.
4. Provide one acceptance recommendation:
   - `accepted_for_extraction`
   - `supporting_evidence_only`
   - `flagged_for_auditor_review`
   - `rejected_excluded`
   - `pending_clarification`
5. Keep OCR confidence optional. Do not make OCR confidence/page count mandatory J2 fields.
6. Retain rationale, missing fields, recommended remediation, and source references.
7. Preserve auditor override fields for later human review.

---

## 2. Recommended AWS setup

### Preferred account approach
Use a company-controlled AWS account if available. Ask Vivian/team for either:

- an AWS IAM Identity Center login, or
- an IAM user/access key created for this prototype only.

Do not use the AWS root account. Do not commit credentials.

### If company account is not available
Use a new personal AWS Free Tier/sandbox account only for synthetic demo documents. Do not upload real client data. Immediately create a budget alert at `$10` or `$20`.

### AWS region
Use one region consistently:

```text
AWS_REGION=us-east-1
```

### Required AWS services

- Amazon S3: store uploaded PDFs/images for Textract async processing.
- Amazon Textract: OCR, forms, tables, and optional queries.
- AWS Budgets: cost guardrail.
- IAM: least-privilege access.

---

## 3. AWS account setup checklist

### 3.1 Create cost guardrail
In AWS Console:

1. Go to AWS Budgets.
2. Create a monthly cost budget.
3. Set budget amount to `$10` or `$20`.
4. Add email alert at 50%, 80%, and 100% actual/forecasted usage.

### 3.2 Create S3 bucket
Create a bucket such as:

```text
sustentra-j2-ocr-dev-<yourname-or-random-suffix>
```

Bucket settings:

- Region: `us-east-1`
- Block all public access: ON
- Bucket versioning: optional, can be OFF for prototype
- Default encryption: ON, SSE-S3 is acceptable for prototype

Suggested folder structure inside bucket:

```text
uploads/
textract-output/
processed/
```

### 3.3 Create IAM policy
Create a least-privilege IAM policy. Replace `YOUR_BUCKET_NAME`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TextractAccess",
      "Effect": "Allow",
      "Action": [
        "textract:AnalyzeDocument",
        "textract:DetectDocumentText",
        "textract:StartDocumentAnalysis",
        "textract:GetDocumentAnalysis",
        "textract:StartDocumentTextDetection",
        "textract:GetDocumentTextDetection"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3BucketListAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME"
    },
    {
      "Sid": "S3ObjectAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
    }
  ]
}
```

Attach this policy to the prototype IAM user or role.

---

## 4. Local development setup

### 4.1 Install AWS CLI
Install AWS CLI v2.

Then verify:

```bash
aws --version
```

### 4.2 Configure credentials
If using IAM access keys:

```bash
aws configure
```

Use:

```text
AWS Access Key ID: provided by AWS/IAM
AWS Secret Access Key: provided by AWS/IAM
Default region name: us-east-1
Default output format: json
```

If using company SSO:

```bash
aws configure sso
aws sso login
```

Verify access:

```bash
aws sts get-caller-identity
aws s3 ls
```

---

## 5. Repo structure

Create or adjust the repo to this structure:

```text
sustentra-j2-ocr-prototype/
  PLAN.md
  README.md
  .gitignore
  .env.example
  requirements.txt
  app.py
  schemas/
    evidence_type_library.json
  prompts/
    j2_classifier_prompt.md
  src/
    config.py
    aws_s3.py
    textract_client.py
    textract_parser.py
    j2_classifier.py
    j2_validation.py
    output_writer.py
  data/
    sample_docs/
    outputs/
  tests/
    test_j2_validation.py
```

Do not commit `.env`, local AWS credential files, or real uploaded documents.

---

## 6. Python environment

### 6.1 Create virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Mac/Linux:

```bash
source .venv/bin/activate
```

### 6.2 requirements.txt

```text
boto3
python-dotenv
pydantic
pandas
streamlit
openai
pytest
```

Install:

```bash
pip install -r requirements.txt
```

### 6.3 .env.example

```text
AWS_REGION=us-east-1
S3_BUCKET=your-sustentra-j2-ocr-dev-bucket
OPENAI_API_KEY=your-openai-api-key-if-using-llm-classification
```

`.gitignore` must include:

```text
.env
.venv/
__pycache__/
data/sample_docs/private/
data/outputs/
.aws/
```

---

## 7. Implementation plan for the coding agent

### Milestone 1 — AWS connectivity
Create:

- `src/config.py`
- `src/aws_s3.py`
- `src/textract_client.py`

Requirements:

1. Load `AWS_REGION` and `S3_BUCKET` from environment variables.
2. Upload a local PDF/image to `s3://bucket/uploads/<filename>`.
3. Start Textract analysis with `FeatureTypes=["FORMS", "TABLES"]`.
4. Poll `get_document_analysis` until job succeeds or fails.
5. Save raw Textract response to `data/outputs/<filename>_textract_raw.json`.

Use async Textract for PDFs and multi-page documents:

```python
start_document_analysis(
    DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
    FeatureTypes=["FORMS", "TABLES"]
)
```

For a small single-page image/PDF under the synchronous API limit, direct `analyze_document` is acceptable, but the prototype should prefer the S3 async path for reliability.

### Milestone 2 — Parse Textract output
Create `src/textract_parser.py`.

Requirements:

1. Convert Textract `Blocks` into:
   - plain text lines
   - key-value pairs
   - tables
   - source references with page number and block IDs
2. Save parsed output to:

```text
data/outputs/<filename>_parsed.json
```

Target shape:

```json
{
  "full_text": "...",
  "key_values": [
    {"key": "Service Address", "value": "...", "page": 1, "block_ids": []}
  ],
  "tables": [
    {"page": 1, "rows": [["header", "value"]], "block_ids": []}
  ]
}
```

### Milestone 3 — Load Nora evidence type library
Use `schemas/evidence_type_library.json`.

Create `src/j2_classifier.py`.

Requirements:

1. Load evidence type definitions.
2. Send parsed OCR output plus evidence type library to an LLM.
3. Return strict JSON only.
4. Do not let the LLM make final assurance conclusions.

Expected output shape:

```json
{
  "evidence_document": {
    "file_name": "...",
    "evidence_type_predicted": "Natural gas utility bill",
    "evidence_type_id_predicted": "J2-001",
    "data_type": "Raw quantitative activity data",
    "evidence_role_predicted": "Primary activity evidence",
    "related_assertions": ["Responsibility", "Cutoff", "Accuracy & valuation"],
    "regulatory_category_predicted": "Scope 1 stationary combustion",
    "acceptance_status": "pending_rule_validation",
    "acceptance_reason_code": null
  },
  "extracted_fields": [
    {
      "field_name": "billing_period_start",
      "raw_value": "01/01/2025",
      "normalized_value": "2025-01-01",
      "unit": null,
      "required_for_j2_acceptance": true,
      "source_reference": {"page": 1, "text_snippet": "..."}
    }
  ]
}
```

### Milestone 4 — Deterministic J2 validation rules
Create `src/j2_validation.py`.

Requirements:

1. Look up `minimum_j2_acceptance_fields` for predicted evidence type.
2. Check whether all required fields are present.
3. Apply basic rule checks:
   - missing field
   - ambiguous unit
   - missing date/period
   - facility not mapped
   - wrong Scope classification, e.g. electricity bill routed to Scope 1
4. Assign final system recommendation:
   - `accepted_for_extraction`
   - `supporting_evidence_only`
   - `flagged_for_auditor_review`
   - `rejected_excluded`
   - `pending_clarification`
5. Generate `gap_findings` if needed.

Example rule:

```python
def validate_required_fields(classification, evidence_type_definition):
    required = evidence_type_definition["minimum_j2_acceptance_fields"]
    extracted_names = {f["field_name"] for f in classification.get("extracted_fields", []) if f.get("raw_value")}
    missing = [field for field in required if field not in extracted_names]

    if missing:
        return {
            "acceptance_status": "flagged_for_auditor_review",
            "acceptance_reason_code": "missing_required_j2_fields",
            "required_fields_missing": missing,
            "recommended_remediation": "Ask auditor/client to provide or confirm missing fields."
        }

    return {
        "acceptance_status": "accepted_for_extraction",
        "acceptance_reason_code": "minimum_j2_fields_present"
    }
```

### Milestone 5 — Streamlit UI
Create `app.py`.

UI requirements:

1. Upload PDF/image.
2. Button: `Run OCR + J2 Classification`.
3. Show:
   - file name
   - predicted evidence type
   - data type
   - evidence role
   - related assertions
   - required fields found/missing
   - acceptance status
   - recommended remediation
4. Show extracted fields table.
5. Show raw OCR text in expandable section.
6. Add placeholders for auditor override:
   - final evidence type
   - final acceptance status
   - auditor note

### Milestone 6 — Test with sample evidence
Use synthetic/sample documents only.

Test first:

1. Natural gas utility bill.
2. Electricity bill.
3. Fuel receipt/delivery ticket.
4. Fleet fuel card report.
5. Refrigerant service record.
6. Facility register/boundary evidence.

For each test, save:

```text
data/outputs/<filename>_textract_raw.json
data/outputs/<filename>_parsed.json
data/outputs/<filename>_j2_result.json
```

---

## 8. Prompt file for LLM classification
Create `prompts/j2_classifier_prompt.md`.

```text
You are an ISSA 5000-first sustainability evidence intake classifier for Sustentra Journey 2.

Your job is to classify one uploaded evidence document before downstream extraction, testing, calculation, or final assurance conclusion.

You must use the provided evidence_type_library.json as the source of truth.

Do not make final assurance conclusions.
Do not decide final materiality.
Do not invent values not present in the OCR output.
If a field is missing or ambiguous, mark it as missing/ambiguous and recommend auditor review.

Return only valid JSON with this structure:
{
  "evidence_document": {
    "file_name": string,
    "evidence_type_id_predicted": string,
    "evidence_type_predicted": string,
    "data_type": string,
    "evidence_role_predicted": string,
    "related_assertions": string[],
    "disclosure_or_metric_id": string | null,
    "regulatory_category_predicted": string | null,
    "facility_predicted": string | null,
    "source_predicted": string | null,
    "external_source_flag": boolean,
    "acceptance_status": "pending_rule_validation",
    "acceptance_reason_code": null
  },
  "extracted_fields": [
    {
      "field_name": string,
      "raw_value": string | null,
      "normalized_value": string | number | null,
      "unit": string | null,
      "required_for_j2_acceptance": boolean,
      "source_reference": {
        "page": number | null,
        "text_snippet": string | null,
        "block_ids": string[]
      },
      "ambiguity_note": string | null
    }
  ],
  "preliminary_notes": string[]
}
```

---

## 9. Acceptance criteria for the prototype
The prototype is acceptable when:

1. A PDF/image can be uploaded.
2. Textract returns OCR/layout results without manual copy-paste.
3. The system outputs a J2 classification row.
4. The system outputs an extracted fields table.
5. Missing required fields trigger `flagged_for_auditor_review` or `pending_clarification`.
6. The output links back to page/text snippets where possible.
7. The output can be exported as JSON.
8. No credentials or private documents are committed.

---

## 10. Non-goals for this prototype
Do not build these yet:

1. Final emissions calculation.
2. Final materiality conclusion.
3. Final assurance opinion impact.
4. Full regulation RAG.
5. Full user authentication.
6. Production database.
7. Automated email rejection flow.
8. DeepSeek OCR local deployment, unless separately requested as a benchmark.

---

## 11. Short explanation for team
This prototype separates concerns:

```text
Textract = OCR/layout/key-value/table extraction
LLM = map OCR output to Nora's J2 evidence schema
Python rules = deterministic acceptance/gap checks
Auditor UI = human review, override, and notes
```

The key product value is not OCR by itself. The key value is regulation-aware, auditor-ready evidence triage with traceable classification, required field checks, and acceptance recommendations.
