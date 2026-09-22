"""
Notion Workspace Health Auditor -- Streamlit UI.

Audits a Notion database's structure (relations, rollups, formulas, select
options) and shows how an external event would sync into Notion via an
n8n-style webhook trigger.
"""

import os

import streamlit as st

from audit import real_notion_audit, simulate_n8n_sync

st.set_page_config(page_title="Notion Workspace Health Auditor", page_icon="🗂️", layout="centered")

st.title("Notion Workspace Health Auditor")
st.write(
    "Scans a Notion database's structure and flags the issues that quietly "
    "cost teams the most time: missing relations, missing rollups, duplicate "
    "status options, and properties that should be formulas."
)

st.divider()

st.subheader("1. Run a Workspace Audit")

database_name = st.text_input("Database name", value="Client Operations DB")
run_audit = st.button("Run Audit", type="primary")

if "audit_result" not in st.session_state:
    st.session_state.audit_result = None

if run_audit:
    api_key = os.environ.get("NOTION_API_KEY", "")
    with st.spinner("Analyzing workspace structure..."):
        st.session_state.audit_result = real_notion_audit(database_name, api_key)

result = st.session_state.audit_result

if result:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Health Score", f"{result['health_score']} / 100")
    with col2:
        high = len([i for i in result["issues"] if i["severity"] == "High"])
        med = len([i for i in result["issues"] if i["severity"] == "Medium"])
        low = len([i for i in result["issues"] if i["severity"] == "Low"])
        st.metric("Issues Found", f"{len(result['issues'])} total", f"{high} high / {med} med / {low} low")

    st.markdown("**Detected Issues**")
    st.dataframe(
        [
            {"Severity": i["severity"], "Category": i["category"], "Finding": i["finding"]}
            for i in result["issues"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**Recommended Fixes**")
    for rec in result["recommendations"]:
        st.markdown(f"- {rec}")

    st.caption("Sample audit -- connect your Notion API key for a live workspace scan.")

st.divider()

st.subheader("2. Simulate n8n Sync")
st.write(
    "Shows how an external event (a form submission, a CRM update, etc.) "
    "would flow through an n8n webhook and land as a page in Notion."
)

with st.form("sync_form"):
    sync_col1, sync_col2 = st.columns(2)
    with sync_col1:
        sync_name = st.text_input("Name", value="Jordan Blake")
        sync_email = st.text_input("Email", value="jordan@example.com")
    with sync_col2:
        sync_status = st.selectbox("Status", ["New", "In Progress", "Done"])
        sync_source = st.selectbox("Source", ["Typeform", "HubSpot", "Webhook", "Zapier"])

    sync_submit = st.form_submit_button("Simulate Sync")

if sync_submit:
    payload = {
        "name": sync_name,
        "email": sync_email,
        "status": sync_status,
        "source": sync_source,
    }
    sync_result = simulate_n8n_sync(payload)

    st.success(f"Page created in Notion via {sync_result['trigger']} trigger")
    st.json(sync_result)
