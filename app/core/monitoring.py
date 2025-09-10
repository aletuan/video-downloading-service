"""
Monitoring and alerting functionality for cookie management and system health.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


@dataclass
class MetricCounter:
    """Thread-safe metric counter for tracking events."""
    count: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def increment(self):
        """Increment the counter."""
        self.count += 1
        self.last_updated = datetime.utcnow()
    
    def reset(self):
        """Reset the counter."""
        self.count = 0
        self.last_updated = datetime.utcnow()


@dataclass 
class FailureEvent:
    """Represents a failure event for tracking."""
    timestamp: datetime
    error_type: str
    error_message: str
    context: Dict[str, Any] = field(default_factory=dict)


class CookieFailureMonitor:
    """Monitor and track cookie-related failures and metrics."""
    
    def __init__(self, max_events: int = 100):
        self.max_events = max_events
        self.failure_events: deque = deque(maxlen=max_events)
        self.metrics = {
            'cookie_download_failures': MetricCounter(),
            'cookie_validation_failures': MetricCounter(),
            'cookie_decryption_failures': MetricCounter(),
            'cookie_s3_access_failures': MetricCounter(),
            'cookie_rotation_failures': MetricCounter(),
            'yt_dlp_cookie_failures': MetricCounter(),
        }
        self._alerts_sent = defaultdict(lambda: datetime.min)
        self._lock = asyncio.Lock()
    
    async def record_failure(self, failure_type: str, error: Exception, context: Dict[str, Any] = None):
        """Record a cookie-related failure event."""
        async with self._lock:
            # Record the failure event
            event = FailureEvent(
                timestamp=datetime.utcnow(),
                error_type=type(error).__name__,
                error_message=str(error),
                context=context or {}
            )
            self.failure_events.append(event)
            
            # Increment relevant metric
            metric_key = f'cookie_{failure_type}_failures'
            if metric_key in self.metrics:
                self.metrics[metric_key].increment()
                logger.warning(f"Cookie failure recorded: {failure_type} - {error}")
            
            # Check if alert threshold is reached
            await self._check_alert_thresholds(failure_type)
    
    async def _check_alert_thresholds(self, failure_type: str):
        """Check if failure rate exceeds alert thresholds."""
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        
        # Count failures in the last hour
        recent_failures = [
            event for event in self.failure_events 
            if event.timestamp > one_hour_ago and failure_type in event.error_message.lower()
        ]
        
        failure_count = len(recent_failures)
        
        # Alert thresholds
        thresholds = {
            'download': 5,      # 5 download failures per hour
            'validation': 10,   # 10 validation failures per hour
            'decryption': 3,    # 3 decryption failures per hour
            's3_access': 5,     # 5 S3 access failures per hour
            'rotation': 2,      # 2 rotation failures per hour
            'yt_dlp': 10,       # 10 yt-dlp cookie failures per hour
        }
        
        threshold = thresholds.get(failure_type, 5)
        
        # Send alert if threshold exceeded and not recently alerted
        last_alert = self._alerts_sent[failure_type]
        if failure_count >= threshold and (now - last_alert) > timedelta(hours=1):
            await self._send_alert(failure_type, failure_count, recent_failures)
            self._alerts_sent[failure_type] = now
    
    async def _send_alert(self, failure_type: str, count: int, events: List[FailureEvent]):
        """Send alert for high failure rate (placeholder implementation)."""
        alert_message = (
            f"COOKIE ALERT: High failure rate detected\n"
            f"Type: {failure_type}\n"
            f"Count: {count} failures in the last hour\n"
            f"Latest error: {events[-1].error_message if events else 'N/A'}"
        )
        
        logger.critical(alert_message)
        
        # TODO: Integrate with actual alerting system (SNS, email, Slack, etc.)
        # This is a placeholder for actual alert implementation
    
    async def get_failure_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get failure statistics for the specified time period."""
        async with self._lock:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            recent_events = [
                event for event in self.failure_events 
                if event.timestamp > cutoff_time
            ]
            
            # Count failures by type
            failure_counts = defaultdict(int)
            for event in recent_events:
                failure_counts[event.error_type] += 1
            
            return {
                "time_period_hours": hours,
                "total_failures": len(recent_events),
                "failure_by_type": dict(failure_counts),
                "current_metrics": {
                    name: {"count": metric.count, "last_updated": metric.last_updated}
                    for name, metric in self.metrics.items()
                },
                "recent_events": [
                    {
                        "timestamp": event.timestamp.isoformat(),
                        "error_type": event.error_type,
                        "error_message": event.error_message[:200],  # Truncate long messages
                        "context": event.context
                    }
                    for event in list(recent_events)[-10:]  # Last 10 events
                ]
            }
    
    async def reset_metrics(self):
        """Reset all metrics counters."""
        async with self._lock:
            for metric in self.metrics.values():
                metric.reset()
            logger.info("Cookie failure metrics reset")


class SystemHealthMonitor:
    """Monitor overall system health including cookie management."""
    
    def __init__(self):
        self.cookie_monitor = CookieFailureMonitor()
        self.health_checks = {
            'last_database_check': None,
            'last_storage_check': None,
            'last_cookie_check': None,
            'last_full_check': None,
        }
    
    async def record_cookie_failure(self, failure_type: str, error: Exception, context: Dict[str, Any] = None):
        """Record a cookie-related failure."""
        await self.cookie_monitor.record_failure(failure_type, error, context)
    
    async def update_health_check(self, check_type: str, status: str, details: Dict[str, Any] = None):
        """Update health check status."""
        self.health_checks[f'last_{check_type}_check'] = {
            'timestamp': datetime.utcnow(),
            'status': status,
            'details': details or {}
        }
    
    async def get_system_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive system health summary."""
        cookie_stats = await self.cookie_monitor.get_failure_statistics()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cookie_management": {
                "failure_statistics": cookie_stats,
                "status": "healthy" if cookie_stats["total_failures"] < 10 else "degraded"
            },
            "health_checks": self.health_checks,
            "alerts": {
                "recent_alerts": len([
                    alert_time for alert_time in self.cookie_monitor._alerts_sent.values()
                    if (datetime.utcnow() - alert_time) < timedelta(hours=24)
                ])
            }
        }


# Global monitoring instance
system_monitor = SystemHealthMonitor()


# Convenience functions for easy usage
async def record_cookie_failure(failure_type: str, error: Exception, context: Dict[str, Any] = None):
    """Record a cookie-related failure (convenience function)."""
    await system_monitor.record_cookie_failure(failure_type, error, context)


async def get_cookie_failure_stats(hours: int = 24) -> Dict[str, Any]:
    """Get cookie failure statistics (convenience function)."""
    return await system_monitor.cookie_monitor.get_failure_statistics(hours)


async def get_system_health() -> Dict[str, Any]:
    """Get system health summary (convenience function)."""
    return await system_monitor.get_system_health_summary()