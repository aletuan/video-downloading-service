#!/usr/bin/env python3

"""
Cookie Management Tools for YouTube Download Service

This comprehensive utility provides advanced cookie management capabilities including:
- Cookie rotation scheduling and automation
- Cookie expiration monitoring and notifications
- Cookie health checks and diagnostics
- Cookie backup and restore operations
- Cookie access audit reporting
- Cookie performance monitoring and analytics

Usage:
    python cookie-management.py <command> [OPTIONS]

Commands:
    rotate              Rotate cookies (backup current, activate backup)
    check-expiration    Check cookie expiration status
    health-check        Perform comprehensive cookie health check
    backup              Create manual backup of current cookies
    restore             Restore cookies from backup
    audit               Generate cookie access audit report
    monitor             Show cookie performance monitoring data
    schedule            Set up automated cookie rotation schedule
    cleanup             Clean up old backups and temporary files

Examples:
    # Rotate cookies automatically
    python cookie-management.py rotate --notify

    # Check for expiring cookies
    python cookie-management.py check-expiration --warn-days 7

    # Perform health check
    python cookie-management.py health-check --detailed

    # Generate audit report
    python cookie-management.py audit --days 30 --format json
"""

import os
import sys
import json
import argparse
import logging
import asyncio
import smtplib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import boto3
import croniter
from cryptography.fernet import Fernet

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.core.config import settings
from app.core.cookie_manager import CookieManager


@dataclass
class CookieHealthStatus:
    """Cookie health status information."""
    active_present: bool = False
    backup_present: bool = False
    metadata_present: bool = False
    decryption_successful: bool = False
    cookie_count: int = 0
    expired_count: int = 0
    expiring_soon_count: int = 0
    domains: List[str] = field(default_factory=list)
    expires_earliest: Optional[datetime] = None
    expires_latest: Optional[datetime] = None
    last_rotation: Optional[datetime] = None
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class CookiePerformanceMetrics:
    """Cookie performance metrics."""
    total_downloads: int = 0
    successful_downloads: int = 0
    cookie_failures: int = 0
    success_rate: float = 0.0
    average_response_time: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    failure_rate_trend: str = "stable"
    performance_grade: str = "unknown"


