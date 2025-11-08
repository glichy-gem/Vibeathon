"""
Reusable Jira Cloud helper utilities.

This module centralizes authentication and API calls so they can be reused by
CLI scripts, MCP tools, and Streamlit apps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


class JiraConfigError(RuntimeError):
    """Raised when required Jira configuration values are missing."""


@dataclass
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    default_project: Optional[str] = None
    story_points_field_id: Optional[str] = None


def load_config() -> JiraConfig:
    """Load Jira configuration from environment variables (with .env support)."""
    load_dotenv()

    base_url = os.getenv("JIRA_BASE_URL", "").strip()
    email = os.getenv("JIRA_EMAIL", "").strip()
    api_token = os.getenv("JIRA_API_TOKEN", "").strip()
    default_project = os.getenv("JIRA_DEFAULT_PROJECT", "").strip() or None
    story_points_field_id = os.getenv("JIRA_STORY_POINTS_FIELD_ID", "").strip() or None

    missing = {
        "JIRA_BASE_URL": base_url,
        "JIRA_EMAIL": email,
        "JIRA_API_TOKEN": api_token,
    }
    missing_keys = [key for key, value in missing.items() if not value]
    if missing_keys:
        raise JiraConfigError(
            "Missing required environment variables: "
            + ", ".join(missing_keys)
            + ". Please provide them via environment variables or a .env file."
        )

    return JiraConfig(
        base_url=base_url.rstrip("/"),
        email=email,
        api_token=api_token,
        default_project=default_project,
        story_points_field_id=story_points_field_id,
    )


class JiraClient:
    """Thin wrapper around Jira REST API v3."""

    def __init__(self, config: Optional[JiraConfig] = None) -> None:
        self.config = config or load_config()
        self._story_points_field_checked = False

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        url = f"{self.config.base_url}{path}"
        response = requests.request(
            method=method.upper(),
            url=url,
            auth=(self.config.email, self.config.api_token),
            params=params,
            json=json_body,
            timeout=15,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Jira API request failed ({response.status_code}): {response.text}"
            )
        return response

    def get_myself(self) -> Dict[str, Any]:
        return self._request("GET", "/rest/api/3/myself").json()

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"/rest/api/3/issue/{issue_key}",
            params={"expand": "renderedFields"},
        ).json()

    def search(
        self,
        jql: str,
        *,
        max_results: int = 50,
        start_at: int = 0,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
        }
        if fields:
            params["fields"] = fields
        return self._request(
            "GET",
            "/rest/api/3/search/jql",
            params=params,
        ).json()

    def list_tasks(
        self,
        project_key: str,
        *,
        status: Optional[str] = None,
        limit: int = 20,
        start_at: int = 0,
    ) -> Dict[str, Any]:
        jql_parts = [f'project = "{project_key}"']
        if status:
            jql_parts.append(f'status = "{status}"')
        jql = " AND ".join(jql_parts) + " ORDER BY created DESC"

        return self.search(
            jql,
            max_results=limit,
            start_at=start_at,
            fields="summary,status,assignee,duedate",
        )

    @staticmethod
    def _make_adf_paragraph(text: str) -> Dict[str, Any]:
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ],
                }
            ],
        }

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: Optional[str] = None,
        assignee_email: Optional[str] = None,
        story_points: Optional[float] = None,
        priority: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
        }
        if description:
            payload["fields"]["description"] = self._make_adf_paragraph(description)

        if assignee_email:
            account_id = self._find_account_id_by_query(assignee_email)
            if not account_id:
                raise RuntimeError(
                    f"Could not find a Jira user matching '{assignee_email}'."
                )
            payload["fields"]["assignee"] = {"accountId": account_id}

        if story_points is not None:
            field_id = self._ensure_story_points_field_id()
            payload["fields"][field_id] = story_points

        if priority:
            payload["fields"]["priority"] = {"name": priority}

        return self._request(
            "POST",
            "/rest/api/3/issue",
            json_body=payload,
        ).json()

    def assign_issue(
        self,
        issue_key: str,
        *,
        email: str,
    ) -> None:
        """
        Assign an issue to a user.

        Args:
            issue_key: Jira issue key (e.g., SCRUM-1).
            account_id: Atlassian accountId to assign. Required if email is not provided.
            email: Convenience parameter; if provided, the first matching user's accountId
                is used. Requires permissions to search users.
        """
        if not email:
            raise ValueError("An email must be provided to assign an issue.")

        target_account_id = self._find_account_id_by_query(email)
        if not target_account_id:
            raise RuntimeError(
                f"Could not find a Jira user matching '{email}'."
            )

        self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}/assignee",
            json_body={"accountId": target_account_id},
        )

    def set_story_points(self, issue_key: str, story_points: float) -> None:
        field_id = self._ensure_story_points_field_id()
        self._update_issue_fields(issue_key, {field_id: story_points})

    def set_priority(self, issue_key: str, priority: str) -> None:
        if not priority:
            raise ValueError("priority is required.")
        self._update_issue_fields(
            issue_key,
            {"priority": {"name": priority}},
        )

    def transition_issue(
        self,
        issue_key: str,
        target_status: str,
    ) -> Dict[str, Any]:
        """
        Move an issue to the desired workflow status.
        """
        if not issue_key or not issue_key.strip():
            raise ValueError("issue_key is required.")
        if not target_status or not target_status.strip():
            raise ValueError("target_status is required.")

        transitions_response = self._request(
            "GET",
            f"/rest/api/3/issue/{issue_key}/transitions",
        )
        transitions = transitions_response.json().get("transitions", [])

        chosen = None
        target_status_lower = target_status.strip().lower()
        for transition in transitions:
            status = transition.get("to") or {}
            name = status.get("name", "")
            if name.lower() == target_status_lower:
                chosen = transition
                break

        if not chosen:
            available = ", ".join(
                (t.get("to") or {}).get("name", "Unknown") for t in transitions
            )
            raise RuntimeError(
                f"Cannot transition {issue_key} to '{target_status}'. "
                f"Available: {available or 'none'}."
            )

        transition_id = chosen.get("id")
        response = self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/transitions",
            json_body={"transition": {"id": transition_id}},
        )
        return response.json() if response.text else {"status": "ok"}

    def _find_account_id_by_query(self, query: str) -> Optional[str]:
        """Return the first accountId that matches the given user search query."""
        response = self._request(
            "GET",
            "/rest/api/3/user/search",
            params={
                "query": query,
                "maxResults": 2,
            },
        )
        users: List[Dict[str, Any]] = response.json()
        if not users:
            return None
        return users[0].get("accountId")

    def _ensure_story_points_field_id(self) -> str:
        if self.config.story_points_field_id:
            return self.config.story_points_field_id

        if not self._story_points_field_checked:
            self._discover_story_points_field()
            self._story_points_field_checked = True

        if not self.config.story_points_field_id:
            raise RuntimeError(
                "Unable to determine Story Points field id. Set JIRA_STORY_POINTS_FIELD_ID."
            )
        return self.config.story_points_field_id

    def _discover_story_points_field(self) -> None:
        response = self._request("GET", "/rest/api/3/field")
        fields = response.json()
        candidates = [
            field
            for field in fields
            if isinstance(field, dict)
            and field.get("name")
            and "story point" in field["name"].lower()
        ]
        if candidates:
            field_id = candidates[0].get("id")
            if field_id:
                self.config.story_points_field_id = field_id

    def _update_issue_fields(self, issue_key: str, fields: Dict[str, Any]) -> None:
        self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}",
            json_body={"fields": fields},
        )

    def story_points_by_jql(
        self,
        jql: str,
        *,
        max_results: int = 1000,
    ) -> Dict[str, Any]:
        """
        Aggregate story points per assignee for issues matching the given JQL.
        """
        if not jql or not jql.strip():
            raise ValueError("JQL must be provided.")

        story_points_field = self._ensure_story_points_field_id()
        fields_param = f"summary,assignee,{story_points_field}"
        members: Dict[str, Dict[str, Any]] = {}
        unassigned: Dict[str, Any] = {
            "storyPoints": 0.0,
            "issueCount": 0,
            "unestimatedCount": 0,
            "issues": [],
        }
        total_issues = 0

        start_at = 0
        remaining = max_results
        while remaining > 0:
            batch_size = min(remaining, 100)
            response = self._request(
                "GET",
                "/rest/api/3/search/jql",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": batch_size,
                    "fields": fields_param,
                },
            )
            data = response.json()
            issues = data.get("issues", [])
            total_issues += len(issues)

            for issue in issues:
                fields = issue.get("fields") or {}
                assignee = fields.get("assignee")
                story_points = fields.get(story_points_field)
                has_estimate = isinstance(story_points, (int, float))
                story_points_value = float(story_points) if has_estimate else 0.0

                issue_entry = {
                    "key": issue.get("key"),
                    "summary": fields.get("summary"),
                    "storyPoints": story_points if has_estimate else None,
                }

                if assignee and assignee.get("accountId"):
                    account_id = assignee["accountId"]
                    member_entry = members.setdefault(
                        account_id,
                        {
                            "accountId": account_id,
                            "displayName": assignee.get("displayName"),
                            "emailAddress": assignee.get("emailAddress"),
                            "storyPoints": 0.0,
                            "issueCount": 0,
                            "unestimatedCount": 0,
                            "issues": [],
                        },
                    )
                    member_entry["issueCount"] += 1
                    if has_estimate:
                        member_entry["storyPoints"] += story_points_value
                    else:
                        member_entry["unestimatedCount"] += 1
                    member_entry["issues"].append(issue_entry)
                else:
                    unassigned["issueCount"] += 1
                    if has_estimate:
                        unassigned["storyPoints"] += story_points_value
                    else:
                        unassigned["unestimatedCount"] += 1
                    unassigned["issues"].append(issue_entry)

            if len(issues) < batch_size:
                break

            start_at += len(issues)
            remaining -= len(issues)

        members_list = list(members.values())
        members_list.sort(key=lambda m: m["storyPoints"], reverse=True)

        result: Dict[str, Any] = {
            "jql": jql,
            "totalIssues": total_issues,
            "members": members_list,
        }

        if unassigned["issueCount"] or unassigned["storyPoints"]:
            result["unassigned"] = unassigned

        return result

    def story_points_by_sprint(
        self,
        sprint: str,
        *,
        project_key: Optional[str] = None,
        max_results: int = 1000,
    ) -> Dict[str, Any]:
        """
        Aggregate story points per assignee for a specific sprint.

        Args:
            sprint: Sprint identifier. Accepts a sprint ID (numeric), a full JQL clause
                such as "sprint in openSprints()", or a sprint name.
            project_key: Optional project key to scope the query.
        """
        if not sprint or not sprint.strip():
            raise ValueError("Sprint identifier must be provided.")

        sprint = sprint.strip()
        sprint_lower = sprint.lower()

        if sprint_lower.startswith("sprint =") or sprint_lower.startswith("sprint in"):
            sprint_clause = sprint
        elif sprint.isdigit():
            sprint_clause = f"sprint = {sprint}"
        else:
            sanitized = sprint.replace('"', '\\"')
            sprint_clause = f'sprint = "{sanitized}"'

        if project_key:
            jql = f'{sprint_clause} AND project = "{project_key}"'
        else:
            jql = sprint_clause

        result = self.story_points_by_jql(jql, max_results=max_results)
        result["sprint"] = sprint
        if project_key:
            result["project"] = project_key
        return result


__all__ = [
    "JiraClient",
    "JiraConfig",
    "JiraConfigError",
    "load_config",
]

