import asyncio
from datetime import datetime
from celery import Celery
from celery.signals import worker_init, worker_shutdown
from app.core.config import settings
from app.core.database import get_sync_db_session, init_sync_database_only, close_sync_database
from app.core.exceptions import (
    SerializableTaskException, 
    DownloadServiceException, 
    DatabaseOperationException,
    wrap_exception
)
from app.services.downloader import YouTubeDownloader
from app.models.database import DownloadJob
from sqlalchemy import select, update
import logging

logger = logging.getLogger(__name__)

# Create Celery instance
celery_app = Celery(
    "youtube_service",
    broker=settings.redis_url,
    backend=settings.redis_url
)

# Enhanced Celery configuration for better async/exception handling
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Error handling
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
    result_expires=3600,
    
    # Retry configuration
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    
    # Connection handling
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Tracking
    task_track_started=True,
    
    # Pool configuration
    worker_pool_restarts=True,
)


# Worker lifecycle hooks
@worker_init.connect
def init_worker(**kwargs):
    """Initialize Celery worker with sync database connection."""
    logger.info("Initializing Celery worker with sync database")
    try:
        init_sync_database_only()
        logger.info("Celery worker initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Celery worker: {e}")
        raise


@worker_shutdown.connect
def shutdown_worker(**kwargs):
    """Cleanup Celery worker resources."""
    logger.info("Shutting down Celery worker")
    try:
        close_sync_database()
        logger.info("Celery worker shutdown complete")
    except Exception as e:
        logger.error(f"Error during Celery worker shutdown: {e}")

@celery_app.task(bind=True, name='process_download', autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def process_download(self, job_id: str, url: str, options: dict):
    """
    Background task to process YouTube video downloads using the YouTubeDownloader service.
    
    Args:
        job_id: Unique job identifier
        url: YouTube video URL to download
        options: Download options dict containing:
            - quality: Video quality (best, 720p, 1080p, etc.)
            - output_format: Output format (mp4, mkv, webm)
            - audio_only: Boolean for audio-only download
            - include_transcription: Boolean for subtitle extraction
            - subtitle_languages: List of subtitle languages
    """
    
    def progress_callback(progress: float, status: str):
        """Callback to update Celery task progress."""
        self.update_state(
            state='PROGRESS',
            meta={
                'current': progress,
                'total': 100,
                'status': status,
                'job_id': job_id
            }
        )
    
    def update_job_status_sync(status: str, **kwargs):
        """Update job status using sync database operations."""
        try:
            with get_sync_db_session() as session:
                update_data = {'status': status}
                update_data.update(kwargs)
                
                stmt = update(DownloadJob).where(
                    DownloadJob.id == job_id
                ).values(**update_data)
                
                session.execute(stmt)
                session.commit()
                logger.debug(f"Job {job_id} status updated to {status}")
                
        except Exception as e:
            raise DatabaseOperationException(
                message=f"Failed to update job {job_id} status to {status}",
                operation="update",
                table="DownloadJob",
                original_exception=e
            )
    
    async def async_download():
        """Async download function with proper error handling."""
        downloader = YouTubeDownloader()
        
        try:
            # Update database job status to processing using sync operation
            update_job_status_sync(
                status='processing',
                started_at=datetime.utcnow()
            )
            
            # Extract download options
            quality = options.get('quality', 'best')
            output_format = options.get('output_format', 'mp4')
            audio_only = options.get('audio_only', False)
            include_transcription = options.get('include_transcription', True)
            subtitle_languages = options.get('subtitle_languages', ['en'])
            
            # Start download
            result = await downloader.download_video(
                url=url,
                job_id=job_id,
                quality=quality,
                output_format=output_format,
                audio_only=audio_only,
                include_transcription=include_transcription,
                subtitle_languages=subtitle_languages,
                progress_callback=progress_callback
            )
            
            # Update database with results using sync operation
            metadata = result.get('metadata', {})
            update_job_status_sync(
                status='completed',
                completed_at=datetime.utcnow(),
                title=metadata.get('title'),
                duration=metadata.get('duration'),
                channel_name=metadata.get('uploader'),
                view_count=metadata.get('view_count'),
                like_count=metadata.get('like_count'),
                video_path=result.get('video_path'),
                transcription_path=result.get('subtitle_paths', [None])[0],
                thumbnail_path=result.get('thumbnail_path'),
                file_size=result.get('file_size', 0),
                progress=100.0
            )
            
            return {
                'current': 100,
                'total': 100,
                'status': 'Download completed successfully!',
                'result': {
                    'job_id': job_id,
                    'url': url,
                    'title': metadata.get('title'),
                    'video_path': result.get('video_path'),
                    'video_url': result.get('video_url'),
                    'audio_path': result.get('audio_path'),
                    'audio_url': result.get('audio_url'),
                    'thumbnail_path': result.get('thumbnail_path'),
                    'thumbnail_url': result.get('thumbnail_url'),
                    'subtitle_paths': result.get('subtitle_paths', []),
                    'file_size': result.get('file_size', 0),
                    'metadata': metadata
                }
            }
            
        except Exception as e:
            logger.error(f"Download failed for job {job_id}: {e}")
            
            # Update database job status to failed using sync operation
            try:
                update_job_status_sync(
                    status='failed',
                    error_message=str(e),
                    retry_count=DownloadJob.retry_count + 1
                )
            except Exception as db_error:
                logger.error(f"Failed to update job status in database: {db_error}")
            
            # Raise as DownloadServiceException for proper serialization
            raise DownloadServiceException(
                message=f"Download failed for job {job_id}",
                job_id=job_id,
                url=url,
                original_exception=e,
                stage="download"
            )
    
    try:
        # Use asyncio.run() for cleaner event loop management
        # This creates a new event loop, runs the coroutine, and cleans up properly
        return asyncio.run(async_download())
            
    except (SerializableTaskException, DownloadServiceException, DatabaseOperationException) as exc:
        # Already properly wrapped exceptions - update state and re-raise
        logger.error(f"Task failed with serializable exception: {exc}")
        
        self.update_state(
            state='FAILURE',
            meta=exc.to_dict()
        )
        raise exc
        
    except Exception as exc:
        # Wrap unexpected exceptions for proper serialization
        logger.error(f"Task failed with unexpected exception: {exc}")
        
        wrapped_exception = wrap_exception(
            original_exception=exc,
            context_message=f"Unexpected error in download task for job {job_id}",
            job_id=job_id,
            url=url,
            task_name="process_download"
        )
        
        self.update_state(
            state='FAILURE',
            meta=wrapped_exception.to_dict()
        )
        raise wrapped_exception


@celery_app.task
def health_check():
    """Comprehensive health check task for Celery workers."""
    try:
        from app.core.database import check_sync_database_connection
        
        # Check database connectivity
        db_healthy = check_sync_database_connection()
        
        return {
            'status': 'healthy' if db_healthy else 'degraded',
            'message': 'Celery worker is running',
            'database_connection': db_healthy,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'message': f'Health check failed: {str(e)}',
            'timestamp': datetime.utcnow().isoformat()
        }


# Export celery_app for worker discovery
__all__ = ['celery_app', 'process_download', 'health_check']

# Make the Celery app discoverable
if __name__ == '__main__':
    celery_app.start()