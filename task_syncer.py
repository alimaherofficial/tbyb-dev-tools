#!/usr/bin/env python3
"""
TBYB Task Syncer

Synchronizes tasks between Notion and Linear, identifying:
- Tasks in Notion but missing in Linear
- Issues in Linear not tracked in Notion  
- Items with mismatched priorities

Generates comprehensive sync reports for project management.

Author: TBYB Dev Team
Date: 2026-01-31
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict
from enum import Enum

import requests


# Configuration
NOTION_API_KEY = os.getenv("NOTION_KEY") or os.getenv("NOTION_API_KEY")
LINEAR_API_KEY = os.getenv("LINEAR_KEY") or os.getenv("LINEAR_API_KEY")
NOTION_API_VERSION = "2022-06-28"

# Database/Project IDs
NOTION_TASKS_DB_ID = "233fd206-a137-813e-8e79-eb2ed04dbd10"
LINEAR_TEAM_KEY = "TBYB"  # Try Before You Bike team


class Priority(Enum):
    """Standardized priority levels."""
    URGENT = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1
    NO_PRIORITY = 0
    
    @classmethod
    def from_string(cls, s: str) -> "Priority":
        s = s.lower()
        if s in ("urgent", "critical", "p0", "highest"):
            return cls.URGENT
        elif s in ("high", "p1"):
            return cls.HIGH
        elif s in ("medium", "p2", "normal"):
            return cls.MEDIUM
        elif s in ("low", "p3"):
            return cls.LOW
        return cls.NO_PRIORITY


@dataclass
class Task:
    """Unified task representation."""
    id: str
    title: str
    source: str  # 'notion' or 'linear'
    status: str
    priority: Priority
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    # Source-specific IDs for cross-referencing
    notion_id: Optional[str] = None
    linear_id: Optional[str] = None
    linear_identifier: Optional[str] = None  # TBYB-123


@dataclass
class SyncIssue:
    """Represents a synchronization issue."""
    issue_type: str
    severity: str  # 'error', 'warning', 'info'
    task_title: str
    notion_task: Optional[Task] = None
    linear_task: Optional[Task] = None
    message: str = ""
    recommendation: str = ""


class NotionClient:
    """Client for Notion API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json"
        }
    
    def query_database(self, database_id: str, filter_obj: Optional[dict] = None) -> list:
        """Query a Notion database."""
        url = f"{self.base_url}/databases/{database_id}/query"
        all_results = []
        
        payload = filter_obj or {}
        
        while True:
            try:
                response = requests.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                data = response.json()
                all_results.extend(data.get("results", []))
                
                # Handle pagination
                if data.get("has_more") and data.get("next_cursor"):
                    payload["start_cursor"] = data["next_cursor"]
                else:
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Error querying Notion: {e}")
                break
        
        return all_results


