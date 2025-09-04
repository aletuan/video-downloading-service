import asyncio
import logging
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from app.core.config import settings
# Removed unused import - using direct SQLAlchemy session creation instead
from app.models.database import DownloadJob
from app.services.downloader import create_youtube_downloader, DownloadOptions
# Removed unused OutputFormat import

# Create Celery instance
celery_app = Celery(
    "youtube_service",
    broker=settings.redis_url,
    backend=settings.redis_url
)

logger = logging.getLogger(__name__)

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
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
)

async def _update_job_status(job_id: str, **updates):
    """Update DownloadJob in database with new status/metadata."""
    try:
        # Create synchronous database session for Celery worker
        engine = create_engine(settings.database_url.replace('+asyncpg', ''))
        SessionLocal = sessionmaker(bind=engine)
        
        with SessionLocal() as session:
            job = session.query(DownloadJob).filter(DownloadJob.id == job_id).first()
            if job:
                for key, value in updates.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                session.commit()
                logger.debug(f"Updated job {job_id}: {updates}")
            else:
                logger.warning(f"Job {job_id} not found in database")
                
    except Exception as e:
        logger.error(f"Failed to update job {job_id}: {str(e)}")


def _create_progress_callback(task_instance, job_id: str):
    """Create progress callback for yt-dlp integration."""
    
    def progress_hook(d):
        """Progress callback for yt-dlp downloads."""
        try:
            if d['status'] == 'downloading':
                # Calculate percentage
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                
                if total_bytes > 0:
                    percentage = min(100, int((downloaded_bytes / total_bytes) * 100))
                else:
                    percentage = 0
                
                # Update Celery task state
                task_instance.update_state(
                    state='PROGRESS',
                    meta={
                        'current': percentage,
                        'total': 100,
                        'status': f'Downloading... {percentage}%',
                        'downloaded_bytes': downloaded_bytes,
                        'total_bytes': total_bytes,
                        'speed': d.get('speed'),
                        'eta': d.get('eta')
                    }
                )
                
                # Update database
                asyncio.run(_update_job_status(
                    job_id,
                    progress=percentage / 100.0,
                    status='processing'
                ))
                
            elif d['status'] == 'finished':
                task_instance.update_state(
                    state='PROGRESS',
                    meta={
                        'current': 90,
                        'total': 100,
                        'status': 'Processing completed file...'
                    }
                )
                
        except Exception as e:
            logger.error(f"Progress callback error: {str(e)}")
    
    return progress_hook


@celery_app.task(bind=True, name='process_download', autoretry_for=(Exception,))
def process_download(self, job_id: str, url: str, options: dict):
    """
    Background task to process YouTube video downloads using yt-dlp.
    
    Args:
        job_id: Unique identifier for the download job
        url: YouTube video URL to download
        options: Download options dictionary
        
    Returns:
        Dictionary with download results and file paths
    """
    logger.info(f"Starting download job {job_id} for URL: {url}")
    
    try:
        # Update initial status
        self.update_state(
            state='PROGRESS',
            meta={'current': 5, 'total': 100, 'status': 'Initializing download...'}
        )
        
        asyncio.run(_update_job_status(
            job_id,
            status='processing',
            progress=0.05,
            started_at=datetime.now(timezone.utc)
        ))
        
        # Parse download options
        download_options = DownloadOptions(
            quality=options.get('quality', 'best'),
            include_transcription=options.get('include_transcription', True),
            audio_only=options.get('audio_only', False),
            output_format=options.get('output_format', 'mp4'),
            subtitle_languages=options.get('subtitle_languages', ['en']),
            extract_thumbnail=options.get('extract_thumbnail', True)
        )
        
        # Create downloader instance
        downloader = create_youtube_downloader()
        
        # Create progress callback
        progress_callback = _create_progress_callback(self, job_id)
        
        # Start download process
        self.update_state(
            state='PROGRESS',
            meta={'current': 10, 'total': 100, 'status': 'Extracting video metadata...'}
        )
        
        # Run the download process
        download_result = asyncio.run(
            downloader.download_video(
                job_id=job_id,
                url=url,
                options=download_options,
                progress_callback=progress_callback
            )
        )
        
        if not download_result.success:
            raise Exception(download_result.error_message or "Download failed")
        
        # Update progress - post-processing
        self.update_state(
            state='PROGRESS',
            meta={'current': 95, 'total': 100, 'status': 'Finalizing download...'}
        )
        
        # Update database with final results
        asyncio.run(_update_job_status(
            job_id,
            status='completed',
            progress=1.0,
            completed_at=datetime.now(timezone.utc),
            title=download_result.metadata.title if download_result.metadata else None,
            duration=download_result.metadata.duration if download_result.metadata else None,
            channel_name=download_result.metadata.channel_name if download_result.metadata else None,
            upload_date=download_result.metadata.upload_date if download_result.metadata else None,
            view_count=download_result.metadata.view_count if download_result.metadata else None,
            like_count=download_result.metadata.like_count if download_result.metadata else None,
            video_path=download_result.video_path,
            transcription_path=download_result.transcription_files[0].file_path if download_result.transcription_files else None,
            thumbnail_path=download_result.thumbnail_path
        ))
        
        # Prepare transcription file info
        transcription_info = []
        for tf in download_result.transcription_files:
            transcription_info.append({
                'language': tf.language,
                'format': tf.format,
                'file_path': tf.file_path,
                'is_auto_generated': tf.is_auto_generated
            })
        
        # Complete successfully
        result = {
            'current': 100,
            'total': 100,
            'status': 'Download completed successfully!',
            'result': {
                'job_id': job_id,
                'url': url,
                'video_path': download_result.video_path,
                'transcription_files': transcription_info,
                'thumbnail_path': download_result.thumbnail_path,
                'metadata': {
                    'title': download_result.metadata.title if download_result.metadata else None,
                    'duration': download_result.metadata.duration if download_result.metadata else None,
                    'channel_name': download_result.metadata.channel_name if download_result.metadata else None,
                    'view_count': download_result.metadata.view_count if download_result.metadata else None
                } if download_result.metadata else None
            }
        }
        
        logger.info(f"Successfully completed download job {job_id}")
        return result
        
    except Exception as exc:
        logger.error(f"Download job {job_id} failed: {str(exc)}")
        
        # Update database with failure
        try:
            asyncio.run(_update_job_status(
                job_id,
                status='failed',
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc)
            ))
        except Exception as db_exc:
            logger.error(f"Failed to update job status in DB: {str(db_exc)}")
        
        # Update task state
        self.update_state(
            state='FAILURE',
            meta={
                'current': 0,
                'total': 100,
                'status': f'Download failed: {str(exc)}',
                'error': str(exc)
            }
        )
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying download job {job_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        
        raise exc


@celery_app.task
def health_check():
    """Simple health check task for Celery workers."""
    return {'status': 'healthy', 'message': 'Celery worker is running'}


# Make the Celery app discoverable
if __name__ == '__main__':
    celery_app.start()