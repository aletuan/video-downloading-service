from datetime import datetime
from typing import List, Optional
import uuid
import logging

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.database import DownloadJob
from app.models.download import (
    DownloadRequest, DownloadResponse, DownloadJobStatus, DownloadJobList,
    VideoInfo, ErrorResponse, VideoMetadata, JobProgress,
    DownloadStatus, VideoQuality, OutputFormat
)
from app.services.downloader import YouTubeDownloader
from app.tasks.download_tasks import process_download

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/download",
    response_model=DownloadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Start YouTube video download",
    description="Initiate a new YouTube video download job with specified options"
)
async def start_download(
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Start a new YouTube video download.
    
    This endpoint validates the YouTube URL, creates a new download job,
    and queues it for background processing.
    """
    try:
        # Validate YouTube URL
        downloader = YouTubeDownloader()
        if not downloader.is_valid_youtube_url(str(request.url)):
            raise HTTPException(
                status_code=400,
                detail="Invalid YouTube URL provided"
            )
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Create database record
        download_job = DownloadJob(
            id=job_id,
            url=str(request.url),
            status=DownloadStatus.QUEUED,
            quality=request.quality.value,
            include_transcription=request.include_transcription,
            audio_only=request.audio_only,
            output_format=request.output_format.value,
            subtitle_languages=",".join(request.subtitle_languages),
            created_at=datetime.utcnow()
        )
        
        db.add(download_job)
        await db.commit()
        await db.refresh(download_job)
        
        # Queue background task
        download_options = {
            "quality": request.quality.value,
            "output_format": request.output_format.value,
            "audio_only": request.audio_only,
            "include_transcription": request.include_transcription,
            "subtitle_languages": request.subtitle_languages
        }
        
        # Start Celery task
        task = process_download.delay(job_id, str(request.url), download_options)
        
        logger.info(f"Started download job {job_id} for URL: {request.url}")
        
        return DownloadResponse(
            job_id=job_id,
            status=DownloadStatus.QUEUED,
            message="Download job queued successfully",
            estimated_time=300  # Estimate 5 minutes
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start download: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start download: {str(e)}"
        )


@router.get(
    "/status/{job_id}",
    response_model=DownloadJobStatus,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Get download job status",
    description="Retrieve the current status and progress of a download job"
)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the status of a specific download job.
    
    Returns detailed information about the job including progress,
    file paths, metadata, and any error messages.
    """
    try:
        # Query job from database
        stmt = select(DownloadJob).where(DownloadJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail=f"Download job {job_id} not found"
            )
        
        # Convert to response model
        return DownloadJobStatus(
            job_id=str(job.id),
            url=job.url,
            status=DownloadStatus(job.status),
            progress=JobProgress(
                current=job.progress or 0,
                status=f"Status: {job.status}"
            ),
            metadata=VideoMetadata(
                title=job.title,
                duration=job.duration,
                uploader=job.channel_name,
                view_count=job.view_count,
                like_count=job.like_count
            ) if job.title else None,
            video_path=job.video_path,
            thumbnail_path=job.thumbnail_path,
            transcription_path=job.transcription_path,
            file_size=job.file_size,
            file_size_formatted=job.file_size_formatted,
            duration_formatted=job.duration_formatted,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            can_retry=job.can_retry
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status for {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job status: {str(e)}"
        )


@router.get(
    "/jobs",
    response_model=DownloadJobList,
    summary="List download jobs",
    description="Get a paginated list of download jobs with filtering options"
)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Jobs per page"),
    status: Optional[DownloadStatus] = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db)
):
    """
    List download jobs with pagination and filtering.
    
    Returns a paginated list of download jobs, optionally filtered by status.
    """
    try:
        # Build query
        stmt = select(DownloadJob).order_by(desc(DownloadJob.created_at))
        
        if status:
            stmt = stmt.where(DownloadJob.status == status.value)
        
        # Get total count
        count_stmt = select(func.count(DownloadJob.id))
        if status:
            count_stmt = count_stmt.where(DownloadJob.status == status.value)
        
        total_result = await db.execute(count_stmt)
        total = total_result.scalar()
        
        # Calculate pagination
        offset = (page - 1) * per_page
        total_pages = (total + per_page - 1) // per_page
        
        # Get paginated results
        stmt = stmt.offset(offset).limit(per_page)
        result = await db.execute(stmt)
        jobs = result.scalars().all()
        
        # Convert to response models
        job_list = []
        for job in jobs:
            job_status = DownloadJobStatus(
                job_id=str(job.id),
                url=job.url,
                status=DownloadStatus(job.status),
                progress=JobProgress(
                    current=job.progress or 0,
                    status=f"Status: {job.status}"
                ),
                metadata=VideoMetadata(
                    title=job.title,
                    duration=job.duration,
                    uploader=job.channel_name,
                    view_count=job.view_count,
                    like_count=job.like_count
                ) if job.title else None,
                video_path=job.video_path,
                thumbnail_path=job.thumbnail_path,
                transcription_path=job.transcription_path,
                file_size=job.file_size,
                file_size_formatted=job.file_size_formatted,
                duration_formatted=job.duration_formatted,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                error_message=job.error_message,
                retry_count=job.retry_count,
                max_retries=job.max_retries,
                can_retry=job.can_retry
            )
            job_list.append(job_status)
        
        return DownloadJobList(
            jobs=job_list,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=max(total_pages, 1)
        )
        
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list jobs: {str(e)}"
        )


