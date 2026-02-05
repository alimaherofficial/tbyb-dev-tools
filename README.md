# TBYB Dev Tools

A collection of development tools for Try Before You Bike (TBYB) - built to streamline content creation and project management workflows.

## 🚀 Tools Overview

### 1. Content Pipeline Generator (`content_pipeline.py`)

Automatically generates video script outlines from content ideas stored in Notion.

**What it does:**
- Fetches content ideas from your Notion database
- Generates structured script templates with:
  - Attention-grabbing hooks
  - Professional intros
  - Timed talking points
  - Call-to-action suggestions
  - Production notes
- Categorizes content (educational, promotional, testimonial, how-to)
- Estimates video duration
- Saves scripts to dated folders for easy organization

**Usage:**
```bash
# Set your Notion API key
export NOTION_KEY="your_notion_api_key"

# Run the pipeline
python content_pipeline.py

# Limit to 5 ideas
python content_pipeline.py --limit 5
```

**Output:** Scripts saved to `~/clawd/content_scripts/YYYY-MM-DD/`

---

### 2. Task Syncer (`task_syncer.py`)

Synchronizes tasks between Notion and Linear, identifying discrepancies and generating sync reports.

**What it does:**
- Fetches all tasks from Notion database
- Fetches all issues from Linear (TBYB project)
- Cross-references and identifies:
  - Tasks in Notion but missing in Linear
  - Issues in Linear not tracked in Notion
  - Items with mismatched priorities
- Generates detailed sync reports with recommendations

**Usage:**
```bash
# Set your API keys
export NOTION_KEY="your_notion_api_key"
export LINEAR_KEY="your_linear_api_key"

# Run the sync
python task_syncer.py

# Custom output directory
python task_syncer.py --output /path/to/reports
```

**Output:** 
- Text reports: `~/clawd/sync_reports/sync_report_YYYYMMDD_HHMMSS.txt`
- JSON exports: `~/clawd/sync_reports/sync_data_YYYYMMDD_HHMMSS.json`

---

## 📋 Prerequisites

- Python 3.8+
- Notion API key (from https://www.notion.so/my-integrations)
- Linear API key (from https://linear.app/settings/api)

## 🛠️ Installation

```bash
# Clone/navigate to the dev-tools directory
cd /home/bilo/code/tbyb-dev-tools

# Install dependencies
pip install -r requirements.txt

# Or use a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 🔧 Configuration

### Notion Setup
1. Create an integration at https://www.notion.so/my-integrations
2. Share your Tasks database with the integration
3. Copy the API key and set as `NOTION_KEY` environment variable

### Linear Setup
1. Get your API key from https://linear.app/settings/api
2. Set as `LINEAR_KEY` environment variable
3. The tool connects to the "TBYB" team by default

### Environment Variables
```bash
# Add to your ~/.bashrc or ~/.zshrc
export NOTION_KEY="ntn_your_key_here"
export LINEAR_KEY="lin_api_your_key_here"
```

## 📁 Output Structure

```
~/clawd/
├── content_scripts/
│   └── 2026-01-31/
│       ├── 01_Why_Electric_Bikes_Are_Perfect.txt
│       ├── 02_How_to_Choose_Your_First_Bike.txt
│       └── _summary.json
└── sync_reports/
    ├── sync_report_20260131_234500.txt
    └── sync_data_20260131_234500.json
```

## 🎯 Script Templates

The content pipeline generates scripts with:

- **Hook**: First 5 seconds to grab attention
- **Intro**: Welcome and topic introduction
- **Talking Points**: Timestamped sections with key messages
- **Call-to-Action**: End with clear next steps
- **Production Notes**: Tone, B-roll suggestions, music, captions

## 📊 Sync Report Features

The task syncer generates reports showing:

- Summary statistics
- Missing items in each system
- Priority mismatches with recommendations
- Action items to resolve sync issues
- Full JSON export for programmatic processing

## 🔄 Automation Ideas

Add to your crontab for nightly runs:

```bash
# Run content pipeline every Sunday at 9 AM
0 9 * * 0 cd /home/bilo/code/tbyb-dev-tools && python content_pipeline.py

# Run task syncer every day at 8 AM
0 8 * * * cd /home/bilo/code/tbyb-dev-tools && python task_syncer.py
```

## 🐛 Troubleshooting

**"No tasks found"**
- Check that your Notion database is shared with the integration
- Verify the database ID in the script matches your setup

**"Team not found" in Linear**
- Ensure your API key has access to the TBYB team
- Check the team key in the script (default: "TBYB")

**Permission errors**
- Verify environment variables are set correctly
- Check file permissions in output directories

## 📝 License

Internal TBYB tooling - For use by authorized team members only.

---

Built with 💚 by the TBYB Dev Team
