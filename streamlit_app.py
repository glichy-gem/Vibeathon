from __future__ import annotations

import json
from typing import Optional

import streamlit as st

from jira_client import JiraClient, JiraConfigError


@st.cache_resource(show_spinner=False)
def get_client() -> JiraClient:
    return JiraClient()


st.set_page_config(page_title="Alchemy Jira Assistant", page_icon="🧪", layout="wide")
st.title("Alchemy Jira Assistant")

try:
    client = get_client()
except JiraConfigError as exc:
    st.error(f"⚠️ Unable to load Jira credentials: {exc}")
    st.stop()

with st.sidebar:
    st.header("Settings")
    default_project: Optional[str] = client.config.default_project
    project_override = st.text_input(
        "Project key",
        value=default_project or "",
        help="Leave blank to use the default from JIRA_DEFAULT_PROJECT.",
    )
    active_project = project_override or default_project
    if not active_project:
        st.warning("Set a project key here or via JIRA_DEFAULT_PROJECT to enable project-based tools.")

st.subheader("Verify Credentials")
if st.button("Check Jira Connection", type="primary"):
    with st.spinner("Contacting Jira..."):
        data = client.get_myself()
    st.success(f"Authenticated as {data.get('displayName')} ({data.get('emailAddress')})")
    st.json(data)

st.markdown("---")

st.subheader("Fetch Issue")
col1, col2 = st.columns([2, 1])
with col1:
    issue_key = st.text_input("Issue key (e.g., SCRUM-1)", key="issue_key_input")
with col2:
    if st.button("Lookup Issue", type="secondary", key="issue_lookup"):
        if not issue_key:
            st.warning("Enter an issue key first.")
        else:
            with st.spinner(f"Fetching {issue_key}..."):
                issue = client.get_issue(issue_key)
            st.success(f"Loaded issue {issue_key}")
            st.json(issue)

st.markdown("---")

st.subheader("List Tasks")
col_a, col_b, col_c = st.columns(3)
with col_a:
    list_status = st.text_input("Filter by status", placeholder="In Progress")
with col_b:
    list_limit = st.number_input("Max tasks", min_value=1, max_value=100, value=10)
with col_c:
    list_start = st.number_input("Start at", min_value=0, value=0, step=10)

if st.button("Refresh Task List", type="secondary"):
    if not active_project:
        st.error("Project key required. Set it in the sidebar.")
    else:
        with st.spinner(f"Listing tasks in {active_project}..."):
            data = client.list_tasks(
                project_key=active_project,
                status=list_status or None,
                limit=int(list_limit),
                start_at=int(list_start),
            )
        issues = data.get("issues", [])
        if not issues:
            st.info("No tasks found.")
        else:
            for item in issues:
                fields = item.get("fields", {})
                summary = fields.get("summary", "<no summary>")
                status_name = fields.get("status", {}).get("name", "Unknown")
                assignee = fields.get("assignee", {}).get("displayName") if fields.get("assignee") else "Unassigned"
                due_date = fields.get("duedate") or "-"
                with st.expander(f"{item.get('key')} · {summary}"):
                    st.write(f"**Status:** {status_name}")
                    st.write(f"**Assignee:** {assignee}")
                    st.write(f"**Due:** {due_date}")
                    st.json(item)

st.markdown("---")

st.subheader("Create Issue")
with st.form("create_issue_form", clear_on_submit=True):
    summary = st.text_input("Summary", placeholder="Fix login redirect")
    issue_type = st.selectbox("Issue type", ["Task", "Bug", "Story"])
    description = st.text_area("Description", height=150)
    submitted = st.form_submit_button("Create Jira Issue", type="primary")

if submitted:
    if not active_project:
        st.error("Project key required. Set it in the sidebar before creating issues.")
    elif not summary.strip():
        st.warning("Summary is required.")
    else:
        with st.spinner(f"Creating issue in {active_project}..."):
            issue = client.create_issue(
                project_key=active_project,
                summary=summary.strip(),
                issue_type=issue_type,
                description=description.strip() or None,
            )
        st.success(f"Issue created: {issue.get('key')}")
        st.json(issue)

