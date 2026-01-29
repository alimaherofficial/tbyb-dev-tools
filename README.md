# TBYB Development Tools

Lightweight monitoring and utility tools for the Try Before You Bike platform.

Built for: **Ali Maher** (@alimaherofficial)  
Created by: **bilo** 🤖 (your AI assistant)

---

## 🚀 Quick Start

```bash
# Clone the tools
git clone https://github.com/alimaherofficial/tbyb-dev-tools.git
cd tbyb-dev-tools

# No installation needed - pure Python standard library!
python3 cron_monitor.py
```

---

## 📦 Tools Included

### 1. 🔍 Cron Monitor (`cron_monitor.py`)

Monitor your NestJS cron jobs without modifying your main application.

**Features:**
- ✅ Track job execution history
- ✅ Monitor success/failure rates  
- ✅ Measure execution duration
- ✅ JSON report generation
- ✅ Watch mode for real-time monitoring

**Usage:**
```bash
# Show current status
python3 cron_monitor.py

# Watch mode (refreshes every 5s)
python3 cron_monitor.py --watch

# Generate JSON report for dashboards
python3 cron_monitor.py --report
```

**Sample Output:**
```
================================================================================
                          TBYB Cron Jobs Status                               
================================================================================
Job Name                       Last Run             Status     24h Runs   Avg (ms)
--------------------------------------------------------------------------------
daily-cleanup                  2026-01-29 22:00:00  ✓ OK       1          452    
subscription-reminders         2026-01-29 09:00:00  ✓ OK       3          123    
report-generation              Never                -          0          -      
================================================================================
```

**Integration with NestJS:**

Wrap your cron jobs like this:

```typescript
// Import the monitor wrapper
import { monitoredCron } from './utils/cron-monitor';

@Cron('0 0 * * *')
async handleDailyCleanup() {
  await monitoredCron('daily-cleanup', async () => {
    // Your actual cron logic
    await this.cleanupService.runDailyCleanup();
  })();
}
```

---

### 2. 📧 Email Health Checker (`email_health.py`)

Monitor email delivery health and catch issues before they affect customers.

**Tracks:**
- 📊 Delivery rates (should be >95%)
- 📊 Bounce rates (should be <5%)
- 📊 Failure rates (should be <5%)
- 📊 Pending queue size
- 📊 Per-template performance

**Usage:**
```bash
# Quick health check
python3 email_health.py

# Detailed report with template breakdown
python3 email_health.py --detailed

# Watch mode for monitoring
python3 email_health.py --watch

# JSON output for dashboards
python3 email_health.py --json
```

**Health Status Levels:**
- ✅ **HEALTHY** - All metrics within normal ranges
- ⚠️ **WARNING** - Some metrics need attention
- ❌ **CRITICAL** - Immediate action required
- ❓ **UNKNOWN** - No data available yet

---

## 🎯 Addresses Your Linear Issues

| Tool | Linear Issue | Status |
|------|--------------|--------|
| `cron_monitor.py` | [TRY-168](https://linear.app/try-before-you-bike/issue/TRY-168) - Cron Jobs Dashboard | ✅ Provides monitoring foundation |
| `email_health.py` | [TRY-149](https://linear.app/try-before-you-bike/issue/TRY-149) - Emails system review | ✅ Health monitoring ready |

---

## 🔧 Setup

### Option 1: Standalone (Recommended)
Just copy the scripts you need into your project:
```bash
cp cron_monitor.py /path/to/tbyb-server/utils/
cp email_health.py /path/to/tbyb-server/utils/
```

### Option 2: Git Submodule
```bash
cd /path/to/tbyb-server
git submodule add https://github.com/alimaherofficial/tbyb-dev-tools.git tools
```

### Option 3: Nightly Automation
Add to your crontab for nightly checks:
```bash
# Edit crontab
crontab -e

# Add this line for 11 PM Cairo time:
0 23 * * * /path/to/tbyb-dev-tools/nightly-build.sh
```

---

## 💾 Data Storage

All tools use **SQLite** databases stored in `.data/` directory:
- `cron-monitor.db` - Cron job execution history
- `email-health.db` - Email delivery metrics

This keeps everything lightweight with no external dependencies.

---

## 🛣️ Roadmap

Coming soon:
- [ ] **Database Health Checker** - PostgreSQL connection monitoring
- [ ] **API Latency Tracker** - Endpoint response time monitoring
- [ ] **Business Report CLI** - Daily/weekly business metrics
- [ ] **Slack Integration** - Alert notifications

---

## 🤝 Contributing

These tools are built specifically for TBYB but feel free to adapt them!

To suggest features or report issues:
1. Create an issue in Linear
2. Tag it with `dev-tools`
3. I'll pick it up in the next nightly session

---

Built with 🐾 by **bilo** for Ali Maher