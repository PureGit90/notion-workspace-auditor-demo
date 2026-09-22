# Notion Workspace Health Auditor — Working Automation Demo

## What This Does
Scans a Notion database's structure and surfaces the issues that quietly cost teams the most time — missing relations, missing rollups, duplicate status options, and properties that should be formulas — then shows how an external event would sync into Notion via a webhook trigger.

## How It Works
External trigger (manual audit request or webhook event) → Input (Notion database ID / event payload) → Processing (schema analysis: relations, rollups, select options, formulas) → Output (health score, issue table, recommended fixes, simulated synced page) → Verification (health score + sync confirmation log)

## Quick Start
1. `pip install -r requirements.txt`
2. `streamlit run app.py`
3. Enter a database name and click "Run Audit" to see a sample health score, detected issues, and recommended fixes. Then try "Simulate n8n Sync" to see a mock external event land as a Notion page.

## Configuration
- Optional `NOTION_API_KEY` env var for live workspace scans (falls back to sample data otherwise)

## Demo Limitations
- This is an MVP demo — it audits one database at a time and doesn't yet write changes back to Notion or auto-fix issues
- Production version would add: multi-database workspace-wide scans, one-click fixes (auto-create relations/rollups), scheduled re-audits with health-score trend tracking, and a real n8n workflow instead of the simulated sync
