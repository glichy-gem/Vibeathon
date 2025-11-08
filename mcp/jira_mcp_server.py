from __future__ import annotations

import json
from typing import Any, Dict, Optional

import os
import sys

from fastmcp import FastMCP

CURRENT_DIR = os.path.dirname(__file__)
PARENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from jira_client import JiraClient, JiraConfigError


app = FastMCP("jira-tools")


def _get_client() -> JiraClient:
    try:
        return JiraClient()
    except JiraConfigError as exc:
        raise RuntimeError(f"Jira configuration error: {exc}") from exc


@app.tool
def verify_credentials() -> Dict[str, Any]:
    """
    Verify Jira credentials by calling the `/myself` endpoint.

    Returns the authenticated user's profile details.
    """
    client = _get_client()
    return client.get_myself()


@app.tool
def get_issue(issue_key: str) -> Dict[str, Any]:
    """
    Fetch a Jira issue by key (e.g., SCRUM-1).
    """
    client = _get_client()
    return client.get_issue(issue_key)


@app.tool
def search_issues(
    jql: str,
    max_results: int = 50,
    start_at: int = 0,
    fields: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search Jira issues using a JQL query.

    Args:
        jql: JQL search string.
        max_results: Max issues to return (default 50).
        start_at: Pagination offset.
        fields: Optional comma-separated list of fields to include.
    """
    client = _get_client()
    return client.search(
        jql,
        max_results=max_results,
        start_at=start_at,
        fields=fields,
    )


@app.tool
def list_tasks(
    project_key: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    start_at: int = 0,
) -> Dict[str, Any]:
    """
    Convenience wrapper to list tasks in a project (defaults to configured project).
    """
    client = _get_client()
    project = project_key or client.config.default_project
    if not project:
        raise RuntimeError(
            "Project key is required. Pass project_key or set JIRA_DEFAULT_PROJECT."
        )
    return client.list_tasks(
        project_key=project,
        status=status,
        limit=limit,
        start_at=start_at,
    )


@app.tool
def create_issue(
    project_key: Optional[str],
    summary: str,
    issue_type: str = "Task",
    description: Optional[str] = None,
    assignee_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a Jira issue in the specified project.
    """
    client = _get_client()
    project = project_key or client.config.default_project
    if not project:
        raise RuntimeError(
            "Project key is required. Pass project_key or set JIRA_DEFAULT_PROJECT."
        )
    return client.create_issue(
        project_key=project,
        summary=summary,
        issue_type=issue_type,
        description=description,
        assignee_email=assignee_email,
    )


@app.tool
def assign_issue(
    issue_key: str,
    email: str,
) -> Dict[str, Any]:
    """
    Assign a Jira issue to a user. Provide either account_id or email.
    """
    client = _get_client()
    client.assign_issue(
        issue_key,
        email=email,
    )
    return {"status": "ok", "issue": issue_key, "assigned_to": email}


if __name__ == "__main__":
    app.run()

