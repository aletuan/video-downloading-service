import asyncio
from datetime import datetime
from celery import Celery
from app.core.config import settings
from app.core.database import get_db_session
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

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

@celery_app.task(bind=True, name='process_download')
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
    
    async def async_download():
        """Async download function."""
        downloader = YouTubeDownloader()
        
        try:
            # Update database job status to processing
            async with get_db_session() as session:
                stmt = update(DownloadJob).where(
                    DownloadJob.id == job_id
                ).values(
                    status='processing',
                    started_at=datetime.utcnow()
                )
                await session.execute(stmt)
                await session.commit()
            
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
            
            # Update database with results
            async with get_db_session() as session:
                metadata = result.get('metadata', {})
                
                stmt = update(DownloadJob).where(
                    DownloadJob.id == job_id
                ).values(
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
                await session.execute(stmt)
                await session.commit()
            
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
            
            # Update database job status to failed
            try:
                async with get_db_session() as session:
                    stmt = update(DownloadJob).where(
                        DownloadJob.id == job_id
                    ).values(
                        status='failed',
                        error_message=str(e),
                        retry_count=DownloadJob.retry_count + 1
                    )
                    await session.execute(stmt)
                    await session.commit()
            except Exception as db_error:
                logger.error(f"Failed to update job status in database: {db_error}")
            
            raise e
    
    try:
        # Run the async download in the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(async_download())
        finally:
            loop.close()
            
    except Exception as exc:
        # Update task state to failure
        self.update_state(
            state='FAILURE',
            meta={
                'current': 0,
                'total': 100,
                'status': f'Download failed: {str(exc)}',
                'job_id': job_id,
                'error': str(exc)
            }
        )
        raise exc


@celery_app.task
def health_check():
    """Simple health check task for Celery workers."""
    return {'status': 'healthy', 'message': 'Celery worker is running'}


# Make the Celery app discoverable
if __name__ == '__main__':
    celery_app.start()