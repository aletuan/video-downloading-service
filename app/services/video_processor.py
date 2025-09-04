"""
Video Processor Service

FFmpeg integration for video/audio processing including:
- Format conversion
- Quality adjustment
- Audio extraction
- Subtitle processing
- Thumbnail generation
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import ffmpeg
from ffmpeg import Error as FFmpegError

from app.core.config import settings


logger = logging.getLogger(__name__)


class VideoCodec(Enum):
    """Supported video codecs."""
    H264 = "libx264"
    H265 = "libx265" 
    VP8 = "libvpx"
    VP9 = "libvpx-vp9"
    AV1 = "libaom-av1"


class AudioCodec(Enum):
    """Supported audio codecs."""
    AAC = "aac"
    MP3 = "libmp3lame"
    OPUS = "libopus"
    VORBIS = "libvorbis"


class OutputFormat(Enum):
    """Supported output formats."""
    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"
    AVI = "avi"
    MOV = "mov"
    MP3 = "mp3"
    M4A = "m4a"
    WAV = "wav"
    FLAC = "flac"


@dataclass
class VideoProcessingOptions:
    """Configuration for video processing operations."""
    # Output format
    output_format: OutputFormat = OutputFormat.MP4
    
    # Video settings
    video_codec: Optional[VideoCodec] = VideoCodec.H264
    resolution: Optional[Tuple[int, int]] = None  # (width, height)
    video_bitrate: Optional[str] = None  # e.g., "2M", "5000k"
    framerate: Optional[int] = None
    
    # Audio settings  
    audio_codec: Optional[AudioCodec] = AudioCodec.AAC
    audio_bitrate: Optional[str] = None  # e.g., "128k", "320k"
    audio_channels: Optional[int] = None  # 1=mono, 2=stereo
    
    # Processing options
    trim_start: Optional[float] = None  # seconds
    trim_end: Optional[float] = None    # seconds
    remove_audio: bool = False
    extract_audio_only: bool = False
    
    # Quality presets
    use_preset: Optional[str] = None  # "ultrafast", "fast", "medium", "slow", "veryslow"


@dataclass
class ProcessingResult:
    """Result of video processing operation."""
    success: bool
    output_path: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[float] = None
    resolution: Optional[Tuple[int, int]] = None
    error_message: Optional[str] = None


class VideoProcessor:
    """
    Video processing service using FFmpeg.
    
    Handles video/audio conversion, quality adjustment, format conversion,
    and various post-processing operations.
    """
    
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "video_processing"
        self.temp_dir.mkdir(exist_ok=True)
    
    async def process_video(
        self, 
        input_path: str, 
        output_path: str, 
        options: VideoProcessingOptions
    ) -> ProcessingResult:
        """
        Process video with specified options.
        
        Args:
            input_path: Path to input video file
            output_path: Path for output file
            options: Processing configuration
            
        Returns:
            ProcessingResult with processing outcome
        """
        logger.info(f"Processing video: {input_path} -> {output_path}")
        
        try:
            # Validate input file
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"Input file not found: {input_path}")
            
            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Build FFmpeg command
            input_stream = ffmpeg.input(input_path)
            
            # Apply video filters and settings
            if options.extract_audio_only:
                # Audio-only extraction
                output_stream = self._configure_audio_extraction(input_stream, options)
            else:
                # Video processing
                output_stream = self._configure_video_processing(input_stream, options)
            
            # Execute FFmpeg command
            await self._run_ffmpeg(output_stream, output_path)
            
            # Get output file info
            file_size = os.path.getsize(output_path)
            duration, resolution = await self._get_media_info(output_path)
            
            result = ProcessingResult(
                success=True,
                output_path=output_path,
                file_size=file_size,
                duration=duration,
                resolution=resolution
            )
            
            logger.info(f"Successfully processed video: {output_path}")
            return result
            
        except Exception as e:
            logger.error(f"Video processing failed: {str(e)}")
            return ProcessingResult(
                success=False,
                error_message=str(e)
            )
    
    async def convert_format(
        self, 
        input_path: str, 
        output_path: str, 
        target_format: OutputFormat,
        quality: str = "medium"
    ) -> ProcessingResult:
        """
        Convert video to different format with preset quality.
        
        Args:
            input_path: Path to input file
            output_path: Path for output file
            target_format: Target output format
            quality: Quality preset ("low", "medium", "high")
            
        Returns:
            ProcessingResult with conversion outcome
        """
        logger.info(f"Converting format: {input_path} -> {target_format.value}")
        
        # Create processing options based on format and quality
        options = self._create_format_conversion_options(target_format, quality)
        
        return await self.process_video(input_path, output_path, options)
    
    async def extract_audio(
        self, 
        input_path: str, 
        output_path: str, 
        audio_format: OutputFormat = OutputFormat.MP3,
        bitrate: str = "128k"
    ) -> ProcessingResult:
        """
        Extract audio from video file.
        
        Args:
            input_path: Path to input video
            output_path: Path for output audio file
            audio_format: Audio format (MP3, M4A, WAV, FLAC)
            bitrate: Audio bitrate (e.g., "128k", "320k")
            
        Returns:
            ProcessingResult with extraction outcome
        """
        logger.info(f"Extracting audio: {input_path} -> {audio_format.value}")
        
        options = VideoProcessingOptions(
            output_format=audio_format,
            audio_bitrate=bitrate,
            extract_audio_only=True
        )
        
        return await self.process_video(input_path, output_path, options)
    
    async def generate_thumbnail(
        self, 
        input_path: str, 
        output_path: str, 
        timestamp: float = None
    ) -> ProcessingResult:
        """
        Generate thumbnail from video at specific timestamp.
        
        Args:
            input_path: Path to input video
            output_path: Path for output thumbnail
            timestamp: Time position in seconds (None for middle of video)
            
        Returns:
            ProcessingResult with thumbnail generation outcome
        """
        logger.info(f"Generating thumbnail: {input_path} -> {output_path}")
        
        try:
            # Get video duration if timestamp not specified
            if timestamp is None:
                duration, _ = await self._get_media_info(input_path)
                timestamp = duration / 2 if duration else 5  # middle or 5 seconds
            
            # Create FFmpeg command for thumbnail
            input_stream = ffmpeg.input(input_path, ss=timestamp)
            output_stream = input_stream.output(
                output_path,
                vframes=1,
                format='image2'
            )
            
            await self._run_ffmpeg(output_stream, output_path)
            
            file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            
            return ProcessingResult(
                success=True,
                output_path=output_path,
                file_size=file_size
            )
            
        except Exception as e:
            logger.error(f"Thumbnail generation failed: {str(e)}")
            return ProcessingResult(
                success=False,
                error_message=str(e)
            )
    
    async def trim_video(
        self, 
        input_path: str, 
        output_path: str, 
        start_time: float, 
        end_time: float
    ) -> ProcessingResult:
        """
        Trim video to specified time range.
        
        Args:
            input_path: Path to input video
            output_path: Path for output video
            start_time: Start time in seconds
            end_time: End time in seconds
            
        Returns:
            ProcessingResult with trimming outcome
        """
        logger.info(f"Trimming video: {start_time}s - {end_time}s")
        
        options = VideoProcessingOptions(
            trim_start=start_time,
            trim_end=end_time,
            output_format=OutputFormat.MP4
        )
        
        return await self.process_video(input_path, output_path, options)
    
    def _configure_video_processing(
        self, 
        input_stream, 
        options: VideoProcessingOptions
    ):
        """Configure FFmpeg stream for video processing."""
        
        video_stream = input_stream['v'] if 'v' in input_stream else input_stream.video
        audio_stream = input_stream['a'] if 'a' in input_stream else input_stream.audio
        
        # Apply video filters
        if options.resolution:
            width, height = options.resolution
            video_stream = video_stream.filter('scale', width, height)
        
        if options.framerate:
            video_stream = video_stream.filter('fps', fps=options.framerate)
        
        # Configure output with streams
        output_kwargs = {}
        
        if options.video_codec:
            output_kwargs['vcodec'] = options.video_codec.value
        
        if options.video_bitrate:
            output_kwargs['video_bitrate'] = options.video_bitrate
        
        if not options.remove_audio and audio_stream:
            if options.audio_codec:
                output_kwargs['acodec'] = options.audio_codec.value
            
            if options.audio_bitrate:
                output_kwargs['audio_bitrate'] = options.audio_bitrate
            
            if options.audio_channels:
                output_kwargs['ac'] = options.audio_channels
        
        # Quality preset
        if options.use_preset:
            output_kwargs['preset'] = options.use_preset
        
        # Trim settings
        if options.trim_start is not None:
            output_kwargs['ss'] = options.trim_start
        
        if options.trim_end is not None:
            output_kwargs['t'] = options.trim_end - (options.trim_start or 0)
        
        # Combine streams
        streams = [video_stream]
        if not options.remove_audio and audio_stream:
            streams.append(audio_stream)
        
        return ffmpeg.output(*streams, 'pipe:', format=options.output_format.value, **output_kwargs)
    
    def _configure_audio_extraction(
        self, 
        input_stream, 
        options: VideoProcessingOptions
    ):
        """Configure FFmpeg stream for audio-only extraction."""
        
        audio_stream = input_stream['a'] if 'a' in input_stream else input_stream.audio
        
        output_kwargs = {}
        
        if options.audio_codec:
            output_kwargs['acodec'] = options.audio_codec.value
        
        if options.audio_bitrate:
            output_kwargs['audio_bitrate'] = options.audio_bitrate
        
        if options.audio_channels:
            output_kwargs['ac'] = options.audio_channels
        
        # Trim settings
        if options.trim_start is not None:
            output_kwargs['ss'] = options.trim_start
        
        if options.trim_end is not None:
            output_kwargs['t'] = options.trim_end - (options.trim_start or 0)
        
        return ffmpeg.output(
            audio_stream, 
            'pipe:', 
            format=options.output_format.value, 
            vn=None,  # No video
            **output_kwargs
        )
    
    def _create_format_conversion_options(
        self, 
        target_format: OutputFormat, 
        quality: str
    ) -> VideoProcessingOptions:
        """Create processing options for format conversion."""
        
        options = VideoProcessingOptions(output_format=target_format)
        
        # Quality-based settings
        if quality == "high":
            options.video_bitrate = "5M"
            options.audio_bitrate = "320k"
            options.use_preset = "slow"
        elif quality == "medium":
            options.video_bitrate = "2M"
            options.audio_bitrate = "128k"
            options.use_preset = "medium"
        else:  # low
            options.video_bitrate = "1M"
            options.audio_bitrate = "96k"
            options.use_preset = "fast"
        
        # Format-specific codec selection
        if target_format == OutputFormat.MP4:
            options.video_codec = VideoCodec.H264
            options.audio_codec = AudioCodec.AAC
        elif target_format == OutputFormat.WEBM:
            options.video_codec = VideoCodec.VP9
            options.audio_codec = AudioCodec.OPUS
        elif target_format == OutputFormat.MKV:
            options.video_codec = VideoCodec.H265
            options.audio_codec = AudioCodec.AAC
        
        return options
    
    async def _run_ffmpeg(self, stream, output_path: str):
        """Execute FFmpeg command asynchronously."""
        
        # Create the final output stream
        final_stream = stream.overwrite_output()
        
        # Get the command as a list
        cmd = ffmpeg.compile(final_stream)
        
        # Replace 'pipe:' with actual output path
        cmd = [arg.replace('pipe:', output_path) for arg in cmd]
        
        logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
        
        # Run FFmpeg asynchronously
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            raise FFmpegError(f"FFmpeg failed: {error_msg}")
    
    async def _get_media_info(self, file_path: str) -> Tuple[Optional[float], Optional[Tuple[int, int]]]:
        """Get media file information (duration and resolution)."""
        
        try:
            probe = await asyncio.get_event_loop().run_in_executor(
                None, ffmpeg.probe, file_path
            )
            
            duration = None
            resolution = None
            
            # Get duration from format info
            if 'format' in probe and 'duration' in probe['format']:
                duration = float(probe['format']['duration'])
            
            # Get resolution from video stream
            for stream in probe.get('streams', []):
                if stream.get('codec_type') == 'video':
                    width = stream.get('width')
                    height = stream.get('height')
                    if width and height:
                        resolution = (width, height)
                    break
            
            return duration, resolution
            
        except Exception as e:
            logger.warning(f"Could not get media info for {file_path}: {str(e)}")
            return None, None


# Factory function
def create_video_processor() -> VideoProcessor:
    """Create a new VideoProcessor instance."""
    return VideoProcessor()