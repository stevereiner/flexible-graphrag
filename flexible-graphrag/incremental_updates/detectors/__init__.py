"""
Change Detectors Package

Modular change detection for various data sources.
Each detector is in its own file for better maintainability.
"""

from .base import (
    ChangeDetector,
    ChangeType,
    ChangeEvent,
    FileMetadata
)

from .filesystem_detector import FilesystemDetector
from .s3_detector import S3Detector
from .alfresco_detector import AlfrescoDetector
from .azure_blob_detector import AzureBlobDetector
from .gcs_detector import GCSDetector
from .google_drive_detector import GoogleDriveDetector
from .box_detector import BoxDetector
from .msgraph_detector import MicrosoftGraphDetector

from .factory import create_detector

__all__ = [
    # Base classes
    'ChangeDetector',
    'ChangeType',
    'ChangeEvent',
    'FileMetadata',
    
    # Detector implementations
    'FilesystemDetector',
    'S3Detector',
    'AlfrescoDetector',
    'AzureBlobDetector',
    'GCSDetector',
    'GoogleDriveDetector',
    'BoxDetector',
    'MicrosoftGraphDetector',
    
    # Factory
    'create_detector',
]
