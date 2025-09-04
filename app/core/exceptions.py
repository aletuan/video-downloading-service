"""
Custom exceptions for the YouTube Video Download Service.

This module provides serializable exceptions that can be properly handled
across async/sync boundaries and Celery task processing.
"""

import traceback
from typing import Dict, Any, Optional


class SerializableTaskException(Exception):
    """
    Exception that can be properly serialized across Celery message queues.
    
    This exception addresses the common issue where async exceptions don't
    serialize properly in Celery, leading to "Exception information must 
    include the exception type" errors.
    """
    
    def __init__(
        self, 
        message: str, 
        original_exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        capture_traceback: bool = True
    ):
        super().__init__(message)
        self.message = message
        self.original_type = original_exception.__class__.__name__ if original_exception else None
        self.original_message = str(original_exception) if original_exception else None
        self.context = context or {}
        
        # Capture traceback if requested and exception exists
        if capture_traceback and original_exception:
            self.traceback_str = traceback.format_exc()
        else:
            self.traceback_str = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for Celery serialization."""
        return {
            'message': self.message,
            'original_type': self.original_type,
            'original_message': self.original_message,
            'context': self.context,
            'traceback': self.traceback_str,
            'serializable': True  # Flag to identify this as a serializable exception
        }
    
    def __str__(self) -> str:
        """String representation of the exception."""
        if self.original_type:
            return f"{self.message} (Original: {self.original_type}: {self.original_message})"
        return self.message
    
    def __repr__(self) -> str:
        """Detailed representation of the exception."""
        return (
            f"SerializableTaskException("
            f"message='{self.message}', "
            f"original_type='{self.original_type}', "
            f"context={self.context})"
        )


class DownloadServiceException(SerializableTaskException):
    """Exception specific to YouTube download operations."""
    
    def __init__(
        self, 
        message: str, 
        job_id: Optional[str] = None,
        url: Optional[str] = None,
        original_exception: Optional[Exception] = None,
        stage: Optional[str] = None
    ):
        context = {}
        if job_id:
            context['job_id'] = job_id
        if url:
            context['url'] = url
        if stage:
            context['stage'] = stage
            
        super().__init__(
            message=message,
            original_exception=original_exception,
            context=context
        )
        
        self.job_id = job_id
        self.url = url
        self.stage = stage


class DatabaseOperationException(SerializableTaskException):
    """Exception for database operations in Celery tasks."""
    
    def __init__(
        self, 
        message: str,
        operation: Optional[str] = None,
        table: Optional[str] = None,
        original_exception: Optional[Exception] = None
    ):
        context = {}
        if operation:
            context['operation'] = operation
        if table:
            context['table'] = table
            
        super().__init__(
            message=message,
            original_exception=original_exception,
            context=context
        )
        
        self.operation = operation
        self.table = table


class TaskConfigurationException(SerializableTaskException):
    """Exception for task configuration and setup issues."""
    
    def __init__(
        self, 
        message: str,
        task_name: Optional[str] = None,
        configuration_item: Optional[str] = None,
        original_exception: Optional[Exception] = None
    ):
        context = {}
        if task_name:
            context['task_name'] = task_name
        if configuration_item:
            context['configuration_item'] = configuration_item
            
        super().__init__(
            message=message,
            original_exception=original_exception,
            context=context
        )
        
        self.task_name = task_name
        self.configuration_item = configuration_item


def wrap_exception(
    original_exception: Exception, 
    context_message: str,
    **context_data
) -> SerializableTaskException:
    """
    Utility function to wrap any exception as a SerializableTaskException.
    
    Args:
        original_exception: The original exception to wrap
        context_message: Descriptive message about the context
        **context_data: Additional context data to include
    
    Returns:
        SerializableTaskException with the original exception wrapped
    """
    return SerializableTaskException(
        message=context_message,
        original_exception=original_exception,
        context=context_data
    )


def safe_str(obj: Any) -> str:
    """
    Safely convert any object to string, handling potential encoding issues.
    
    Args:
        obj: Object to convert to string
        
    Returns:
        String representation of the object
    """
    try:
        return str(obj)
    except (UnicodeEncodeError, UnicodeDecodeError):
        return repr(obj)
    except Exception:
        return f"<Error converting {type(obj).__name__} to string>"