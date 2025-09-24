"""
Data source modules for Flexible GraphRAG.

This package contains modular data source implementations using LlamaIndex Hub readers.
Each data source is implemented as a separate module for better maintainability.
"""

from .base import BaseDataSource
from .filesystem import FileSystemSource
from .cmis import CmisSource
from .alfresco import AlfrescoSource
from .web import WebSource
from .wikipedia import WikipediaSource
from .youtube import YouTubeSource
from .s3 import S3Source
from .gcs import GCSSource
from .azure_blob import AzureBlobSource
from .onedrive import OneDriveSource
from .sharepoint import SharePointSource
from .box import BoxSource
from .google_drive import GoogleDriveSource

__all__ = [
    "BaseDataSource",
    "FileSystemSource",
    "CmisSource", 
    "AlfrescoSource",
    "WebSource",
    "WikipediaSource",
    "YouTubeSource",
    "S3Source",
    "GCSSource",
    "AzureBlobSource",
    "OneDriveSource",
    "SharePointSource",
    "BoxSource",
    "GoogleDriveSource"
]
