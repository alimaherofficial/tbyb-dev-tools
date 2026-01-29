#!/bin/bash
# Nightly Build Script for Ali
# This script runs every night at 11 PM Cairo time to build something useful
# Add this to crontab with: 0 23 * * * /path/to/tbyb-dev-tools/nightly-build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/nightly-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG_FILE")"

exec > >(tee -a "$LOG_FILE")
exec 2>&1

echo "=========================================="
echo "🌙 Nightly Build Session - $(date)"
echo "=========================================="

# Check Linear for urgent issues
echo "📋 Checking Linear issues..."
# Set LINEAR_API_KEY environment variable before running this script
# Example: export LINEAR_API_KEY="your_key_here"

if [ -z "$LINEAR_API_KEY" ]; then
    echo "  ⚠️  LINEAR_API_KEY not set, skipping Linear check"
    URGENT_ISSUES=""
else
    URGENT_ISSUES=$(curl -s -X POST "https://api.linear.app/graphql" \
      -H "Authorization: $LINEAR_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"query": "query { issues(filter: { assignee: { email: { eq: \"ali840085@gmail.com\" } } state: { type: { in: [\"started\", \"unstarted\"] } } }) { nodes { id title identifier state { name } priorityLabel dueDate } } }"}' \
      | python3 -c "import sys, json; data = json.load(sys.stdin); issues = data.get('data', {}).get('issues', {}).get('nodes', []); [print(f\"  - {i['identifier']}: {i['title']} [{i['state']['name']}]") for i in issues]" 2>/dev/null || echo "  Could not fetch Linear issues")
fi

echo "$URGENT_ISSUES"

# Run cron monitor health check
echo ""
echo "⏰ Checking cron jobs..."
cd "$SCRIPT_DIR"
python3 cron_monitor.py --report > /tmp/cron-status.json 2>/dev/null || echo "  No cron data yet"

# Run email health check
echo ""
echo "📧 Checking email system..."
python3 email_health.py --json > /tmp/email-status.json 2>/dev/null || echo "  No email data yet"

# TODO: Add your build tasks here
# Examples:
# - Generate reports
# - Run database maintenance
# - Build dashboard components
# - Update documentation

echo ""
echo "✅ Nightly build complete!"
echo "Log saved to: $LOG_FILE"
echo "=========================================="

# Send summary to Telegram (optional - requires Telegram bot setup)
# You can uncomment and configure this if you want notifications
# curl -s -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
#   -d "chat_id=<CHAT_ID>" \
#   -d "text=🌙 Nightly build complete. Log: $LOG_FILE"
