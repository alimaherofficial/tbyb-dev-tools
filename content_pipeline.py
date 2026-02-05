#!/usr/bin/env python3
"""
TBYB Content Pipeline Generator

Fetches content ideas from Notion and generates structured script outlines
ready for recording. Saves output to dated folders for easy organization.

Author: TBYB Dev Team
Date: 2026-01-31
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

import requests


# Configuration
NOTION_API_KEY = os.getenv("NOTION_KEY") or os.getenv("NOTION_API_KEY")
NOTION_API_VERSION = "2022-06-28"
CONTENT_DATABASE_ID = "233fd206-a137-813e-8e79-eb2ed04dbd10"  # Tasks database (can be repurposed)

# Output directory
OUTPUT_BASE_DIR = Path.home() / "clawd" / "content_scripts"


@dataclass
class ContentIdea:
    """Represents a content idea from Notion."""
    title: str
    description: str
    category: str
    target_audience: str
    key_points: list
    notion_url: Optional[str] = None
    tags: list = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class ScriptOutline:
    """Generated script outline for a content idea."""
    title: str
    hook: str
    intro: str
    talking_points: list
    call_to_action: str
    estimated_duration: str
    tone: str


class NotionClient:
    """Client for interacting with Notion API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json"
        }
    
    def query_database(self, database_id: str, filter_obj: Optional[dict] = None) -> list:
        """Query a Notion database and return results."""
        url = f"{self.base_url}/databases/{database_id}/query"
        
        payload = {}
        if filter_obj:
            payload["filter"] = filter_obj
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            print(f"❌ Error querying Notion database: {e}")
            return []
    
    def get_page(self, page_id: str) -> Optional[dict]:
        """Get a specific page from Notion."""
        url = f"{self.base_url}/pages/{page_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching page {page_id}: {e}")
            return None


