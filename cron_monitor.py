#!/usr/bin/env python3
"""
TBYB Cron Jobs Monitor
A lightweight monitoring utility for NestJS cron jobs

This helps you track:
- Which cron jobs are configured
- When they last ran
- Success/failure rates
- Execution duration

Usage:
    python cron_monitor.py              # Show status of all jobs
    python cron_monitor.py --watch    # Watch mode (refreshes every 5s)
    python cron_monitor.py --report   # Generate JSON report
"""

import json
import sqlite3
import argparse
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class CronJob:
    name: str
    schedule: str
    last_run: Optional[datetime] = None
    last_status: Optional[str] = None
    last_duration_ms: Optional[int] = None
    run_count_24h: int = 0
    error_count_24h: int = 0
    avg_duration_ms: Optional[float] = None
    next_run: Optional[datetime] = None


class CronMonitor:
    """Monitor for TBYB cron jobs"""
    
    def __init__(self, db_path: str = ".data/cron-monitor.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the monitoring database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT,  -- 'success', 'error', 'running'
                error_message TEXT,
                duration_ms INTEGER,
                metadata TEXT  -- JSON blob for extra context
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_job_name ON job_runs(job_name)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_started_at ON job_runs(started_at)
        ''')
        
        conn.commit()
        conn.close()
    
    def record_start(self, job_name: str, metadata: Optional[Dict] = None) -> int:
        """Record that a job started - returns the run ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO job_runs (job_name, status, metadata)
            VALUES (?, 'running', ?)
        ''', (job_name, json.dumps(metadata) if metadata else None))
        
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return run_id
    
    def record_complete(self, run_id: int, status: str, 
                        error_message: Optional[str] = None,
                        metadata: Optional[Dict] = None):
        """Record job completion"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Calculate duration
        cursor.execute('''
            SELECT started_at FROM job_runs WHERE id = ?
        ''', (run_id,))
        
        result = cursor.fetchone()
        if result:
            started_at = datetime.fromisoformat(result[0])
            completed_at = datetime.utcnow()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            
            # Merge metadata
            cursor.execute('SELECT metadata FROM job_runs WHERE id = ?', (run_id,))
            existing_metadata = cursor.fetchone()[0]
            existing = json.loads(existing_metadata) if existing_metadata else {}
            if metadata:
                existing.update(metadata)
            
            cursor.execute('''
                UPDATE job_runs 
                SET completed_at = CURRENT_TIMESTAMP,
                    status = ?,
                    error_message = ?,
                    duration_ms = ?,
                    metadata = ?
                WHERE id = ?
            ''', (status, error_message, duration_ms, json.dumps(existing), run_id))
            
            conn.commit()
        
        conn.close()
    
    def get_job_stats(self, job_name: str, hours: int = 24) -> Dict:
        """Get statistics for a specific job"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                AVG(duration_ms) as avg_duration,
                MAX(started_at) as last_run,
                MAX(CASE WHEN status = 'success' THEN started_at END) as last_success
            FROM job_runs 
            WHERE job_name = ? AND started_at > ?
        ''', (job_name, since.isoformat()))
        
        result = cursor.fetchone()
        conn.close()
        
        return {
            'total_runs': result[0] or 0,
            'errors': result[1] or 0,
            'avg_duration_ms': round(result[2], 2) if result[2] else None,
            'last_run': result[3],
            'last_success': result[4]
        }
    
    def get_all_jobs(self) -> List[str]:
        """Get list of all known job names"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT DISTINCT job_name FROM job_runs ORDER BY job_name')
        jobs = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return jobs
    
    def get_recent_runs(self, job_name: Optional[str] = None, 
                        limit: int = 10) -> List[Dict]:
        """Get recent job runs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if job_name:
            cursor.execute('''
                SELECT job_name, started_at, completed_at, status, 
                       error_message, duration_ms
                FROM job_runs 
                WHERE job_name = ?
                ORDER BY started_at DESC
                LIMIT ?
            ''', (job_name, limit))
        else:
            cursor.execute('''
                SELECT job_name, started_at, completed_at, status, 
                       error_message, duration_ms
                FROM job_runs 
                ORDER BY started_at DESC
                LIMIT ?
            ''', (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'job_name': row[0],
                'started_at': row[1],
                'completed_at': row[2],
                'status': row[3],
                'error_message': row[4],
                'duration_ms': row[5]
            })
        
        conn.close()
        return results
    
    def generate_report(self) -> Dict:
        """Generate a full monitoring report"""
        jobs = self.get_all_jobs()
        
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'jobs': {}
        }
        
        for job_name in jobs:
            stats = self.get_job_stats(job_name)
            recent = self.get_recent_runs(job_name, limit=5)
            
            report['jobs'][job_name] = {
                'stats': stats,
                'recent_runs': recent
            }
        
        return report


# Decorator for NestJS-style cron jobs
def monitored_cron(job_name: str, monitor: Optional[CronMonitor] = None):
    """Decorator to monitor a cron job function"""
    mon = monitor or CronMonitor()
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            run_id = mon.record_start(job_name)
            try:
                result = func(*args, **kwargs)
                mon.record_complete(run_id, 'success')
                return result
            except Exception as e:
                mon.record_complete(run_id, 'error', error_message=str(e))
                raise
        return wrapper
    return decorator


def print_status(monitor: CronMonitor):
    """Print a nice status table"""
    jobs = monitor.get_all_jobs()
    
    if not jobs:
        print("No jobs recorded yet. Jobs will appear here after they run.")
        return
    
    print("\n" + "="*80)
    print(f"{'TBYB Cron Jobs Status':^80}")
    print("="*80)
    print(f"{'Job Name':<30} {'Last Run':<20} {'Status':<10} {'24h Runs':<10} {'Avg (ms)':<10}")
    print("-"*80)
    
    for job_name in jobs:
        stats = monitor.get_job_stats(job_name)
        
        last_run = stats['last_run'] or 'Never'
        if isinstance(last_run, str) and len(last_run) > 19:
            last_run = last_run[:19]
        
        status = "✓ OK" if stats['errors'] == 0 else f"✗ {stats['errors']} errors"
        if stats['total_runs'] == 0:
            status = "-"
        
        avg_duration = str(stats['avg_duration_ms'] or '-')[:8]
        
        print(f"{job_name:<30} {str(last_run):<20} {status:<10} {stats['total_runs']:<10} {avg_duration:<10}")
    
    print("="*80)
    print("\nRun with --watch to auto-refresh every 5 seconds")
    print("Run with --report to get JSON output")


def main():
    parser = argparse.ArgumentParser(description='TBYB Cron Jobs Monitor')
    parser.add_argument('--watch', action='store_true', 
                        help='Watch mode - refreshes every 5 seconds')
    parser.add_argument('--report', action='store_true',
                        help='Generate JSON report')
    parser.add_argument('--db', default='.data/cron-monitor.db',
                        help='Database path')
    
    args = parser.parse_args()
    
    monitor = CronMonitor(args.db)
    
    if args.report:
        report = monitor.generate_report()
        print(json.dumps(report, indent=2))
    elif args.watch:
        import time
        import sys
        try:
            while True:
                os.system('clear' if os.name != 'nt' else 'cls')
                print_status(monitor)
                print(f"\nRefreshing every 5s... (Ctrl+C to exit)")
                time.sleep(5)
        except KeyboardInterrupt:
            print("\nExiting...")
            sys.exit(0)
    else:
        print_status(monitor)


if __name__ == '__main__':
    main()
