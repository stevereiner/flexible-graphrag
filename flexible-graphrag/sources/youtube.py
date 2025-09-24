"""
YouTube data source for Flexible GraphRAG using youtube_transcript_api directly.
"""

from typing import List, Dict, Any, Optional
import logging
import re
import os
from urllib.parse import urlparse, parse_qs
from datetime import timedelta
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class YouTubeSource(BaseDataSource):
    """Data source for YouTube videos using youtube_transcript_api directly"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("url", "")
        self.chunk_size_seconds = config.get("chunk_size_seconds", 60)  # 1 minute default
        
        # Extract video ID from URL
        self.video_id = self._extract_video_id(self.url)
        
        # Import youtube_transcript_api directly (more reliable than LlamaIndex wrapper)
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api.proxies import GenericProxyConfig
            
            # Set up proxy if configured
            proxy = os.environ.get("YOUTUBE_TRANSCRIPT_PROXY")
            proxy_config = GenericProxyConfig(http_url=proxy, https_url=proxy) if proxy else None
            self.youtube_api = YouTubeTranscriptApi(proxy_config=proxy_config)
            
            logger.info(f"YouTubeSource initialized for video ID: {self.video_id}")
        except ImportError as e:
            logger.error(f"Failed to import youtube_transcript_api: {e}")
            raise ImportError("Please install youtube_transcript_api: pip install youtube_transcript_api")
    
    def _extract_video_id(self, url: str) -> str:
        """Extract YouTube video ID from various URL formats"""
        if not url:
            return ""
        
        # Clean up escaped braces and other common formatting issues
        cleaned_url = url.replace('\\{', '').replace('\\}', '').replace('{', '').replace('}', '')
        
        # Handle different YouTube URL formats
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
            # More flexible patterns for edge cases
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#\s]+)',
            r'youtube\.com\/v\/([^&\n?#\s]+)',
            r'youtube\.com\/watch\?.*v=([^&\n?#\s]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cleaned_url)
            if match:
                video_id = match.group(1)
                # YouTube video IDs are typically 11 characters, but allow some flexibility
                if len(video_id) >= 10 and len(video_id) <= 15:
                    return video_id
        
        # If no pattern matches, check if it's already a video ID format
        if re.match(r'^[a-zA-Z0-9_-]{10,15}$', cleaned_url):
            return cleaned_url
        
        # Last resort: return the cleaned URL
        return cleaned_url
    
    def validate_config(self) -> bool:
        """Validate the YouTube source configuration."""
        if not self.url:
            logger.error("No URL specified for YouTube source")
            return False
        
        if not self.video_id:
            logger.error(f"Could not extract video ID from URL: {self.url}")
            return False
        
        if self.chunk_size_seconds <= 0:
            logger.error(f"Invalid chunk_size_seconds value: {self.chunk_size_seconds}")
            return False
        
        return True
    
    def _get_youtube_transcript(self) -> List[Dict]:
        """Get raw transcript data from YouTube API"""
        try:
            transcript_pieces = self.youtube_api.fetch(self.video_id, preserve_formatting=True)
            return transcript_pieces.to_raw_data()
        except Exception as e:
            message = f"YouTube transcript is not available for video ID: {self.video_id}"
            logger.error(message)
            raise Exception(message)
    
    def _create_chunked_documents(self, transcript_data: List[Dict]) -> List[Document]:
        """Create time-based chunks from transcript data"""
        try:
            documents = []
            transcript_content = ''
            counter = self.chunk_size_seconds
            
            for i, segment in enumerate(transcript_data):
                if segment['start'] < counter:
                    transcript_content += segment['text'] + " "
                else:
                    # Create document for current chunk
                    transcript_content += segment['text'] + " "
                    
                    start_time = counter - self.chunk_size_seconds
                    end_time = segment['start']
                    
                    doc = Document(
                        text=transcript_content.strip(),
                        metadata={
                            'source': 'youtube',
                            'video_id': self.video_id,
                            'url': self.url,
                            'start_timestamp': str(timedelta(seconds=start_time)).split('.')[0],
                            'end_timestamp': str(timedelta(seconds=end_time)).split('.')[0],
                            'chunk_size_seconds': self.chunk_size_seconds,
                            'source_type': 'youtube_transcript'
                        }
                    )
                    documents.append(doc)
                    
                    counter += self.chunk_size_seconds
                    transcript_content = ''
            
            # Handle remaining content
            if transcript_content.strip():
                start_time = counter - self.chunk_size_seconds
                end_time = transcript_data[-1]['start'] if transcript_data else counter
                
                doc = Document(
                    text=transcript_content.strip(),
                    metadata={
                        'source': 'youtube',
                        'video_id': self.video_id,
                        'url': self.url,
                        'start_timestamp': str(timedelta(seconds=start_time)).split('.')[0],
                        'end_timestamp': str(timedelta(seconds=end_time)).split('.')[0],
                        'chunk_size_seconds': self.chunk_size_seconds,
                        'source_type': 'youtube_transcript'
                    }
                )
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Error creating chunked documents: {str(e)}")
            raise

    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from YouTube video transcript.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading YouTube transcript for video ID: {self.video_id}")
            
            # Get raw transcript data
            transcript_data = self._get_youtube_transcript()
            
            # Create time-based chunks
            documents = self._create_chunked_documents(transcript_data)
            
            logger.info(f"YouTubeSource loaded {len(documents)} transcript chunks for video: {self.video_id}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading YouTube transcript for video '{self.video_id}': {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from YouTube video transcript with progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading YouTube transcript for video ID: {self.video_id} with progress tracking")
            
            if progress_callback:
                progress_callback(0, 3, "Fetching YouTube transcript...", self.url)
            
            # Get raw transcript data
            transcript_data = self._get_youtube_transcript()
            
            if progress_callback:
                progress_callback(1, 3, f"Processing transcript into {self.chunk_size_seconds}s chunks...", self.url)
            
            # Create time-based chunks
            documents = self._create_chunked_documents(transcript_data)
            
            if progress_callback:
                progress_callback(3, 3, f"Processed {len(documents)} transcript chunks", self.url)
            
            logger.info(f"YouTubeSource loaded {len(documents)} transcript chunks from: {self.url}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading YouTube transcript for video '{self.video_id}': {str(e)}")
            raise
