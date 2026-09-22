"""
Notion Workspace Health Auditor -- core logic.

Connects to a Notion database via the official API and analyzes its schema
for common structural problems: missing relations, missing rollups,
duplicate select options, and orphaned/unused properties. Falls back to
realistic mock data when no API key is configured so the tool is fully
demoable without credentials.

Also includes a small n8n-style sync simulator that shows how an external
event (form submission, CRM update, etc.) would land in Notion as a page.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Any


def _mock_notion_audit(database_name: str) -> dict[str, Any]:
    """Return realistic, specific audit findings for a demo workspace.

    This models a typical mid-size ops workspace: a "Tasks" database and a
    "Projects" database that were built organically over time without a
    relation between them, plus the usual Notion drift (duplicate status
    options, unused text fields that should be formulas/rollups).
    """
    properties = [
        {"name": "Task Name", "type": "title", "used_in_views": 6},
        {"name": "Status", "type": "status", "used_in_views": 6},
        {"name": "Assignee", "type": "person", "used_in_views": 5},
        {"name": "Due Date", "type": "date", "used_in_views": 4},
        {"name": "Priority", "type": "select", "used_in_views": 3},
        {"name": "Project", "type": "text", "used_in_views": 2},
        {"name": "Hours Logged", "type": "number", "used_in_views": 1},
        {"name": "Client", "type": "text", "used_in_views": 2},
        {"name": "Notes", "type": "text", "used_in_views": 0},
    ]

    issues = [
        {
            "severity": "High",
            "category": "Missing Relation",
            "finding": (
                "\"Project\" on Tasks is a plain text field, not a relation "
                "to a Projects database. Project names are typed freely "
                "(\"Q3 Launch\", \"q3 launch\", \"Q3-Launch\" all appear), "
                "so nothing rolls up and project-level reporting is manual."
            ),
        },
        {
            "severity": "High",
            "category": "Missing Rollup",
            "finding": (
                "Without a Tasks <-> Projects relation, there is no rollup "
                "for \"Open Tasks\" or \"% Complete\" on the Projects side. "
                "Project status is currently updated by hand once a week."
            ),
        },
        {
            "severity": "Medium",
            "category": "Duplicate Select Options",
            "finding": (
                "Status has 11 options where 5 would cover it: \"Done\", "
                "\"Complete\", and \"Completed\" all exist as separate "
                "values, splitting completed-task counts across three "
                "buckets in every filtered view."
            ),
        },
        {
            "severity": "Medium",
            "category": "No Formula Used",
            "finding": (
                "\"Due Date\" has no companion formula for overdue "
                "detection. A days-until-due / overdue flag (Formulas 2.0 "
                "supports this natively now) would replace the manual "
                "red-highlighting Marco's team does today."
            ),
        },
        {
            "severity": "Low",
            "category": "Orphaned Property",
            "finding": (
                "\"Notes\" appears in 0 of 6 views and has content on only "
                "4% of rows. It is not deleted, just abandoned -- a good "
                "candidate to fold into a comment or remove."
            ),
        },
        {
            "severity": "Low",
            "category": "Unstructured Client Field",
            "finding": (
                "\"Client\" is free text on Tasks with 34 distinct spellings "
                "for what audit sampling suggests are ~12 real clients. "
                "Should be a relation to a Clients database, not text."
            ),
        },
    ]

    recommendations = [
        "Create a Projects database and convert \"Project\" from text to a two-way relation, then backfill existing rows by matching on the free-text value.",
        "Add a rollup on Projects for \"Open Task Count\" and \"% Complete\" (count of related Tasks where Status != Done, formatted as a percent).",
        "Consolidate Status options to 5 canonical values (Not Started, In Progress, Blocked, In Review, Done) and bulk-reassign the 3 duplicate \"done\" variants.",
        "Add an \"Overdue\" formula using Formulas 2.0 (if(and(Status != \"Done\", Due Date < now()), \"Overdue\", \"On Track\")) and surface it as a view filter.",
        "Create a Clients database, relate it to Tasks, and migrate the 34 free-text spellings down to ~12 canonical client records.",
        "Archive or merge the \"Notes\" property into page comments since it has near-zero usage across all views.",
    ]

    # Deterministic-looking but slightly varied score so repeated runs on
    # different database names don't look canned.
    base_score = 58
    penalty = len([i for i in issues if i["severity"] == "High"]) * 8
    penalty += len([i for i in issues if i["severity"] == "Medium"]) * 4
    penalty += len([i for i in issues if i["severity"] == "Low"]) * 2
    health_score = max(0, min(100, base_score - penalty + 34))

    return {
        "database_name": database_name,
        "source": "mock",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "properties": properties,
        "issues": issues,
        "recommendations": recommendations,
        "health_score": health_score,
    }


def real_notion_audit(database_id: str, api_key: str) -> dict[str, Any]:
    """Fetch a live Notion database schema and audit it.

    Requires the `notion-client` package (`pip install notion-client`).
    If `api_key` is falsy, falls back to `_mock_notion_audit` so the caller
    never has to branch on whether credentials are configured.
    """
    if not api_key:
        return _mock_notion_audit(database_id or "Client Operations DB")

    try:
        from notion_client import Client
    except ImportError as exc:
        raise RuntimeError(
            "notion-client is not installed. Run `pip install notion-client` "
            "to enable live audits."
        ) from exc

    client = Client(auth=api_key)
    db = client.databases.retrieve(database_id=database_id)

    props = db.get("properties", {})
    properties: list[dict[str, Any]] = []
    relation_targets: list[str] = []
    rollup_props: list[str] = []
    select_props: dict[str, list[str]] = {}

    for name, meta in props.items():
        prop_type = meta.get("type", "unknown")
        properties.append({"name": name, "type": prop_type, "used_in_views": None})

        if prop_type == "relation":
            relation_targets.append(meta.get("relation", {}).get("database_id", ""))
        if prop_type == "rollup":
            rollup_props.append(name)
        if prop_type in ("select", "multi_select", "status"):
            options = meta.get(prop_type, {}).get("options", [])
            select_props[name] = [o.get("name", "") for o in options]

    issues: list[dict[str, str]] = []

    if not relation_targets:
        issues.append({
            "severity": "High",
            "category": "Missing Relation",
            "finding": (
                "No relation properties found on this database. If related "
                "work lives in another database, link them so rollups and "
                "cross-database views become possible."
            ),
        })

    if relation_targets and not rollup_props:
        issues.append({
            "severity": "High",
            "category": "Missing Rollup",
            "finding": (
                "Relations exist but no rollup properties consume them. "
                "Add rollups to surface counts/sums from related records "
                "instead of checking manually."
            ),
        })

    for prop_name, options in select_props.items():
        lowered = [o.strip().lower() for o in options]
        if len(lowered) != len(set(lowered)):
            issues.append({
                "severity": "Medium",
                "category": "Duplicate Select Options",
                "finding": f"\"{prop_name}\" has case/whitespace duplicate options: {options}",
            })

    formula_props = [n for n, m in props.items() if m.get("type") == "formula"]
    date_props = [n for n, m in props.items() if m.get("type") == "date"]
    if date_props and not formula_props:
        issues.append({
            "severity": "Medium",
            "category": "No Formula Used",
            "finding": (
                f"Date propert{'y' if len(date_props) == 1 else 'ies'} "
                f"({', '.join(date_props)}) present but no formulas derive "
                "overdue/upcoming flags from them."
            ),
        })

    recommendations = [
        "Add relations between databases that reference each other by free text today.",
        "Back every relation with at least one rollup (count, sum, or % complete) to remove manual status tracking.",
        "Normalize select/status options to remove case and whitespace duplicates before they split your reporting.",
        "Add Formulas 2.0 overdue/at-risk flags on any date property used for deadlines.",
        "Review properties with near-zero view usage and archive or fold them into comments.",
        "Group free-text identifier fields (client names, project names) into their own related database.",
    ]

    penalty = sum(8 if i["severity"] == "High" else 4 if i["severity"] == "Medium" else 2 for i in issues)
    health_score = max(0, min(100, 96 - penalty))

    return {
        "database_name": db.get("title", [{}])[0].get("plain_text", database_id) if db.get("title") else database_id,
        "source": "live",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "properties": properties,
        "issues": issues,
        "recommendations": recommendations,
        "health_score": health_score,
    }


def simulate_n8n_sync(trigger_payload: dict[str, Any]) -> dict[str, Any]:
    """Simulate an n8n-style webhook trigger writing into Notion.

    Takes an external event payload (e.g. a form submission or CRM update)
    and returns the shape of the Notion page that would be created or
    updated, without requiring a live Notion connection.
    """
    page_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    properties_set = {
        "Name": {"title": trigger_payload.get("name", "Untitled")},
        "Email": {"email": trigger_payload.get("email", "")},
        "Status": {"status": trigger_payload.get("status", "New")},
        "Source": {"select": trigger_payload.get("source", "Webhook")},
        "Submitted At": {"date": timestamp},
    }

    return {
        "trigger": trigger_payload.get("source", "Webhook"),
        "action": "page_created",
        "notion_page_id": page_id,
        "notion_page_url": f"https://notion.so/{page_id.replace('-', '')}",
        "properties_set": properties_set,
        "synced_at": timestamp,
        "sync_latency_ms": random.randint(180, 420),
    }
