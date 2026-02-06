"""
Detector Factory

Creates appropriate change detector based on source type.
"""

import logging
from typing import Dict, Optional

from .base import ChangeDetector
from .filesystem_detector import FilesystemDetector
from .s3_detector import S3Detector
from .alfresco_detector import AlfrescoDetector
from .azure_blob_detector import AzureBlobDetector
from .gcs_detector import GCSDetector
from .google_drive_detector import GoogleDriveDetector
from .box_detector import BoxDetector
from .msgraph_detector import MicrosoftGraphDetector

logger = logging.getLogger("flexible_graphrag.incremental.detectors.factory")


def create_detector(source_type: str, config: Dict) -> Optional[ChangeDetector]:
    """
    Create detector based on source type.
    
    Args:
        source_type: Type of data source ('filesystem', 's3', 'alfresco', 'gcs', etc.)
        config: Source-specific configuration dictionary
    
    Returns:
        ChangeDetector instance, or None if source type not supported
    """
    
    if source_type == 'filesystem':
        return FilesystemDetector(config)
    
    elif source_type == 's3':
        return S3Detector(config)
    
    elif source_type == 'alfresco':
        return AlfrescoDetector(config)
    
    elif source_type == 'gcs':
        return GCSDetector(config)
    
    elif source_type == 'azure_blob':
        return AzureBlobDetector(config)
    
    elif source_type == 'google_drive':
        return GoogleDriveDetector(config)
    
    elif source_type == 'onedrive' or source_type == 'sharepoint':
        # Both OneDrive and SharePoint use Microsoft Graph
        return MicrosoftGraphDetector(config)
    
    elif source_type == 'box':
        return BoxDetector(config)
    
    else:
        logger.warning(f"Unsupported source type: {source_type}")
        return None
