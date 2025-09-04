import asyncio
import json
import logging
from typing import Dict, Set
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.database import DownloadJob
from app.models.download import ProgressMessage, StatusMessage, ErrorMessage, JobProgress, DownloadStatus

logger = logging.getLogger(__name__)

router = APIRouter()


class WebSocketManager:
    """
    WebSocket connection manager for handling real-time progress updates.
    """
    
    def __init__(self):
        # Map of job_id -> set of WebSocket connections
        self.job_connections: Dict[str, Set[WebSocket]] = {}
        # Map of WebSocket -> job_id for cleanup
        self.connection_jobs: Dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket, job_id: str):
        """Connect a WebSocket to a specific job."""
        await websocket.accept()
        
        if job_id not in self.job_connections:
            self.job_connections[job_id] = set()
        
        self.job_connections[job_id].add(websocket)
        self.connection_jobs[websocket] = job_id
        
        logger.info(f"WebSocket connected for job {job_id}")
        
        # Send initial status
        await self.send_initial_status(websocket, job_id)
    
    async def disconnect(self, websocket: WebSocket):
        """Disconnect a WebSocket and clean up."""
        if websocket in self.connection_jobs:
            job_id = self.connection_jobs[websocket]
            
            # Remove from job connections
            if job_id in self.job_connections:
                self.job_connections[job_id].discard(websocket)
                if not self.job_connections[job_id]:
                    del self.job_connections[job_id]
            
            # Remove from connection jobs
            del self.connection_jobs[websocket]
            
            logger.info(f"WebSocket disconnected for job {job_id}")
    
    async def send_progress_update(self, job_id: str, progress: float, status: str):
        """Send progress update to all connections for a job."""
        if job_id not in self.job_connections:
            return
        
        message = ProgressMessage(
            job_id=job_id,
            progress=JobProgress(current=progress, status=status)
        )
        
        await self._broadcast_to_job(job_id, message.dict())
    
    async def send_status_update(self, job_id: str, status: DownloadStatus, message: str):
        """Send status update to all connections for a job."""
        if job_id not in self.job_connections:
            return
        
        status_message = StatusMessage(
            job_id=job_id,
            status=status,
            message=message
        )
        
        await self._broadcast_to_job(job_id, status_message.dict())
    
    async def send_error(self, job_id: str, error: str):
        """Send error message to all connections for a job."""
        if job_id not in self.job_connections:
            return
        
        error_message = ErrorMessage(
            job_id=job_id,
            error=error
        )
        
        await self._broadcast_to_job(job_id, error_message.dict())
    
    async def send_initial_status(self, websocket: WebSocket, job_id: str):
        """Send initial status to a newly connected WebSocket."""
        try:
            # This would require database access, for now send a simple message
            initial_message = {
                "type": "connected",
                "job_id": job_id,
                "message": f"Connected to job {job_id}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await websocket.send_text(json.dumps(initial_message))
            
        except Exception as e:
            logger.error(f"Failed to send initial status: {e}")
    
    async def _broadcast_to_job(self, job_id: str, message_dict: dict):
        """Broadcast a message to all connections for a specific job."""
        if job_id not in self.job_connections:
            return
        
        connections_to_remove = set()
        
        for websocket in self.job_connections[job_id].copy():
            try:
                await websocket.send_text(json.dumps(message_dict))
            except Exception as e:
                logger.error(f"Failed to send message to WebSocket: {e}")
                connections_to_remove.add(websocket)
        
        # Clean up failed connections
        for websocket in connections_to_remove:
            await self.disconnect(websocket)


# Global WebSocket manager instance
ws_manager = WebSocketManager()


@router.websocket("/progress/{job_id}")
async def websocket_progress_endpoint(
    websocket: WebSocket, 
    job_id: str
):
    """
    WebSocket endpoint for receiving real-time progress updates for a download job.
    
    Args:
        job_id: The unique identifier of the download job to monitor
    
    The WebSocket will receive JSON messages with the following structure:
    
    Progress updates:
    {
        "type": "progress",
        "job_id": "string",
        "progress": {
            "current": float,
            "total": 100,
            "status": "string"
        },
        "timestamp": "ISO datetime"
    }
    
    Status updates:
    {
        "type": "status", 
        "job_id": "string",
        "status": "queued|processing|completed|failed",
        "message": "string",
        "timestamp": "ISO datetime"
    }
    
    Error messages:
    {
        "type": "error",
        "job_id": "string", 
        "error": "string",
        "timestamp": "ISO datetime"
    }
    """
    try:
        await ws_manager.connect(websocket, job_id)
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client (optional)
                message = await websocket.receive_text()
                
                # Handle client messages if needed
                try:
                    data = json.loads(message)
                    if data.get("type") == "ping":
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }))
                except json.JSONDecodeError:
                    logger.warning(f"Received invalid JSON from WebSocket: {message}")
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket communication: {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    
    finally:
        await ws_manager.disconnect(websocket)


# Helper function to send progress updates from other parts of the application
async def notify_progress(job_id: str, progress: float, status: str):
    """
    Send progress notification to WebSocket clients.
    
    This function can be called from the download service or Celery tasks
    to notify connected clients about progress updates.
    """
    await ws_manager.send_progress_update(job_id, progress, status)


async def notify_status_change(job_id: str, status: DownloadStatus, message: str):
    """
    Send status change notification to WebSocket clients.
    
    This function can be called when a job status changes.
    """
    await ws_manager.send_status_update(job_id, status, message)


async def notify_error(job_id: str, error: str):
    """
    Send error notification to WebSocket clients.
    
    This function can be called when an error occurs during download.
    """
    await ws_manager.send_error(job_id, error)


# Export the WebSocket manager for use in other modules
__all__ = ["router", "ws_manager", "notify_progress", "notify_status_change", "notify_error"]