class CookieManagementTools:
    """Comprehensive cookie management and monitoring tools."""
    
    def __init__(self, bucket_name: Optional[str] = None, aws_region: Optional[str] = None):
        """Initialize cookie management tools."""
        self.bucket_name = bucket_name or settings.cookie_s3_bucket or os.getenv('COOKIE_S3_BUCKET')
        self.aws_region = aws_region or os.getenv('AWS_REGION', 'us-east-1')
        self.encryption_key = settings.cookie_encryption_key or os.getenv('COOKIE_ENCRYPTION_KEY')
        
        if not self.bucket_name:
            raise ValueError("COOKIE_S3_BUCKET environment variable or bucket name required")
        
        if not self.encryption_key:
            raise ValueError("COOKIE_ENCRYPTION_KEY environment variable required")
        
        # Initialize encryption and AWS clients
        self.cipher_suite = Fernet(self._derive_key(self.encryption_key))
        self.s3_client = boto3.client('s3', region_name=self.aws_region)
        self.cloudwatch = boto3.client('cloudwatch', region_name=self.aws_region)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
    
    def _derive_key(self, password: str) -> bytes:
        """Derive a Fernet key from password using PBKDF2."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        import base64
        
        salt = b"youtube_cookie_salt_v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    async def rotate_cookies(self, notify: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """
        Rotate cookies by promoting backup to active and creating new backup.
        
        Args:
            notify: Send notification after rotation
            dry_run: Show what would be done without executing
            
        Returns:
            Dictionary with rotation results
        """
        result = {
            'success': False,
            'timestamp': datetime.utcnow().isoformat(),
            'dry_run': dry_run,
            'actions_taken': [],
            'warnings': [],
            'errors': []
        }
        
        try:
            self.logger.info(f"Starting cookie rotation (dry_run={dry_run})")
            
            # Check if backup cookies exist
            backup_exists = False
            try:
                self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key='cookies/youtube-cookies-backup.txt'
                )
                backup_exists = True
                result['actions_taken'].append("Found backup cookies")
            except self.s3_client.exceptions.NoSuchKey:
                result['warnings'].append("No backup cookies found - cannot rotate")
                return result
            
            if not dry_run:
                # Step 1: Archive current active cookies
                try:
                    archive_key = f"cookies/archives/youtube-cookies-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
                    self.s3_client.copy_object(
                        Bucket=self.bucket_name,
                        CopySource={'Bucket': self.bucket_name, 'Key': 'cookies/youtube-cookies-active.txt'},
                        Key=archive_key
                    )
                    result['actions_taken'].append(f"Archived active cookies to {archive_key}")
                except self.s3_client.exceptions.NoSuchKey:
                    result['warnings'].append("No active cookies to archive")
                
                # Step 2: Promote backup to active
                self.s3_client.copy_object(
                    Bucket=self.bucket_name,
                    CopySource={'Bucket': self.bucket_name, 'Key': 'cookies/youtube-cookies-backup.txt'},
                    Key='cookies/youtube-cookies-active.txt'
                )
                result['actions_taken'].append("Promoted backup cookies to active")
                
                # Step 3: Update metadata
                metadata = await self._get_metadata()
                if metadata:
                    metadata['last_rotation'] = datetime.utcnow().isoformat()
                    metadata['rotation_count'] = metadata.get('rotation_count', 0) + 1
                    await self._save_metadata(metadata)
                    result['actions_taken'].append("Updated rotation metadata")
                
                result['success'] = True
                self.logger.info("Cookie rotation completed successfully")
                
                if notify:
                    await self._send_notification(
                        "Cookie Rotation Completed",
                        f"Cookies rotated successfully at {result['timestamp']}"
                    )
                    result['actions_taken'].append("Sent rotation notification")
            
            else:
                result['actions_taken'].extend([
                    "Would archive current active cookies",
                    "Would promote backup cookies to active", 
                    "Would update rotation metadata"
                ])
                result['success'] = True
        
        except Exception as e:
            error_msg = f"Cookie rotation failed: {str(e)}"
            result['errors'].append(error_msg)
            self.logger.error(error_msg)
        
        return result
    
    async def check_expiration(self, warn_days: int = 7) -> Dict[str, Any]:
        """
        Check cookie expiration status and identify expiring cookies.
        
        Args:
            warn_days: Number of days to warn before expiration
            
        Returns:
            Dictionary with expiration check results
        """
        result = {
            'timestamp': datetime.utcnow().isoformat(),
            'total_cookies': 0,
            'expired_cookies': 0,
            'expiring_soon': 0,
            'expiring_cookies': [],
            'expires_earliest': None,
            'expires_latest': None,
            'needs_attention': False,
            'recommendations': []
        }
        
        try:
            # Get active cookies
            cookies_content = await self._get_decrypted_cookies('cookies/youtube-cookies-active.txt')
            if not cookies_content:
                result['recommendations'].append("No active cookies found")
                return result
            
            cookies_data = await self._parse_cookies(cookies_content)
            result['total_cookies'] = len(cookies_data)
            
            now = datetime.utcnow()
            warn_threshold = now + timedelta(days=warn_days)
            expires_times = []
            
            for cookie in cookies_data:
                expires = cookie.get('expires')
                if expires:
                    try:
                        if isinstance(expires, (int, float)):
                            expires_dt = datetime.fromtimestamp(expires)
                        else:
                            expires_dt = datetime.fromisoformat(str(expires).replace('Z', '+00:00'))
                        
                        expires_times.append(expires_dt)
                        
                        if expires_dt < now:
                            result['expired_cookies'] += 1
                        elif expires_dt < warn_threshold:
                            result['expiring_soon'] += 1
                            result['expiring_cookies'].append({
                                'name': cookie.get('name', 'unknown'),
                                'domain': cookie.get('domain', 'unknown'),
                                'expires': expires_dt.isoformat(),
                                'days_remaining': (expires_dt - now).days
                            })
                    except (ValueError, TypeError):
                        continue
            
            if expires_times:
                result['expires_earliest'] = min(expires_times).isoformat()
                result['expires_latest'] = max(expires_times).isoformat()
            
            # Generate recommendations
            if result['expired_cookies'] > 0:
                result['needs_attention'] = True
                result['recommendations'].append(f"{result['expired_cookies']} cookies have expired - consider refreshing")
            
            if result['expiring_soon'] > 0:
                result['needs_attention'] = True
                result['recommendations'].append(f"{result['expiring_soon']} cookies expire within {warn_days} days")
            
            if not result['needs_attention']:
                result['recommendations'].append("All cookies are current and valid")
        
        except Exception as e:
            self.logger.error(f"Cookie expiration check failed: {str(e)}")
            result['error'] = str(e)
        
        return result
    
    async def health_check(self, detailed: bool = False) -> CookieHealthStatus:
        """
        Perform comprehensive cookie health check.
        
        Args:
            detailed: Include detailed diagnostic information
            
        Returns:
            CookieHealthStatus object with health information
        """
        status = CookieHealthStatus()
        
        try:
            # Check active cookies
            try:
                active_content = await self._get_decrypted_cookies('cookies/youtube-cookies-active.txt')
                if active_content:
                    status.active_present = True
                    status.decryption_successful = True
                    
                    # Parse cookies for detailed analysis
                    cookies_data = await self._parse_cookies(active_content)
                    status.cookie_count = len(cookies_data)
                    
                    # Analyze domains
                    domains = set()
                    expires_times = []
                    now = datetime.utcnow()
                    
                    for cookie in cookies_data:
                        if 'domain' in cookie:
                            domains.add(cookie['domain'].lstrip('.'))
                        
                        if 'expires' in cookie:
                            try:
                                expires = cookie['expires']
                                if isinstance(expires, (int, float)):
                                    expires_dt = datetime.fromtimestamp(expires)
                                else:
                                    expires_dt = datetime.fromisoformat(str(expires).replace('Z', '+00:00'))
                                
                                expires_times.append(expires_dt)
                                
                                if expires_dt < now:
                                    status.expired_count += 1
                                elif expires_dt < now + timedelta(days=7):
                                    status.expiring_soon_count += 1
                            except (ValueError, TypeError):
                                continue
                    
                    status.domains = sorted(list(domains))
                    if expires_times:
                        status.expires_earliest = min(expires_times)
                        status.expires_latest = max(expires_times)
                    
                    # Check for YouTube domains
                    youtube_domains = [d for d in domains if 'youtube.com' in d or 'google.com' in d]
                    if not youtube_domains:
                        status.warnings.append("No YouTube/Google domains found in cookies")
                
            except Exception as e:
                status.issues.append(f"Active cookies check failed: {str(e)}")
            
            # Check backup cookies
            try:
                backup_content = await self._get_decrypted_cookies('cookies/youtube-cookies-backup.txt')
                if backup_content:
                    status.backup_present = True
            except Exception:
                status.warnings.append("Backup cookies not available")
            
            # Check metadata
            try:
                metadata = await self._get_metadata()
                if metadata:
                    status.metadata_present = True
                    if 'last_rotation' in metadata:
                        status.last_rotation = datetime.fromisoformat(metadata['last_rotation'])
            except Exception:
                status.warnings.append("Metadata not available")
            
            # Health scoring
            if status.expired_count > 0:
                status.issues.append(f"{status.expired_count} expired cookies found")
            
            if status.expiring_soon_count > 0:
                status.warnings.append(f"{status.expiring_soon_count} cookies expire within 7 days")
            
            if not status.active_present:
                status.issues.append("No active cookies available")
            
            if not status.backup_present:
                status.warnings.append("No backup cookies available")
        
        except Exception as e:
            status.issues.append(f"Health check failed: {str(e)}")
        
        return status
    
    async def backup_cookies(self, source: str = "manual") -> Dict[str, Any]:
        """
        Create manual backup of current cookies.
        
        Args:
            source: Source identifier for the backup
            
        Returns:
            Dictionary with backup results
        """
        result = {
            'success': False,
            'timestamp': datetime.utcnow().isoformat(),
            'backup_key': None,
            'source': source
        }
        
        try:
            # Check if active cookies exist
            try:
                self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key='cookies/youtube-cookies-active.txt'
                )
            except self.s3_client.exceptions.NoSuchKey:
                result['error'] = "No active cookies found to backup"
                return result
            
            # Create backup with timestamp
            backup_key = f"cookies/backups/manual-backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
            
            # Copy active cookies to backup location
            self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource={'Bucket': self.bucket_name, 'Key': 'cookies/youtube-cookies-active.txt'},
                Key=backup_key,
                MetadataDirective='REPLACE',
                Metadata={
                    'backup-source': source,
                    'backup-timestamp': result['timestamp'],
                    'backup-type': 'manual'
                }
            )
            
            result['success'] = True
            result['backup_key'] = backup_key
            self.logger.info(f"Manual backup created: {backup_key}")
        
        except Exception as e:
            result['error'] = f"Backup failed: {str(e)}"
            self.logger.error(result['error'])
        
        return result
    
    async def restore_cookies(self, backup_key: str, confirm: bool = False) -> Dict[str, Any]:
        """
        Restore cookies from backup.
        
        Args:
            backup_key: S3 key of the backup to restore
            confirm: Confirmation flag to prevent accidental restores
            
        Returns:
            Dictionary with restore results
        """
        result = {
            'success': False,
            'timestamp': datetime.utcnow().isoformat(),
            'backup_key': backup_key,
            'actions_taken': []
        }
        
        if not confirm:
            result['error'] = "Restore operation requires confirmation (--confirm flag)"
            return result
        
        try:
            # Check if backup exists
            try:
                backup_response = self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=backup_key
                )
                result['actions_taken'].append(f"Verified backup exists: {backup_key}")
            except self.s3_client.exceptions.NoSuchKey:
                result['error'] = f"Backup not found: {backup_key}"
                return result
            
            # Archive current active cookies before restore
            if confirm:
                archive_key = f"cookies/archives/pre-restore-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
                try:
                    self.s3_client.copy_object(
                        Bucket=self.bucket_name,
                        CopySource={'Bucket': self.bucket_name, 'Key': 'cookies/youtube-cookies-active.txt'},
                        Key=archive_key
                    )
                    result['actions_taken'].append(f"Archived current cookies to {archive_key}")
                except self.s3_client.exceptions.NoSuchKey:
                    result['actions_taken'].append("No active cookies to archive")
                
                # Copy backup to active location
                self.s3_client.copy_object(
                    Bucket=self.bucket_name,
                    CopySource={'Bucket': self.bucket_name, 'Key': backup_key},
                    Key='cookies/youtube-cookies-active.txt',
                    MetadataDirective='REPLACE',
                    Metadata={
                        'restored-from': backup_key,
                        'restored-at': result['timestamp'],
                        'restored-by': os.getenv('USER', 'unknown')
                    }
                )
                
                result['success'] = True
                result['actions_taken'].append("Restored cookies from backup")
                self.logger.info(f"Cookies restored from backup: {backup_key}")
        
        except Exception as e:
            result['error'] = f"Restore failed: {str(e)}"
            self.logger.error(result['error'])
        
        return result
    
    async def generate_audit_report(self, days: int = 30, format: str = "text") -> Dict[str, Any]:
        """
        Generate cookie access audit report.
        
        Args:
            days: Number of days to include in report
            format: Output format (text, json, html)
            
        Returns:
            Dictionary with audit report data
        """
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'period_days': days,
            'period_start': (datetime.utcnow() - timedelta(days=days)).isoformat(),
            'period_end': datetime.utcnow().isoformat(),
            'format': format,
            'events': [],
            'summary': {
                'total_events': 0,
                'uploads': 0,
                'rotations': 0,
                'downloads': 0,
                'failures': 0
            }
        }
        
        try:
            # Collect S3 access logs if available
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Get CloudTrail events for S3 operations
            try:
                import boto3
                cloudtrail = boto3.client('cloudtrail', region_name=self.aws_region)
                
                events = cloudtrail.lookup_events(
                    LookupAttributes=[
                        {
                            'AttributeKey': 'ResourceName',
                            'AttributeValue': self.bucket_name
                        }
                    ],
                    StartTime=start_date,
                    EndTime=datetime.utcnow()
                )
                
                for event in events.get('Events', []):
                    if 'cookies/' in str(event.get('Resources', [])):
                        report['events'].append({
                            'timestamp': event['EventTime'].isoformat(),
                            'event_name': event['EventName'],
                            'user': event.get('Username', 'unknown'),
                            'source_ip': event.get('SourceIPAddress', 'unknown'),
                            'resources': [r.get('ResourceName', '') for r in event.get('Resources', [])]
                        })
                        
                        # Update summary
                        report['summary']['total_events'] += 1
                        if 'Put' in event['EventName']:
                            report['summary']['uploads'] += 1
                        elif 'Get' in event['EventName']:
                            report['summary']['downloads'] += 1
            
            except Exception as e:
                report['warning'] = f"CloudTrail access limited: {str(e)}"
            
            # Get application-level metrics from CloudWatch
            try:
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(days=days)
                
                # Query custom metrics if available
                response = self.cloudwatch.get_metric_statistics(
                    Namespace='YouTube/Downloader',
                    MetricName='CookieOperations',
                    Dimensions=[
                        {
                            'Name': 'Environment',
                            'Value': 'dev'
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                if response['Datapoints']:
                    report['cloudwatch_metrics'] = response['Datapoints']
                    
            except Exception:
                # CloudWatch metrics may not exist yet
                pass
            
            # Format report based on requested format
            if format == "html":
                report['formatted_output'] = self._format_audit_html(report)
            elif format == "json":
                report['formatted_output'] = json.dumps(report, indent=2)
            else:
                report['formatted_output'] = self._format_audit_text(report)
        
        except Exception as e:
            report['error'] = f"Audit report generation failed: {str(e)}"
        
        return report
    
    async def get_performance_metrics(self) -> CookiePerformanceMetrics:
        """Get cookie performance monitoring data."""
        metrics = CookiePerformanceMetrics()
        
        try:
            # Get metrics from CloudWatch if available
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            
            try:
                # Download success rate
                success_response = self.cloudwatch.get_metric_statistics(
                    Namespace='YouTube/Downloader',
                    MetricName='DownloadSuccess',
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                failure_response = self.cloudwatch.get_metric_statistics(
                    Namespace='YouTube/Downloader', 
                    MetricName='CookieFailure',
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                if success_response['Datapoints']:
                    metrics.successful_downloads = sum(dp['Sum'] for dp in success_response['Datapoints'])
                
                if failure_response['Datapoints']:
                    metrics.cookie_failures = sum(dp['Sum'] for dp in failure_response['Datapoints'])
                
                metrics.total_downloads = metrics.successful_downloads + metrics.cookie_failures
                if metrics.total_downloads > 0:
                    metrics.success_rate = (metrics.successful_downloads / metrics.total_downloads) * 100
            
            except Exception:
                # Fallback to basic health status if CloudWatch unavailable
                health = await self.health_check()
                metrics.performance_grade = "healthy" if not health.issues else "degraded"
            
            # Performance grading
            if metrics.success_rate >= 95:
                metrics.performance_grade = "excellent"
            elif metrics.success_rate >= 85:
                metrics.performance_grade = "good"
            elif metrics.success_rate >= 70:
                metrics.performance_grade = "fair"
            else:
                metrics.performance_grade = "poor"
        
        except Exception as e:
            self.logger.error(f"Performance metrics collection failed: {str(e)}")
        
        return metrics
    
    async def schedule_rotation(self, cron_expression: str, enable: bool = True) -> Dict[str, Any]:
        """
        Set up automated cookie rotation schedule.
        
        Args:
            cron_expression: Cron expression for scheduling (e.g., "0 2 * * 0" for weekly)
            enable: Enable or disable the schedule
            
        Returns:
            Dictionary with scheduling results
        """
        result = {
            'success': False,
            'cron_expression': cron_expression,
            'enabled': enable,
            'next_run': None
        }
        
        try:
            # Validate cron expression
            try:
                cron = croniter.croniter(cron_expression, datetime.utcnow())
                next_run = cron.get_next(datetime)
                result['next_run'] = next_run.isoformat()
            except Exception as e:
                result['error'] = f"Invalid cron expression: {str(e)}"
                return result
            
            # Create systemd timer or cron job (Linux/macOS)
            script_path = os.path.abspath(__file__)
            
            if enable:
                # Create cron job
                cron_command = f"{cron_expression} {sys.executable} {script_path} rotate --notify"
                
                # Add to crontab (simplified - production should use proper configuration management)
                try:
                    current_cron = subprocess.check_output(['crontab', '-l'], stderr=subprocess.DEVNULL).decode()
                except subprocess.CalledProcessError:
                    current_cron = ""
                
                if script_path not in current_cron:
                    new_cron = current_cron + f"\n# Cookie rotation schedule\n{cron_command}\n"
                    
                    # Write to temporary file and install
                    with open('/tmp/cookie_cron', 'w') as f:
                        f.write(new_cron)
                    
                    subprocess.run(['crontab', '/tmp/cookie_cron'], check=True)
                    os.remove('/tmp/cookie_cron')
                    
                    result['success'] = True
                    result['action'] = 'installed'
                else:
                    result['success'] = True
                    result['action'] = 'already_exists'
            else:
                # Remove from cron
                try:
                    current_cron = subprocess.check_output(['crontab', '-l']).decode()
                    lines = current_cron.split('\n')
                    filtered_lines = [line for line in lines if script_path not in line and 'Cookie rotation' not in line]
                    
                    new_cron = '\n'.join(filtered_lines)
                    with open('/tmp/cookie_cron', 'w') as f:
                        f.write(new_cron)
                    
                    subprocess.run(['crontab', '/tmp/cookie_cron'], check=True)
                    os.remove('/tmp/cookie_cron')
                    
                    result['success'] = True
                    result['action'] = 'removed'
                except subprocess.CalledProcessError:
                    result['success'] = True
                    result['action'] = 'not_found'
        
        except Exception as e:
            result['error'] = f"Schedule setup failed: {str(e)}"
        
        return result
    
    async def cleanup(self, days: int = 30) -> Dict[str, Any]:
        """
        Clean up old backups and temporary files.
        
        Args:
            days: Keep files newer than this many days
            
        Returns:
            Dictionary with cleanup results
        """
        result = {
            'success': False,
            'timestamp': datetime.utcnow().isoformat(),
            'cutoff_date': (datetime.utcnow() - timedelta(days=days)).isoformat(),
            'deleted_files': [],
            'total_deleted': 0,
            'space_freed': 0
        }
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Clean up old backups
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix='cookies/backups/'
            )
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        # Keep at least 3 most recent backups regardless of age
                        all_backups = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
                        if obj not in all_backups[:3]:
                            self.s3_client.delete_object(
                                Bucket=self.bucket_name,
                                Key=obj['Key']
                            )
                            result['deleted_files'].append(obj['Key'])
                            result['space_freed'] += obj['Size']
            
            # Clean up old archives
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix='cookies/archives/'
            )
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        self.s3_client.delete_object(
                            Bucket=self.bucket_name,
                            Key=obj['Key']
                        )
                        result['deleted_files'].append(obj['Key'])
                        result['space_freed'] += obj['Size']
            
            result['total_deleted'] = len(result['deleted_files'])
            result['success'] = True
            
            self.logger.info(f"Cleanup completed: {result['total_deleted']} files deleted, "
                           f"{result['space_freed']} bytes freed")
        
        except Exception as e:
            result['error'] = f"Cleanup failed: {str(e)}"
        
        return result
    
    # Helper methods
    async def _get_decrypted_cookies(self, key: str) -> Optional[str]:
        """Get and decrypt cookies from S3."""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            encrypted_content = response['Body'].read()
            decrypted_content = self.cipher_suite.decrypt(encrypted_content)
            return decrypted_content.decode('utf-8')
        except Exception:
            return None
    
    async def _parse_cookies(self, content: str) -> List[Dict[str, Any]]:
        """Parse cookie content into structured data."""
        cookies = []
        
        if content.strip().startswith('[') or content.strip().startswith('{'):
            # JSON format
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    cookies = data
                else:
                    cookies = [data]
            except json.JSONDecodeError:
                pass
        else:
            # Netscape format
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        cookies.append({
                            'domain': parts[0],
                            'path': parts[2],
                            'secure': parts[3] == 'TRUE',
                            'expires': int(parts[4]) if parts[4] != '0' else None,
                            'name': parts[5],
                            'value': parts[6]
                        })
        
        return cookies
    
    async def _get_metadata(self) -> Optional[Dict[str, Any]]:
        """Get cookie metadata from S3."""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key='cookies/metadata.json'
            )
            content = response['Body'].read().decode()
            return json.loads(content)
        except Exception:
            return None
    
    async def _save_metadata(self, metadata: Dict[str, Any]) -> bool:
        """Save metadata to S3."""
        try:
            metadata_json = json.dumps(metadata, indent=2)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key='cookies/metadata.json',
                Body=metadata_json.encode(),
                ContentType='application/json',
                ServerSideEncryption='AES256'
            )
            return True
        except Exception:
            return False
    
    async def _send_notification(self, subject: str, message: str) -> bool:
        """Send notification email or webhook."""
        try:
            # This is a placeholder - implement actual notification system
            # Could be email, Slack webhook, SNS, etc.
            self.logger.info(f"NOTIFICATION: {subject} - {message}")
            return True
        except Exception:
            return False
    
    def _format_audit_text(self, report: Dict[str, Any]) -> str:
        """Format audit report as text."""
        lines = [
            f"Cookie Access Audit Report",
            f"=" * 40,
            f"Generated: {report['timestamp']}",
            f"Period: {report['period_start']} to {report['period_end']} ({report['period_days']} days)",
            f"",
            f"Summary:",
            f"  Total Events: {report['summary']['total_events']}",
            f"  Uploads: {report['summary']['uploads']}",
            f"  Downloads: {report['summary']['downloads']}",
            f"  Rotations: {report['summary']['rotations']}",
            f"  Failures: {report['summary']['failures']}",
            f"",
            f"Events:"
        ]
        
        for event in report['events'][-10:]:  # Show last 10 events
            lines.append(f"  {event['timestamp']} - {event['event_name']} by {event['user']}")
        
        return '\n'.join(lines)
    
    def _format_audit_html(self, report: Dict[str, Any]) -> str:
        """Format audit report as HTML."""
        html = f"""
        <html>
        <head><title>Cookie Access Audit Report</title></head>
        <body>
        <h1>Cookie Access Audit Report</h1>
        <p><strong>Generated:</strong> {report['timestamp']}</p>
        <p><strong>Period:</strong> {report['period_days']} days</p>
        
        <h2>Summary</h2>
        <ul>
        <li>Total Events: {report['summary']['total_events']}</li>
        <li>Uploads: {report['summary']['uploads']}</li>
        <li>Downloads: {report['summary']['downloads']}</li>
        </ul>
        
        <h2>Recent Events</h2>
        <table border="1">
        <tr><th>Timestamp</th><th>Event</th><th>User</th></tr>
        """
        
        for event in report['events'][-10:]:
            html += f"<tr><td>{event['timestamp']}</td><td>{event['event_name']}</td><td>{event['user']}</td></tr>"
        
        html += """
        </table>
        </body>
        </html>
        """
        return html


async def main():
    """Main entry point for cookie management tools."""
    parser = argparse.ArgumentParser(
        description="Cookie Management Tools for YouTube Download Service",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Rotate command
    rotate_parser = subparsers.add_parser('rotate', help='Rotate cookies')
    rotate_parser.add_argument('--notify', action='store_true', help='Send notification after rotation')
    rotate_parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    
    # Check expiration command
    expire_parser = subparsers.add_parser('check-expiration', help='Check cookie expiration')
    expire_parser.add_argument('--warn-days', type=int, default=7, help='Days before expiration to warn')
    
    # Health check command
    health_parser = subparsers.add_parser('health-check', help='Perform health check')
    health_parser.add_argument('--detailed', action='store_true', help='Include detailed diagnostics')
    
    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Create manual backup')
    backup_parser.add_argument('--source', default='manual', help='Backup source identifier')
    
    # Restore command
    restore_parser = subparsers.add_parser('restore', help='Restore from backup')
    restore_parser.add_argument('backup_key', help='S3 key of backup to restore')
    restore_parser.add_argument('--confirm', action='store_true', help='Confirm restore operation')
    
    # Audit command
    audit_parser = subparsers.add_parser('audit', help='Generate audit report')
    audit_parser.add_argument('--days', type=int, default=30, help='Days to include in report')
    audit_parser.add_argument('--format', choices=['text', 'json', 'html'], default='text', help='Output format')
    
    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Show performance metrics')
    
    # Schedule command
    schedule_parser = subparsers.add_parser('schedule', help='Set up rotation schedule')
    schedule_parser.add_argument('cron', help='Cron expression (e.g., "0 2 * * 0")')
    schedule_parser.add_argument('--disable', action='store_true', help='Disable schedule')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old files')
    cleanup_parser.add_argument('--days', type=int, default=30, help='Keep files newer than N days')
    
    # Global arguments
    parser.add_argument('--bucket', help='S3 bucket name')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        tools = CookieManagementTools(bucket_name=args.bucket)
        
        if args.command == 'rotate':
            result = await tools.rotate_cookies(notify=args.notify, dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
            return 0 if result['success'] else 1
        
        elif args.command == 'check-expiration':
            result = await tools.check_expiration(warn_days=args.warn_days)
            print(json.dumps(result, indent=2))
            return 0 if not result['needs_attention'] else 1
        
        elif args.command == 'health-check':
            status = await tools.health_check(detailed=args.detailed)
            print(f"Cookie Health Status:")
            print(f"  Active Present: {status.active_present}")
            print(f"  Backup Present: {status.backup_present}")
            print(f"  Cookie Count: {status.cookie_count}")
            print(f"  Expired: {status.expired_count}")
            print(f"  Expiring Soon: {status.expiring_soon_count}")
            print(f"  Domains: {len(status.domains)}")
            
            if status.issues:
                print(f"  Issues: {len(status.issues)}")
                for issue in status.issues:
                    print(f"    - {issue}")
            
            if status.warnings:
                print(f"  Warnings: {len(status.warnings)}")
                for warning in status.warnings:
                    print(f"    - {warning}")
            
            return 0 if not status.issues else 1
        
        elif args.command == 'backup':
            result = await tools.backup_cookies(source=args.source)
            print(json.dumps(result, indent=2))
            return 0 if result['success'] else 1
        
        elif args.command == 'restore':
            result = await tools.restore_cookies(args.backup_key, confirm=args.confirm)
            print(json.dumps(result, indent=2))
            return 0 if result['success'] else 1
        
        elif args.command == 'audit':
            result = await tools.generate_audit_report(days=args.days, format=args.format)
            if 'formatted_output' in result:
                print(result['formatted_output'])
            else:
                print(json.dumps(result, indent=2))
            return 0
        
        elif args.command == 'monitor':
            metrics = await tools.get_performance_metrics()
            print(f"Cookie Performance Metrics:")
            print(f"  Success Rate: {metrics.success_rate:.1f}%")
            print(f"  Total Downloads: {metrics.total_downloads}")
            print(f"  Cookie Failures: {metrics.cookie_failures}")
            print(f"  Performance Grade: {metrics.performance_grade}")
            return 0
        
        elif args.command == 'schedule':
            result = await tools.schedule_rotation(args.cron, enable=not args.disable)
            print(json.dumps(result, indent=2))
            return 0 if result['success'] else 1
        
        elif args.command == 'cleanup':
            result = await tools.cleanup(days=args.days)
            print(json.dumps(result, indent=2))
            return 0 if result['success'] else 1
    
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))