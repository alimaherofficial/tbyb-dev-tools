#!/usr/bin/env python3
"""
TBYB Email System Health Checker

Checks email delivery health by monitoring:
- Bounce rates
- Delivery rates  
- Queue status
- Provider health (if using SendGrid/AWS SES/etc)

Usage:
    python email_health.py              # Quick health check
    python email_health.py --detailed   # Full report with trends
    python email_health.py --watch      # Monitor mode
"""

import json
import sqlite3
import argparse
import os
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class EmailMetrics:
    total_sent: int
    delivered: int
    bounced: int
    failed: int
    pending: int
    avg_delivery_time_ms: Optional[float]
    last_check: datetime


class EmailHealthChecker:
    """Check email system health for TBYB"""
    
    def __init__(self, db_path: str = ".data/email-health.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the email health database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient TEXT NOT NULL,
                template_name TEXT,
                status TEXT NOT NULL,  -- 'sent', 'delivered', 'bounced', 'failed', 'pending'
                provider TEXT,  -- 'sendgrid', 'ses', 'smtp', etc
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivered_at TIMESTAMP,
                bounced_at TIMESTAMP,
                error_message TEXT,
                metadata TEXT  -- JSON blob
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_status ON email_logs(status)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sent_at ON email_logs(sent_at)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_template ON email_logs(template_name)
        ''')
        
        conn.commit()
        conn.close()
    
    def log_email(self, recipient: str, template_name: str, 
                  status: str = 'pending', provider: str = None,
                  metadata: Dict = None):
        """Log an email event"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO email_logs (recipient, template_name, status, provider, metadata)
            VALUES (?, ?, ?, ?, ?)
        ''', (recipient, template_name, status, provider, 
              json.dumps(metadata) if metadata else None))
        
        conn.commit()
        conn.close()
    
    def update_status(self, recipient: str, template_name: str, 
                      new_status: str, error_message: str = None):
        """Update email status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp_field = None
        if new_status == 'delivered':
            timestamp_field = 'delivered_at'
        elif new_status == 'bounced':
            timestamp_field = 'bounced_at'
        
        if timestamp_field:
            cursor.execute(f'''
                UPDATE email_logs 
                SET status = ?, error_message = ?, {timestamp_field} = CURRENT_TIMESTAMP
                WHERE recipient = ? AND template_name = ?
                ORDER BY sent_at DESC
                LIMIT 1
            ''', (new_status, error_message, recipient, template_name))
        else:
            cursor.execute('''
                UPDATE email_logs 
                SET status = ?, error_message = ?
                WHERE recipient = ? AND template_name = ?
                ORDER BY sent_at DESC
                LIMIT 1
            ''', (new_status, error_message, recipient, template_name))
        
        conn.commit()
        conn.close()
    
    def get_metrics(self, hours: int = 24, template: str = None) -> EmailMetrics:
        """Get email metrics for the last N hours"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        if template:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                    SUM(CASE WHEN status = 'bounced' THEN 1 ELSE 0 END) as bounced,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
                FROM email_logs 
                WHERE sent_at > ? AND template_name = ?
            ''', (since.isoformat(), template))
        else:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                    SUM(CASE WHEN status = 'bounced' THEN 1 ELSE 0 END) as bounced,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
                FROM email_logs 
                WHERE sent_at > ?
            ''', (since.isoformat(),))
        
        result = cursor.fetchone()
        conn.close()
        
        return EmailMetrics(
            total_sent=result[0] or 0,
            delivered=result[1] or 0,
            bounced=result[2] or 0,
            failed=result[3] or 0,
            pending=result[4] or 0,
            avg_delivery_time_ms=None,  # TODO: Calculate from timestamps
            last_check=datetime.utcnow()
        )
    
    def get_health_status(self) -> Dict:
        """Get overall health status"""
        metrics = self.get_metrics(hours=24)
        
        if metrics.total_sent == 0:
            return {
                'status': 'unknown',
                'message': 'No emails sent in last 24h',
                'metrics': metrics.__dict__
            }
        
        delivery_rate = metrics.delivered / metrics.total_sent
        bounce_rate = metrics.bounced / metrics.total_sent
        failure_rate = metrics.failed / metrics.total_sent
        
        status = 'healthy'
        issues = []
        
        if delivery_rate < 0.95:
            status = 'warning'
            issues.append(f'Low delivery rate: {delivery_rate:.1%}')
        
        if bounce_rate > 0.05:
            status = 'critical'
            issues.append(f'High bounce rate: {bounce_rate:.1%}')
        
        if failure_rate > 0.05:
            status = 'critical'
            issues.append(f'High failure rate: {failure_rate:.1%}')
        
        if metrics.pending > 50:
            status = 'warning'
            issues.append(f'Large pending queue: {metrics.pending} emails')
        
        return {
            'status': status,
            'message': '; '.join(issues) if issues else 'All systems operational',
            'metrics': {
                'total_sent': metrics.total_sent,
                'delivery_rate': round(delivery_rate, 4),
                'bounce_rate': round(bounce_rate, 4),
                'failure_rate': round(failure_rate, 4),
                'pending': metrics.pending
            }
        }
    
    def get_top_templates(self, limit: int = 10) -> List[Dict]:
        """Get most used email templates"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=24)
        
        cursor.execute('''
            SELECT 
                template_name,
                COUNT(*) as count,
                SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                SUM(CASE WHEN status = 'bounced' THEN 1 ELSE 0 END) as bounced
            FROM email_logs 
            WHERE sent_at > ? AND template_name IS NOT NULL
            GROUP BY template_name
            ORDER BY count DESC
            LIMIT ?
        ''', (since.isoformat(), limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'template': row[0],
                'sent': row[1],
                'delivered': row[2],
                'bounced': row[3],
                'delivery_rate': round(row[2] / row[1], 4) if row[1] > 0 else 0
            })
        
        conn.close()
        return results


def print_health(checker: EmailHealthChecker, detailed: bool = False):
    """Print health report"""
    health = checker.get_health_status()
    
    status_emoji = {
        'healthy': '✅',
        'warning': '⚠️',
        'critical': '❌',
        'unknown': '❓'
    }
    
    print("\n" + "="*70)
    print(f"{'TBYB Email System Health':^70}")
    print("="*70)
    
    emoji = status_emoji.get(health['status'], '❓')
    print(f"\n{emoji} Status: {health['status'].upper()}")
    print(f"   Message: {health['message']}")
    
    if 'metrics' in health and health['metrics']:
        m = health['metrics']
        print(f"\n📊 Last 24 Hours:")
        print(f"   Total Sent:      {m['total_sent']:,}")
        print(f"   Delivery Rate:   {m['delivery_rate']:.1%}")
        print(f"   Bounce Rate:     {m['bounce_rate']:.1%}")
        print(f"   Failure Rate:    {m['failure_rate']:.1%}")
        print(f"   Pending:         {m['pending']:,}")
    
    if detailed:
        templates = checker.get_top_templates()
        if templates:
            print(f"\n📧 Top Email Templates (24h):")
            print(f"   {'Template':<30} {'Sent':<8} {'Delivered':<10} {'Rate':<8}")
            print("   " + "-"*58)
            for t in templates:
                print(f"   {t['template']:<30} {t['sent']:<8} {t['delivered']:<10} {t['delivery_rate']:.1%}")
    
    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(description='TBYB Email System Health Checker')
    parser.add_argument('--detailed', action='store_true', 
                        help='Show detailed report with templates')
    parser.add_argument('--watch', action='store_true',
                        help='Watch mode - refreshes every 30s')
    parser.add_argument('--db', default='.data/email-health.db',
                        help='Database path')
    parser.add_argument('--json', action='store_true',
                        help='Output JSON instead of formatted text')
    
    args = parser.parse_args()
    
    checker = EmailHealthChecker(args.db)
    
    if args.json:
        health = checker.get_health_status()
        print(json.dumps(health, indent=2, default=str))
    elif args.watch:
        import time
        import sys
        try:
            while True:
                os.system('clear' if os.name != 'nt' else 'cls')
                print_health(checker, args.detailed)
                print(f"\nRefreshing every 30s... (Ctrl+C to exit)")
                time.sleep(30)
        except KeyboardInterrupt:
            print("\nExiting...")
            sys.exit(0)
    else:
        print_health(checker, args.detailed)


if __name__ == '__main__':
    main()
