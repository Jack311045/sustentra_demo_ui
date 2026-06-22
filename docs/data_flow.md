# Data Flow

## Current demo flow
Workbook + evidence upload
-> selected prepared scenario load
-> adapted analysis response in session state
-> extraction review controls
-> validation checks and reasoning trail
-> calculation and reconciliation review
-> gap analysis actions
-> regulatory assistant context and chat

## Prepared scenario fixtures
- data/demo/mock_outputs/mock_analysis_response_gap_path.json
- data/demo/mock_outputs/mock_analysis_response_clean_path.json
- data/demo/mock_outputs/mock_analysis_response.json (backward-compatible default)

## Split fixture alignment
The default analysis response sections are synchronized with:
- mock_audit_setup.json
- mock_evidence_results.json
- mock_validation_results.json
- mock_calculation_results.json
- mock_reconciliation_summary.json
- mock_gap_tickets.json
- mock_workbook_results.json
- evidence_assets_manifest.json

## Regulatory assistant mode resolution
1. AUDITOR_CHAT_MODE=real -> prefer live RAG; fallback on runtime failure.
2. AUDITOR_CHAT_MODE=mock -> always prepared responses.
3. AUDITOR_CHAT_MODE=auto -> live RAG when configured, otherwise prepared fallback.

Configuration lookup order for RAG values:
1. os.environ
2. local .env
3. Streamlit secrets