class LinearClient:
    """Client for Linear GraphQL API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = "https://api.linear.app/graphql"
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
    
    def query(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        try:
            response = requests.post(self.url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error querying Linear: {e}")
            return {}
    
    def get_team_issues(self, team_key: str) -> list:
        """Get all issues for a team."""
        query = """
        query($teamKey: String!) {
            team(key: $teamKey) {
                id
                issues {
                    nodes {
                        id
                        identifier
                        title
                        description
                        state {
                            name
                        }
                        priority
                        assignee {
                            name
                            email
                        }
                        dueDate
                        url
                        labels {
                            nodes {
                                name
                            }
                        }
                    }
                }
            }
        }
        """
        
        result = self.query(query, {"teamKey": team_key})
        team_data = result.get("data", {}).get("team", {})
        
        if not team_data:
            print(f"⚠️  Team '{team_key}' not found or no access")
            return []
        
        return team_data.get("issues", {}).get("nodes", [])


class TaskSyncer:
    """Main syncer that compares Notion and Linear tasks."""
    
    # Priority mappings
    NOTION_PRIORITY_MAP = {
        "Urgent": Priority.URGENT,
        "High": Priority.HIGH,
        "Medium": Priority.MEDIUM,
        "Low": Priority.LOW,
    }
    
    LINEAR_PRIORITY_MAP = {
        4: Priority.URGENT,    # Urgent
        3: Priority.HIGH,      # High
        2: Priority.MEDIUM,    # Medium
        1: Priority.LOW,       # Low
        0: Priority.NO_PRIORITY,
    }
    
    def __init__(self, notion_client: NotionClient, linear_client: LinearClient):
        self.notion = notion_client
        self.linear = linear_client
        self.notion_tasks: List[Task] = []
        self.linear_tasks: List[Task] = []
        self.sync_issues: List[SyncIssue] = []
    
    def fetch_notion_tasks(self) -> List[Task]:
        """Fetch and parse tasks from Notion."""
        print("📚 Fetching tasks from Notion...")
        
        results = self.notion.query_database(NOTION_TASKS_DB_ID)
        tasks = []
        
        for page in results:
            task = self._parse_notion_task(page)
            if task:
                tasks.append(task)
        
        self.notion_tasks = tasks
        print(f"✅ Found {len(tasks)} tasks in Notion")
        return tasks
    
    def _parse_notion_task(self, page: dict) -> Optional[Task]:
        """Parse a Notion page into a Task."""
        properties = page.get("properties", {})
        
        # Extract title
        title = self._extract_text(properties.get("Name", properties.get("title", {})))
        if not title:
            return None
        
        # Extract status
        status_prop = properties.get("Status", {})
        status = "Unknown"
        if "status" in status_prop:
            status = status_prop["status"].get("name", "Unknown")
        elif "select" in status_prop:
            status = status_prop["select"].get("name", "Unknown")
        
        # Extract priority
        priority = Priority.NO_PRIORITY
        priority_prop = properties.get("Priority", {})
        if "select" in priority_prop and priority_prop["select"]:
            priority_name = priority_prop["select"].get("name", "")
            priority = self.NOTION_PRIORITY_MAP.get(priority_name, Priority.NO_PRIORITY)
        
        # Extract assignee
        assignee = None
        assignee_prop = properties.get("Assignee", properties.get("Assigned to", {}))
        if "people" in assignee_prop and assignee_prop["people"]:
            assignee = assignee_prop["people"][0].get("name", "Unknown")
        
        # Extract due date
        due_date = None
        due_prop = properties.get("Due date", properties.get("Due", {}))
        if "date" in due_prop and due_prop["date"]:
            due_date = due_prop["date"].get("start")
        
        # Extract tags
        tags = []
        tags_prop = properties.get("Tags", properties.get("tags", {}))
        if "multi_select" in tags_prop:
            tags = [t["name"] for t in tags_prop["multi_select"]]
        
        # Look for Linear reference in title or description
        linear_id = self._extract_linear_reference(title, properties)
        
        return Task(
            id=page["id"],
            title=title,
            source="notion",
            status=status,
            priority=priority,
            assignee=assignee,
            due_date=due_date,
            url=page.get("url"),
            description=self._extract_text(properties.get("Description", {})),
            tags=tags,
            notion_id=page["id"],
            linear_id=linear_id
        )
    
    def _extract_text(self, property_obj: dict) -> str:
        """Extract text from Notion property."""
        if "title" in property_obj:
            texts = [t["text"]["content"] for t in property_obj["title"]]
            return " ".join(texts)
        elif "rich_text" in property_obj:
            texts = [t["text"]["content"] for t in property_obj["rich_text"]]
            return " ".join(texts)
        return ""
    
    def _extract_linear_reference(self, title: str, properties: dict) -> Optional[str]:
        """Try to find Linear issue reference in task."""
        import re
        
        # Look for pattern like [TBYB-123] or TBYB-123 in title
        match = re.search(r'\[?(TBYB-\d+)\]?', title)
        if match:
            return match.group(1)
        
        # Check description
        desc = self._extract_text(properties.get("Description", {}))
        match = re.search(r'\[?(TBYB-\d+)\]?', desc)
        if match:
            return match.group(1)
        
        return None
    
    def fetch_linear_issues(self) -> List[Task]:
        """Fetch and parse issues from Linear."""
        print("📊 Fetching issues from Linear...")
        
        issues = self.linear.get_team_issues(LINEAR_TEAM_KEY)
        tasks = []
        
        for issue in issues:
            task = self._parse_linear_issue(issue)
            if task:
                tasks.append(task)
        
        self.linear_tasks = tasks
        print(f"✅ Found {len(tasks)} issues in Linear")
        return tasks
    
    def _parse_linear_issue(self, issue: dict) -> Optional[Task]:
        """Parse a Linear issue into a Task."""
        if not issue.get("title"):
            return None
        
        priority = self.LINEAR_PRIORITY_MAP.get(issue.get("priority"), Priority.NO_PRIORITY)
        
        assignee = None
        if issue.get("assignee"):
            assignee = issue["assignee"].get("name")
        
        labels = []
        if issue.get("labels"):
            labels = [l["name"] for l in issue["labels"].get("nodes", [])]
        
        return Task(
            id=issue["id"],
            title=issue["title"],
            source="linear",
            status=issue.get("state", {}).get("name", "Unknown"),
            priority=priority,
            assignee=assignee,
            due_date=issue.get("dueDate"),
            url=issue.get("url"),
            description=issue.get("description", ""),
            tags=labels,
            linear_id=issue["id"],
            linear_identifier=issue.get("identifier")
        )
    
    def sync(self) -> List[SyncIssue]:
        """Perform full sync and identify issues."""
        print("\n🔄 Starting sync analysis...")
        
        self.sync_issues = []
        
        # Build lookup maps
        notion_by_title = {t.title.lower().strip(): t for t in self.notion_tasks}
        linear_by_title = {t.title.lower().strip(): t for t in self.linear_tasks}
        linear_by_identifier = {t.linear_identifier: t for t in self.linear_tasks if t.linear_identifier}
        
        # 1. Find tasks in Notion but missing in Linear
        for notion_task in self.notion_tasks:
            matched = False
            
            # Check by title match
            if notion_task.title.lower().strip() in linear_by_title:
                matched = True
            
            # Check by Linear reference
            if notion_task.linear_id and notion_task.linear_id in linear_by_identifier:
                matched = True
            
            if not matched:
                self.sync_issues.append(SyncIssue(
                    issue_type="missing_in_linear",
                    severity="warning",
                    task_title=notion_task.title,
                    notion_task=notion_task,
                    linear_task=None,
                    message=f"Task exists in Notion but not found in Linear",
                    recommendation=f"Create issue in Linear or add [TBYB-XXX] reference to Notion task"
                ))
        
        # 2. Find issues in Linear not tracked in Notion
        for linear_task in self.linear_tasks:
            matched = False
            
            # Check by title match
            if linear_task.title.lower().strip() in notion_by_title:
                matched = True
                # Link them
                notion_task = notion_by_title[linear_task.title.lower().strip()]
                notion_task.linear_id = linear_task.linear_identifier
                linear_task.notion_id = notion_task.notion_id
            
            if not matched:
                self.sync_issues.append(SyncIssue(
                    issue_type="missing_in_notion",
                    severity="warning",
                    task_title=linear_task.title,
                    notion_task=None,
                    linear_task=linear_task,
                    message=f"Issue exists in Linear but not tracked in Notion",
                    recommendation=f"Add to Notion database for centralized tracking"
                ))
        
        # 3. Find mismatched priorities
        for notion_task in self.notion_tasks:
            for linear_task in self.linear_tasks:
                # Match by title or Linear ID
                titles_match = notion_task.title.lower().strip() == linear_task.title.lower().strip()
                id_match = notion_task.linear_id == linear_task.linear_identifier
                
                if titles_match or id_match:
                    if notion_task.priority != linear_task.priority:
                        self.sync_issues.append(SyncIssue(
                            issue_type="priority_mismatch",
                            severity="error",
                            task_title=notion_task.title,
                            notion_task=notion_task,
                            linear_task=linear_task,
                            message=f"Priority mismatch: Notion={notion_task.priority.name}, Linear={linear_task.priority.name}",
                            recommendation=f"Update priority in one system to match"
                        ))
                    break
        
        print(f"🔍 Found {len(self.sync_issues)} sync issues")
        return self.sync_issues
    
    def generate_report(self, output_path: Optional[Path] = None) -> str:
        """Generate a comprehensive sync report."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        lines = [
            "=" * 80,
            "TBYB TASK SYNC REPORT",
            "=" * 80,
            f"Generated: {timestamp}",
            "",
            "📊 SUMMARY",
            "-" * 80,
            f"Notion Tasks:    {len(self.notion_tasks)}",
            f"Linear Issues:   {len(self.linear_tasks)}",
            f"Sync Issues:     {len(self.sync_issues)}",
            "",
        ]
        
        # Categorize issues
        missing_in_linear = [i for i in self.sync_issues if i.issue_type == "missing_in_linear"]
        missing_in_notion = [i for i in self.sync_issues if i.issue_type == "missing_in_notion"]
        priority_mismatches = [i for i in self.sync_issues if i.issue_type == "priority_mismatch"]
        
        # Missing in Linear
        if missing_in_linear:
            lines.extend([
                "⚠️  TASKS IN NOTION BUT MISSING IN LINEAR",
                "-" * 80,
            ])
            for issue in missing_in_linear[:10]:  # Limit to 10
                lines.extend([
                    f"• {issue.task_title}",
                    f"  Status: {issue.notion_task.status}",
                    f"  URL: {issue.notion_task.url}",
                    f"  → {issue.recommendation}",
                    ""
                ])
            if len(missing_in_linear) > 10:
                lines.append(f"... and {len(missing_in_linear) - 10} more")
            lines.append("")
        
        # Missing in Notion
        if missing_in_notion:
            lines.extend([
                "⚠️  ISSUES IN LINEAR NOT TRACKED IN NOTION",
                "-" * 80,
            ])
            for issue in missing_in_notion[:10]:
                lines.extend([
                    f"• [{issue.linear_task.linear_identifier}] {issue.task_title}",
                    f"  Status: {issue.linear_task.status}",
                    f"  URL: {issue.linear_task.url}",
                    f"  → {issue.recommendation}",
                    ""
                ])
            if len(missing_in_notion) > 10:
                lines.append(f"... and {len(missing_in_notion) - 10} more")
            lines.append("")
        
        # Priority mismatches
        if priority_mismatches:
            lines.extend([
                "❌ PRIORITY MISMATCHES",
                "-" * 80,
            ])
            for issue in priority_mismatches:
                lines.extend([
                    f"• {issue.task_title}",
                    f"  Notion: {issue.notion_task.priority.name} | Linear: {issue.linear_task.priority.name}",
                    f"  → {issue.recommendation}",
                    ""
                ])
            lines.append("")
        
        # Stats
        lines.extend([
            "📈 STATISTICS",
            "-" * 80,
            f"Missing in Linear:     {len(missing_in_linear)}",
            f"Missing in Notion:     {len(missing_in_notion)}",
            f"Priority Mismatches:   {len(priority_mismatches)}",
            "",
        ])
        
        # Action items
        lines.extend([
            "✅ RECOMMENDED ACTIONS",
            "-" * 80,
        ])
        
        if missing_in_linear:
            lines.append(f"1. Create {len(missing_in_linear)} issues in Linear from Notion tasks")
        if missing_in_notion:
            lines.append(f"2. Add {len(missing_in_notion)} Linear issues to Notion database")
        if priority_mismatches:
            lines.append(f"3. Fix {len(priority_mismatches)} priority mismatches")
        if not self.sync_issues:
            lines.append("🎉 No issues found! Your task tracking is perfectly synced.")
        
        lines.extend([
            "",
            "=" * 80,
            "END OF REPORT",
            "=" * 80,
        ])
        
        report = "\n".join(lines)
        
        # Save to file
        if output_path:
            output_path.write_text(report, encoding="utf-8")
            print(f"📄 Report saved to: {output_path}")
        
        return report
    
    def export_json(self, output_path: Path) -> None:
        """Export full sync data as JSON."""
        data = {
            "generated_at": datetime.now().isoformat(),
            "notion_tasks": [asdict(t) for t in self.notion_tasks],
            "linear_tasks": [asdict(t) for t in self.linear_tasks],
            "sync_issues": [
                {
                    **asdict(issue),
                    "notion_task": asdict(issue.notion_task) if issue.notion_task else None,
                    "linear_task": asdict(issue.linear_task) if issue.linear_task else None,
                }
                for issue in self.sync_issues
            ]
        }
        
        # Convert Priority enums to strings for JSON
        def convert_priority(obj):
            if isinstance(obj, Priority):
                return obj.name
            return obj
        
        output_path.write_text(
            json.dumps(data, indent=2, default=convert_priority),
            encoding="utf-8"
        )
        print(f"📄 JSON export saved to: {output_path}")
    
    def run(self, output_dir: Optional[Path] = None) -> None:
        """Run the full sync workflow."""
        # Fetch data
        self.fetch_notion_tasks()
        self.fetch_linear_issues()
        
        if not self.notion_tasks and not self.linear_tasks:
            print("⚠️  No tasks found in either system. Check API credentials.")
            return
        
        # Perform sync
        self.sync()
        
        # Generate reports
        if output_dir is None:
            output_dir = Path.home() / "clawd" / "sync_reports"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Text report
        report_path = output_dir / f"sync_report_{timestamp}.txt"
        report = self.generate_report(report_path)
        print("\n" + report)
        
        # JSON export
        json_path = output_dir / f"sync_data_{timestamp}.json"
        self.export_json(json_path)
        
        print(f"\n🎉 Sync complete! Reports saved to: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="TBYB Task Syncer - Sync tasks between Notion and Linear"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory for reports"
    )
    parser.add_argument(
        "--notion-key",
        type=str,
        default=None,
        help="Notion API key (or set NOTION_KEY env var)"
    )
    parser.add_argument(
        "--linear-key",
        type=str,
        default=None,
        help="Linear API key (or set LINEAR_KEY env var)"
    )
    
    args = parser.parse_args()
    
    # Get API keys
    notion_key = args.notion_key or NOTION_API_KEY
    linear_key = args.linear_key or LINEAR_API_KEY
    
    if not notion_key:
        print("❌ Error: Notion API key required. Set NOTION_KEY or use --notion-key")
        sys.exit(1)
    
    if not linear_key:
        print("❌ Error: Linear API key required. Set LINEAR_KEY or use --linear-key")
        sys.exit(1)
    
    # Run syncer
    notion_client = NotionClient(notion_key)
    linear_client = LinearClient(linear_key)
    syncer = TaskSyncer(notion_client, linear_client)
    
    output_dir = Path(args.output) if args.output else None
    
    try:
        syncer.run(output_dir)
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
