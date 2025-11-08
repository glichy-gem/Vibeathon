from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from jira_client import JiraClient, JiraConfigError


def build_parser(default_project: Optional[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI utilities to exercise Jira Cloud REST API for the Alchemy setup.",
    )
    parser.add_argument(
        "--project",
        default=default_project or None,
        help="Default project key to use (falls back to JIRA_DEFAULT_PROJECT).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("verify", help="Verify credentials by hitting /myself.")

    get_parser = subparsers.add_parser("get", help="Fetch a Jira issue by key.")
    get_parser.add_argument("issue_key", help="Issue key, e.g., ALCH-1.")

    search_parser = subparsers.add_parser("search", help="Search issues using a JQL query.")
    search_parser.add_argument("jql", help='JQL query, e.g., "project = ALCH ORDER BY created DESC".')
    search_parser.add_argument("--max-results", type=int, default=25, help="Max issues to return.")
    search_parser.add_argument("--start-at", type=int, default=0, help="Starting index for pagination.")
    search_parser.add_argument(
        "--fields",
        nargs="+",
        help="Specific fields to retrieve (space-separated). Example: --fields summary status assignee",
    )

    list_parser = subparsers.add_parser("list", help="List recent tasks in the project.")
    list_parser.add_argument(
        "--status",
        help="Filter by status name (e.g., 'In Progress').",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of tasks to list (default: 20).",
    )
    list_parser.add_argument(
        "--start-at",
        type=int,
        default=0,
        help="Starting index for pagination (default: 0).",
    )

    create_parser = subparsers.add_parser("create", help="Create a new issue in the Alchemy project.")
    create_parser.add_argument("--summary", required=True, help="Issue summary/title.")
    create_parser.add_argument("--type", default="Task", help='Issue type (default: "Task").')
    create_parser.add_argument("--description", help="Optional issue description.")
    create_parser.add_argument(
        "--assignee-email",
        help="Email of the user to assign the issue to (will be looked up).",
    )
    create_parser.add_argument(
        "--story-points",
        type=float,
        help="Story points for the new issue.",
    )
    create_parser.add_argument(
        "--priority",
        help="Priority name for the new issue (e.g., High, Medium, Low).",
    )

    assign_parser = subparsers.add_parser("assign", help="Assign an issue to a user.")
    assign_parser.add_argument("issue_key", help="Issue key to assign, e.g., SCRUM-1.")
    assign_parser.add_argument("--email", required=True, help="Email address of the assignee.")

    estimate_parser = subparsers.add_parser("set-story-points", help="Update story points for an issue.")
    estimate_parser.add_argument("issue_key", help="Issue key, e.g., SCRUM-1.")
    estimate_parser.add_argument("story_points", type=float, help="New story points value.")

    priority_parser = subparsers.add_parser("set-priority", help="Update priority for an issue.")
    priority_parser.add_argument("issue_key", help="Issue key, e.g., SCRUM-1.")
    priority_parser.add_argument("priority", help="Priority name, e.g., High.")

    transition_parser = subparsers.add_parser("transition", help="Move an issue to a new status.")
    transition_parser.add_argument("issue_key", help="Issue key, e.g., SCRUM-1.")
    transition_parser.add_argument("status", help="Target status name, e.g., 'In Progress'.")

    story_points_parser = subparsers.add_parser("story-points", help="Aggregate story points for a sprint or JQL.")
    story_points_parser.add_argument(
        "--sprint",
        help='Sprint identifier or clause, e.g., "Sprint 1" or 45.',
    )
    story_points_parser.add_argument(
        "--jql",
        help="Custom JQL to aggregate story points (overrides --sprint).",
    )
    story_points_parser.add_argument(
        "--project",
        help="Project key to scope the sprint aggregation (defaults to configured project).",
    )
    story_points_parser.add_argument(
        "--max-results",
        type=int,
        default=500,
        help="Maximum issues to inspect (default: 500).",
    )

    return parser


def main() -> None:
    try:
        client = JiraClient()
    except JiraConfigError as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)

    parser = build_parser(client.config.default_project)
    args = parser.parse_args()

    try:
        if args.command == "verify":
            data = client.get_myself()
            print(json.dumps(data, indent=2, sort_keys=True))
        elif args.command == "get":
            issue = client.get_issue(args.issue_key)
            print(json.dumps(issue, indent=2, sort_keys=True))
        elif args.command == "search":
            fields = ",".join(args.fields) if args.fields else None
            data = client.search(
                args.jql,
                max_results=args.max_results,
                start_at=args.start_at,
                fields=fields,
            )
            print(json.dumps(data, indent=2, sort_keys=True))
        elif args.command == "list":
            project_key = args.project or client.config.default_project
            if not project_key:
                raise ValueError(
                    "Project key is required. Pass --project or set JIRA_DEFAULT_PROJECT in your environment."
                )
            data = client.list_tasks(
                project_key=project_key,
                status=args.status,
                limit=args.limit,
                start_at=args.start_at,
            )
            issues = data.get("issues", [])
            if not issues:
                print("No tasks found.")
            else:
                for issue in issues:
                    fields = issue.get("fields", {})
                    status_name = fields.get("status", {}).get("name", "<unknown>")
                    summary = fields.get("summary", "<no summary>")
                    assignee = fields.get("assignee", {}).get("displayName") if fields.get("assignee") else "Unassigned"
                    due = fields.get("duedate") or "-"
                    print(f"{issue.get('key')}: {summary} | Status: {status_name} | Assignee: {assignee} | Due: {due}")
        elif args.command == "create":
            project_key = args.project or client.config.default_project
            if not project_key:
                raise ValueError(
                    "Project key is required. Pass --project or set JIRA_DEFAULT_PROJECT in your environment."
                )
            issue = client.create_issue(
                project_key=project_key,
                summary=args.summary,
                issue_type=args.type,
                description=args.description,
                assignee_email=args.assignee_email,
                story_points=args.story_points,
                priority=args.priority,
            )
            print("Issue created successfully!")
            print(json.dumps(issue, indent=2, sort_keys=True))
        elif args.command == "assign":
            client.assign_issue(
                args.issue_key,
                email=args.email,
            )
            print(f"Issue {args.issue_key} assigned successfully.")
        elif args.command == "set-story-points":
            client.set_story_points(args.issue_key, args.story_points)
            print(f"Issue {args.issue_key} story points updated to {args.story_points}.")
        elif args.command == "set-priority":
            client.set_priority(args.issue_key, args.priority)
            print(f"Issue {args.issue_key} priority updated to {args.priority}.")
        elif args.command == "transition":
            client.transition_issue(args.issue_key, args.status)
            print(f"Issue {args.issue_key} moved to '{args.status}'.")
        elif args.command == "story-points":
            max_results = args.max_results
            if args.jql:
                result = client.story_points_by_jql(args.jql, max_results=max_results)
            elif args.sprint:
                project_scope = args.project or client.config.default_project
                result = client.story_points_by_sprint(
                    args.sprint,
                    project_key=project_scope,
                    max_results=max_results,
                )
            else:
                raise ValueError("Provide --sprint or --jql to aggregate story points.")
            print(json.dumps(result, indent=2, sort_keys=True))
        else:  # pragma: no cover
            parser.print_help()
            sys.exit(2)
    except Exception as exc:
        print(f"Jira API call failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