class ContentPipeline:
    """Main pipeline for generating content scripts."""
    
    # Content categories and their characteristics
    CATEGORIES = {
        "educational": {
            "tone": "Informative and helpful",
            "hook_template": "Did you know that {topic}? Most bike owners don't realize...",
            "cta_template": "Subscribe for more cycling tips and tricks!"
        },
        "promotional": {
            "tone": "Enthusiastic and persuasive",
            "hook_template": "What if I told you that you could {benefit} without {obstacle}?",
            "cta_template": "Try it free today - visit trybeforeyou.bike!"
        },
        "testimonial": {
            "tone": "Authentic and relatable",
            "hook_template": "I used to think {common_misconception}, until I discovered...",
            "cta_template": "Ready to start your own journey? Book your trial now!"
        },
        "how_to": {
            "tone": "Clear and instructional",
            "hook_template": "Struggling with {problem}? Here's the easiest way to fix it...",
            "cta_template": "What other cycling tips do you want to see? Let us know!"
        }
    }
    
    def __init__(self, notion_client: NotionClient):
        self.notion = notion_client
    
    def fetch_content_ideas(self, limit: Optional[int] = None) -> list:
        """Fetch content ideas from Notion database."""
        print("📚 Fetching content ideas from Notion...")
        
        # Filter for content ideas - looking for tasks with "Content" tag or similar
        filter_obj = {
            "and": [
                {
                    "property": "Status",
                    "status": {
                        "does_not_equal": "Done"
                    }
                }
            ]
        }
        
        results = self.notion.query_database(CONTENT_DATABASE_ID, filter_obj)
        
        ideas = []
        for page in results[:limit] if limit else results:
            idea = self._parse_content_idea(page)
            if idea:
                ideas.append(idea)
        
        print(f"✅ Found {len(ideas)} content ideas")
        return ideas
    
    def _parse_content_idea(self, page: dict) -> Optional[ContentIdea]:
        """Parse a Notion page into a ContentIdea object."""
        properties = page.get("properties", {})
        
        # Extract title
        title_prop = properties.get("Name", properties.get("title", {}))
        title = self._extract_text(title_prop)
        
        if not title:
            return None
        
        # Extract description (if available)
        desc_prop = properties.get("Description", properties.get("description", {}))
        description = self._extract_text(desc_prop) or "No description provided"
        
        # Determine category based on tags or title keywords
        category = self._detect_category(title, description)
        
        # Extract tags
        tags = []
        tags_prop = properties.get("Tags", properties.get("tags", {}))
        if tags_prop.get("multi_select"):
            tags = [t["name"] for t in tags_prop["multi_select"]]
        
        # Build key points from description
        key_points = self._extract_key_points(description)
        
        # Determine target audience
        target_audience = self._detect_audience(title, description, tags)
        
        return ContentIdea(
            title=title,
            description=description,
            category=category,
            target_audience=target_audience,
            key_points=key_points,
            notion_url=page.get("url"),
            tags=tags
        )
    
    def _extract_text(self, property_obj: dict) -> str:
        """Extract text from a Notion property."""
        if "title" in property_obj:
            texts = [t["text"]["content"] for t in property_obj["title"]]
            return " ".join(texts)
        elif "rich_text" in property_obj:
            texts = [t["text"]["content"] for t in property_obj["rich_text"]]
            return " ".join(texts)
        return ""
    
    def _detect_category(self, title: str, description: str) -> str:
        """Detect content category based on keywords."""
        text = (title + " " + description).lower()
        
        if any(word in text for word in ["how to", "guide", "tutorial", "steps", "tips"]):
            return "how_to"
        elif any(word in text for word in ["review", "testimonial", "story", "experience"]):
            return "testimonial"
        elif any(word in text for word in ["discount", "offer", "deal", "free", "promo"]):
            return "promotional"
        else:
            return "educational"
    
    def _detect_audience(self, title: str, description: str, tags: list) -> str:
        """Detect target audience based on content."""
        text = (title + " " + description).lower()
        
        if any(word in text for word in ["beginner", "new to", "first time", "start"]):
            return "Beginner cyclists"
        elif any(word in text for word in ["family", "kids", "children"]):
            return "Families"
        elif any(word in text for word in ["commute", "work", "office"]):
            return "Commuters"
        elif any(word in text for word in ["fitness", "exercise", "health", "training"]):
            return "Fitness enthusiasts"
        else:
            return "General cycling enthusiasts"
    
    def _extract_key_points(self, description: str) -> list:
        """Extract key points from description."""
        # Simple extraction - split by common delimiters
        points = []
        
        # Look for bullet-like patterns or numbered lists
        import re
        
        # Split by numbers or bullets
        parts = re.split(r'(?:\d+\.|\*\s+|\-\s+|\•\s+)', description)
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) > 1:
            points = parts[:5]  # Limit to 5 points
        else:
            # Just split by sentences
            sentences = re.split(r'[.!?]+', description)
            points = [s.strip() for s in sentences if s.strip()][:3]
        
        return points if points else [description[:100] + "..."]
    
    def generate_script_outline(self, idea: ContentIdea) -> ScriptOutline:
        """Generate a structured script outline from a content idea."""
        category_config = self.CATEGORIES.get(idea.category, self.CATEGORIES["educational"])
        
        # Generate hook
        hook = self._generate_hook(idea, category_config["hook_template"])
        
        # Generate intro
        intro = self._generate_intro(idea)
        
        # Generate talking points
        talking_points = self._generate_talking_points(idea)
        
        # Generate CTA
        cta = category_config["cta_template"]
        
        # Estimate duration
        duration = self._estimate_duration(len(talking_points))
        
        return ScriptOutline(
            title=idea.title,
            hook=hook,
            intro=intro,
            talking_points=talking_points,
            call_to_action=cta,
            estimated_duration=duration,
            tone=category_config["tone"]
        )
    
    def _generate_hook(self, idea: ContentIdea, template: str) -> str:
        """Generate an attention-grabbing hook."""
        # Simple template filling
        topic = idea.title.lower().replace("how to", "").replace("why", "").strip()
        
        if "{topic}" in template:
            return template.format(topic=topic)
        elif "{benefit}" in template:
            benefit = idea.key_points[0] if idea.key_points else "enjoy cycling"
            obstacle = "the hassle"
            return template.format(benefit=benefit, obstacle=obstacle)
        elif "{common_misconception}" in template:
            misconception = "cycling was too expensive"
            return template.format(common_misconception=misconception)
        elif "{problem}" in template:
            problem = topic
            return template.format(problem=problem)
        
        return f"🔥 {idea.title} - you won't believe what we discovered!"
    
    def _generate_intro(self, idea: ContentIdea) -> str:
        """Generate video intro."""
        intros = [
            f"Hey there, cycling enthusiasts! Welcome back to Try Before You Bike. Today we're diving into {idea.title}.",
            f"What's up, riders! In this video, we're exploring {idea.title}. Let's get started!",
            f"Hello and welcome! If you've ever wondered about {idea.title}, you're in the right place.",
        ]
        import random
        return random.choice(intros)
    
    def _generate_talking_points(self, idea: ContentIdea) -> list:
        """Generate structured talking points."""
        points = []
        
        # Opening context
        points.append({
            "timestamp": "0:00-0:30",
            "section": "Opening",
            "content": f"Introduce the topic: {idea.title}",
            "key_message": f"Why this matters to {idea.target_audience}"
        })
        
        # Main content points
        for i, key_point in enumerate(idea.key_points[:3], 1):
            points.append({
                "timestamp": f"0:{30 + (i-1)*60}-0:{30 + i*60}",
                "section": f"Point {i}",
                "content": key_point,
                "key_message": f"Takeaway #{i}"
            })
        
        # Add TBYB specific content
        points.append({
            "timestamp": f"0:{30 + len(idea.key_points)*60}-0:{30 + (len(idea.key_points)+1)*60}",
            "section": "TBYB Connection",
            "content": "Explain how Try Before You Bike can help with this",
            "key_message": "Our service makes this easy and risk-free"
        })
        
        # Closing
        points.append({
            "timestamp": f"0:{30 + (len(idea.key_points)+2)*60}+",
            "section": "Wrap-up",
            "content": "Summarize key takeaways",
            "key_message": "Next steps for the viewer"
        })
        
        return points
    
    def _estimate_duration(self, num_points: int) -> str:
        """Estimate video duration based on content."""
        minutes = max(1, num_points - 1)
        if minutes <= 1:
            return "30-60 seconds (Short)"
        elif minutes <= 3:
            return f"{minutes}-{minutes+1} minutes (Standard)"
        else:
            return f"{minutes}-{minutes+2} minutes (Long-form)"
    
    def format_script(self, outline: ScriptOutline) -> str:
        """Format the script outline into a readable template."""
        lines = [
            "=" * 70,
            f"🎬 CONTENT SCRIPT: {outline.title.upper()}",
            "=" * 70,
            "",
            f"📊 Category: {outline.tone}",
            f"⏱️  Estimated Duration: {outline.estimated_duration}",
            "",
            "-" * 70,
            "🎣 HOOK (First 5 seconds - GRAB ATTENTION)",
            "-" * 70,
            f'"{outline.hook}"',
            "",
            "-" * 70,
            "👋 INTRO (0:00-0:15)",
            "-" * 70,
            outline.intro,
            "",
            "-" * 70,
            "📋 TALKING POINTS",
            "-" * 70,
            "",
        ]
        
        for point in outline.talking_points:
            lines.extend([
                f"⏰ {point['timestamp']}",
                f"📍 {point['section']}",
                f"   📝 Content: {point['content']}",
                f"   🎯 Key Message: {point['key_message']}",
                ""
            ])
        
        lines.extend([
            "-" * 70,
            "📣 CALL TO ACTION (End of video)",
            "-" * 70,
            f'"{outline.call_to_action}"',
            "",
            "-" * 70,
            "🎨 PRODUCTION NOTES",
            "-" * 70,
            f"• Tone: {outline.tone}",
            "• B-roll suggestions: Bike close-ups, happy riders, app interface",
            "• Music: Upbeat, energetic background track",
            "• Captions: Enable for accessibility",
            "",
            "=" * 70,
            "✅ SCRIPT READY FOR RECORDING",
            "=" * 70,
            ""
        ])
        
        return "\n".join(lines)
    
    def run(self, limit: Optional[int] = None) -> Path:
        """Run the full pipeline and save outputs."""
        # Create output directory
        today = datetime.now().strftime("%Y-%m-%d")
        output_dir = OUTPUT_BASE_DIR / today
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 Output directory: {output_dir}")
        
        # Fetch ideas
        ideas = self.fetch_content_ideas(limit)
        
        if not ideas:
            print("⚠️  No content ideas found. Check your Notion database.")
            return output_dir
        
        # Generate and save scripts
        scripts_generated = 0
        for idea in ideas:
            outline = self.generate_script_outline(idea)
            formatted_script = self.format_script(outline)
            
            # Save individual script
            safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in idea.title)
            safe_title = safe_title[:50]  # Limit length
            filename = f"{scripts_generated + 1:02d}_{safe_title.replace(' ', '_')}.txt"
            filepath = output_dir / filename
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(formatted_script)
            
            print(f"📝 Saved: {filename}")
            scripts_generated += 1
        
        # Save summary JSON
        summary = {
            "generated_at": datetime.now().isoformat(),
            "total_scripts": scripts_generated,
            "ideas": [asdict(idea) for idea in ideas]
        }
        
        summary_path = output_dir / "_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n🎉 Pipeline complete! Generated {scripts_generated} scripts in {output_dir}")
        return output_dir


def main():
    parser = argparse.ArgumentParser(
        description="TBYB Content Pipeline Generator - Create video scripts from Notion ideas"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of ideas to process"
    )
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        default=None,
        help="Notion API key (or set NOTION_KEY env var)"
    )
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or NOTION_API_KEY
    
    if not api_key:
        print("❌ Error: Notion API key required. Set NOTION_KEY environment variable or use --api-key")
        sys.exit(1)
    
    # Run pipeline
    notion_client = NotionClient(api_key)
    pipeline = ContentPipeline(notion_client)
    
    try:
        output_dir = pipeline.run(limit=args.limit)
        print(f"\n✨ All done! Check your scripts at: {output_dir}")
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
