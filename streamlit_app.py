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

active_project: Optional[str] = client.config.default_project
if not active_project:
    st.error("Set JIRA_DEFAULT_PROJECT in your environment to use this app.")
    st.stop()

st.caption(f"Active project: `{active_project}`")

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

st.subheader("Assign Issue")
with st.form("assign_issue_form", clear_on_submit=True):
    assign_issue_key = st.text_input("Issue key", placeholder="SCRUM-1")
    assign_email = st.text_input("Assignee email")
    assign_submit = st.form_submit_button("Assign")

if assign_submit:
    if not assign_issue_key.strip():
        st.warning("Issue key is required.")
    elif not assign_email.strip():
        st.warning("Provide the assignee's email.")
    else:
        with st.spinner(f"Assigning {assign_issue_key}..."):
            client.assign_issue(
                assign_issue_key.strip(),
                email=assign_email.strip(),
            )
        st.success(f"Issue {assign_issue_key.strip()} assigned successfully.")

st.markdown("---")

st.subheader("Move Issue Between Statuses")
with st.form("transition_form", clear_on_submit=True):
    transition_issue_key = st.text_input("Issue key", placeholder="SCRUM-1")
    transition_status = st.selectbox(
        "Target status",
        ["To Do", "In Progress", "In Review", "Done"],
    )
    transition_submit = st.form_submit_button("Move Issue")

if transition_submit:
    if not transition_issue_key.strip():
        st.warning("Issue key is required.")
    else:
        try:
            with st.spinner(f"Moving {transition_issue_key} to {transition_status}..."):
                client.transition_issue(
                    transition_issue_key.strip(),
                    transition_status,
                )
            st.success(f"Issue {transition_issue_key.strip()} moved to {transition_status}.")
        except Exception as exc:
            st.error(f"Failed to move issue: {exc}")

st.markdown("---")

st.subheader("Sprint Story Points")
with st.form("sprint_story_points_form", clear_on_submit=True):
    sprint_identifier = st.text_input("Sprint (name or ID)", placeholder="Sprint 1 or 45")
    custom_jql = st.text_input(
        "Custom JQL (optional)",
        placeholder='sprint in openSprints() AND project = "SCRUM"',
    )
    limit_to_project = st.checkbox("Limit to configured project", value=True)
    max_story_results = st.number_input(
        "Max issues to inspect",
        min_value=10,
        max_value=1000,
        value=200,
        step=10,
    )
    sprint_story_submit = st.form_submit_button("Calculate Story Points")

if sprint_story_submit:
    try:
        with st.spinner("Aggregating story points..."):
            if custom_jql.strip():
                result = client.story_points_by_jql(
                    custom_jql.strip(),
                    max_results=int(max_story_results),
                )
            elif sprint_identifier.strip():
                result = client.story_points_by_sprint(
                    sprint_identifier.strip(),
                    project_key=active_project if limit_to_project else None,
                    max_results=int(max_story_results),
                )
            else:
                st.warning("Provide either a sprint identifier or a custom JQL query.")
                result = None
        if result:
            members = result.get("members", [])
            if not members:
                st.info("No results found for the provided criteria.")
            else:
                st.write(f"JQL: `{result.get('jql')}`")
                st.write(f"Total issues scanned: {result.get('totalIssues', 0)}")
                for member in members:
                    header = f"{member.get('displayName')} ({round(member.get('storyPoints', 0), 2)} pts)"
                    with st.expander(header):
                        st.write(f"**Email:** {member.get('emailAddress', 'N/A')}")
                        st.write(f"**Estimated Issues:** {member.get('issueCount', 0)}")
                        unestimated = member.get("unestimatedCount", 0)
                        if unestimated:
                            st.write(f"**Unestimated Issues:** {unestimated}")
                        for issue in member.get("issues", []):
                            st.write(
                                f"- {issue.get('key')}: {issue.get('summary')} "
                                f"(Story Points: {issue.get('storyPoints', '—')})"
                            )
                unassigned_info = result.get("unassigned")
                if unassigned_info:
                    with st.expander("Unassigned issues"):
                        st.write(f"Story Points: {round(unassigned_info.get('storyPoints', 0), 2)}")
                        st.write(f"Issue count: {unassigned_info.get('issueCount', 0)}")
                        if unassigned_info.get("unestimatedCount"):
                            st.write(f"Unestimated Issues: {unassigned_info.get('unestimatedCount', 0)}")
                        for issue in unassigned_info.get("issues", []):
                            st.write(
                                f"- {issue.get('key')}: {issue.get('summary')} "
                                f"(Story Points: {issue.get('storyPoints', '—')})"
                            )
    except Exception as exc:
        st.error(f"Failed to aggregate story points: {exc}")

st.markdown("---")

st.subheader("Update Priority")
with st.form("priority_form", clear_on_submit=True):
    pr_issue_key = st.text_input("Issue key for priority", placeholder="SCRUM-1")
    pr_value = st.selectbox(
        "Priority",
        ["Highest", "High", "Medium", "Low", "Lowest"],
    )
    pr_submit = st.form_submit_button("Update Priority")

if pr_submit:
    if not pr_issue_key.strip():
        st.warning("Issue key is required.")
    else:
        with st.spinner(f"Updating priority for {pr_issue_key}..."):
            client.set_priority(pr_issue_key.strip(), pr_value)
        st.success(f"Updated priority for {pr_issue_key.strip()} to {pr_value}.")

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

st.subheader("Create Issue")
with st.form("create_issue_form", clear_on_submit=True):
    summary = st.text_input("Summary", placeholder="Fix login redirect")
    issue_type = st.selectbox("Issue type", ["Task", "Bug", "Story"])
    description = st.text_area("Description", height=150)
    assignee_email = st.text_input("Assignee email (optional)")
    story_points = st.number_input("Story points (optional)", min_value=0.0, step=0.5)
    priority = st.selectbox(
        "Priority (optional)",
        ["", "Highest", "High", "Medium", "Low", "Lowest"],
        index=0,
    )
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
                assignee_email=assignee_email.strip() or None,
                story_points=story_points or None,
                priority=priority or None,
            )
        st.success(f"Issue created: {issue.get('key')}")
        st.json(issue)