@router.get(
    "/info",
    response_model=VideoInfo,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid URL"},
        500: {"model": ErrorResponse, "description": "Extraction failed"}
    },
    summary="Extract video information",
    description="Extract metadata and available formats from a YouTube video without downloading"
)
async def get_video_info(
    url: str = Query(..., description="YouTube video URL"),
):
    """
    Extract video information without downloading.
    
    This endpoint extracts video metadata, available formats, and
    recommended download settings without starting a download.
    """
    try:
        # Validate URL
        downloader = YouTubeDownloader()
        if not downloader.is_valid_youtube_url(url):
            raise HTTPException(
                status_code=400,
                detail="Invalid YouTube URL provided"
            )
        
        # Extract video information
        metadata = await downloader.extract_info(url)
        available_formats = await downloader.get_available_formats(url)
        
        # Determine recommended quality
        recommended_quality = "720p"
        if available_formats:
            # Find best quality under 1080p for recommendation
            qualities = [fmt.get('quality', '').replace('p', '') for fmt in available_formats if fmt.get('quality', '').endswith('p')]
            numeric_qualities = []
            for q in qualities:
                try:
                    numeric_qualities.append(int(q))
                except (ValueError, TypeError):
                    continue
            
            if numeric_qualities:
                # Recommend highest quality <= 1080p
                suitable_qualities = [q for q in numeric_qualities if q <= 1080]
                if suitable_qualities:
                    recommended_quality = f"{max(suitable_qualities)}p"
                else:
                    recommended_quality = f"{min(numeric_qualities)}p"
        
        return VideoInfo(
            url=url,
            metadata=VideoMetadata(**metadata),
            available_formats=available_formats,
            recommended_quality=recommended_quality
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extract video info from {url}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract video information: {str(e)}"
        )


@router.post(
    "/retry/{job_id}",
    response_model=DownloadResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        400: {"model": ErrorResponse, "description": "Job cannot be retried"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Retry failed download",
    description="Retry a failed download job"
)
async def retry_download(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Retry a failed download job.
    
    This endpoint allows retrying a failed download job if it hasn't
    exceeded the maximum retry count.
    """
    try:
        # Get job from database
        stmt = select(DownloadJob).where(DownloadJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail=f"Download job {job_id} not found"
            )
        
        if not job.can_retry:
            raise HTTPException(
                status_code=400,
                detail=f"Job {job_id} cannot be retried (status: {job.status}, retries: {job.retry_count}/{job.max_retries})"
            )
        
        # Reset job status
        job.status = DownloadStatus.QUEUED
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        job.progress = 0.0
        
        await db.commit()
        
        # Queue background task
        download_options = {
            "quality": job.quality,
            "output_format": job.output_format,
            "audio_only": job.audio_only,
            "include_transcription": job.include_transcription,
            "subtitle_languages": job.subtitle_languages.split(",") if job.subtitle_languages else ["en"]
        }
        
        # Start Celery task
        task = process_download.delay(job_id, job.url, download_options)
        
        logger.info(f"Retried download job {job_id}")
        
        return DownloadResponse(
            job_id=job_id,
            status=DownloadStatus.QUEUED,
            message="Download job queued for retry",
            estimated_time=300
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry job {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retry download: {str(e)}"
        )