"""
Data source factory for creating appropriate data source instances.
"""

from typing import Dict, Any
import logging
from sources.base import BaseDataSource
from sources import (
    FileSystemSource, CmisSource, AlfrescoSource,
    WebSource, WikipediaSource, YouTubeSource,
    S3Source, GCSSource, AzureBlobSource,
    OneDriveSource, SharePointSource, BoxSource, GoogleDriveSource
)

logger = logging.getLogger(__name__)


class DataSourceFactory:
    """Factory for creating data source instances."""
    
    _source_classes = {
        "filesystem": FileSystemSource,
        "cmis": CmisSource,
        "alfresco": AlfrescoSource,
        "web": WebSource,
        "wikipedia": WikipediaSource,
        "youtube": YouTubeSource,
        "s3": S3Source,
        "gcs": GCSSource,
        "azure_blob": AzureBlobSource,
        "onedrive": OneDriveSource,
        "sharepoint": SharePointSource,
        "box": BoxSource,
        "google_drive": GoogleDriveSource
    }
    
    @classmethod
    def create_source(cls, source_type: str, config: Dict[str, Any]) -> BaseDataSource:
        """
        Create a data source instance based on type and configuration.
        
        Args:
            source_type: Type of data source (e.g., "web", "s3", "gcs")
            config: Configuration dictionary for the data source
            
        Returns:
            BaseDataSource: Configured data source instance
            
        Raises:
            ValueError: If source type is not supported
            Exception: If source creation fails
        """
        if source_type not in cls._source_classes:
            available_types = ", ".join(cls._source_classes.keys())
            raise ValueError(f"Unsupported data source type: {source_type}. Available types: {available_types}")
        
        source_class = cls._source_classes[source_type]
        
        try:
            logger.info(f"Creating {source_type} data source")
            source = source_class(config)
            
            # Validate configuration
            if not source.validate_config():
                raise ValueError(f"Invalid configuration for {source_type} data source")
            
            logger.info(f"Successfully created {source_type} data source")
            return source
            
        except Exception as e:
            logger.error(f"Failed to create {source_type} data source: {str(e)}")
            raise
    
    @classmethod
    def get_supported_types(cls) -> list:
        """Get list of supported data source types."""
        return list(cls._source_classes.keys())
    
    @classmethod
    def is_supported(cls, source_type: str) -> bool:
        """Check if a data source type is supported."""
        return source_type in cls._source_classes
