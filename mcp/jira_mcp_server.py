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
    story_points: Optional[float] = None,
    priority: Optional[str] = None,
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
        story_points=story_points,
        priority=priority,
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


@app.tool
def set_story_points(
    issue_key: str,
    story_points: float,
) -> Dict[str, Any]:
    """
    Update an issue's story points.
    """
    client = _get_client()
    client.set_story_points(issue_key, story_points)
    return {"status": "ok", "issue": issue_key, "story_points": story_points}


@app.tool
def set_priority(
    issue_key: str,
    priority: str,
) -> Dict[str, Any]:
    """
    Update an issue's priority by name.
    """
    client = _get_client()
    client.set_priority(issue_key, priority)
    return {"status": "ok", "issue": issue_key, "priority": priority}


@app.tool
def transition_issue(
    issue_key: str,
    target_status: str,
) -> Dict[str, Any]:
    """
    Move an issue through the workflow to the target status.
    """
    client = _get_client()
    return client.transition_issue(issue_key, target_status)


@app.tool
def story_points_summary(
    sprint: Optional[str] = None,
    project_key: Optional[str] = None,
    jql: Optional[str] = None,
    max_results: int = 500,
) -> Dict[str, Any]:
    """
    Aggregate story points per assignee for a sprint or custom JQL.
    """
    client = _get_client()
    if jql:
        return client.story_points_by_jql(jql, max_results=max_results)
    if sprint:
        scoped_project = project_key or client.config.default_project
        return client.story_points_by_sprint(
            sprint,
            project_key=scoped_project,
            max_results=max_results,
        )
    raise RuntimeError("Provide either sprint or jql parameter.")




if __name__ == "__main__":
    app.run()

