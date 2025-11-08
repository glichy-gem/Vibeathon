"""
Reusable Jira Cloud helper utilities.

This module centralizes authentication and API calls so they can be reused by
CLI scripts, MCP tools, and Streamlit apps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

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


def load_config() -> JiraConfig:
    """Load Jira configuration from environment variables (with .env support)."""
    load_dotenv()

    base_url = os.getenv("JIRA_BASE_URL", "").strip()
    email = os.getenv("JIRA_EMAIL", "").strip()
    api_token = os.getenv("JIRA_API_TOKEN", "").strip()
    default_project = os.getenv("JIRA_DEFAULT_PROJECT", "").strip() or None

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
    )


class JiraClient:
    """Thin wrapper around Jira REST API v3."""

    def __init__(self, config: Optional[JiraConfig] = None) -> None:
        self.config = config or load_config()

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

        return self._request(
            "POST",
            "/rest/api/3/issue",
            json_body=payload,
        ).json()


__all__ = [
    "JiraClient",
    "JiraConfig",
    "JiraConfigError",
    "load_config",
]

