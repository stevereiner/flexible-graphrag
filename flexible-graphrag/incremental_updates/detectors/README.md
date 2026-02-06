# Change Detectors Package

Modular change detection system for various data sources.

## Structure

```
detectors/
├── __init__.py              # Package exports
├── base.py                  # Base classes (ChangeDetector, ChangeEvent, etc.)
├── filesystem_detector.py   # Filesystem monitoring (watchdog)
├── s3_detector.py           # S3 event detection (SQS)
├── alfresco_detector.py     # Alfresco repository monitoring (ActiveMQ/polling)
├── azure_blob_detector.py   # Azure Blob Storage (change feed)
├── gcs_detector.py          # Google Cloud Storage (Pub/Sub)
├── google_drive_detector.py # Google Drive (Changes API)
├── box_detector.py          # Box (Events API)
├── msgraph_detector.py      # Microsoft Graph - OneDrive/SharePoint (Delta Query)
├── factory.py               # Detector factory
└── README.md                # This file
```

## Usage

```python
from incremental_updates.detectors import (
    create_detector,
    ChangeDetector,
    ChangeType,
    ChangeEvent,
    FileMetadata,
)

# Create detector via factory
detector = create_detector('s3', {
    'bucket': 'my-bucket',
    'prefix': 'documents/',
    'sqs_queue_url': 'https://sqs.us-east-1.amazonaws.com/.../queue'
})

# Or directly instantiate
from incremental_updates.detectors import S3Detector

detector = S3Detector({
    'bucket': 'my-bucket',
    'prefix': 'documents/',
    'sqs_queue_url': 'https://sqs.us-east-1.amazonaws.com/.../queue',
    'aws_region': 'us-east-1'
})

# Start monitoring
await detector.start()

# Get changes (event stream)
async for event in detector.get_changes():
    if event:
        print(f"{event.change_type.value}: {event.metadata.path}")

# Or list all files (periodic)
files = await detector.list_all_files()

# Load file content
content = await detector.load_file_content('path/to/file.txt')

# Stop monitoring
await detector.stop()
```

## Adding New Detectors

To add a new detector (e.g., Google Cloud Storage):

### 1. Create detector file: `gcs_detector.py`

```python
"""
GCS Change Detector

Real-time GCS change detection using Pub/Sub notifications.
"""

import logging
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata

logger = logging.getLogger("flexible_graphrag.incremental.detectors.gcs")

try:
    from google.cloud import storage, pubsub_v1
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("google-cloud-storage not installed")


class GCSDetector(ChangeDetector):
    """
    GCS change detector using Cloud Pub/Sub notifications.
    
    Configuration:
        bucket: GCS bucket name (required)
        prefix: GCS prefix/folder filter (optional)
        project_id: GCP project ID (required)
        pubsub_topic: Pub/Sub topic for notifications (optional)
        pubsub_subscription: Pub/Sub subscription (optional)
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        # ... implementation ...
    
    async def start(self):
        # ... implementation ...
        pass
    
    async def stop(self):
        # ... implementation ...
        pass
    
    async def list_all_files(self) -> List[FileMetadata]:
        # ... implementation ...
        pass
    
    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        # ... implementation ...
        pass
    
    async def load_file_content(self, path: str) -> Optional[bytes]:
        # ... implementation ...
        pass
```

### 2. Update `__init__.py`

```python
from .gcs_detector import GCSDetector

__all__ = [
    # ... existing exports ...
    'GCSDetector',
]
```

### 3. Update `factory.py`

```python
from .gcs_detector import GCSDetector

def create_detector(source_type: str, config: Dict) -> Optional[ChangeDetector]:
    # ... existing code ...
    
    elif source_type == 'gcs':
        return GCSDetector(config)
    
    # ... rest ...
```

## Current Detectors

### FilesystemDetector

- **Library**: `watchdog` (MIT)
- **Mode**: Real-time OS events
- **Status**: ✅ Production ready

**Configuration**:
```python
{
    'paths': ['/path/to/watch', '/another/path']
}
```

**Features**:
- Recursive directory monitoring
- Single file monitoring
- Quiet period to ignore own changes
- Retry logic for file locks (Windows)

---

### S3Detector

- **Library**: `boto3` (Apache 2.0)
- **Mode**: Event-based (SQS) + Periodic fallback
- **Status**: ✅ Production ready

**Configuration (Event Mode)**:
```python
{
    'bucket': 'my-bucket',
    'prefix': 'documents/',
    'sqs_queue_url': 'https://sqs.us-east-1.amazonaws.com/123/queue',
    'aws_region': 'us-east-1',
    'aws_access_key_id': 'AKIA...',  # Optional
    'aws_secret_access_key': '...'   # Optional
}
```

**Configuration (Periodic Mode)**:
```python
{
    'bucket': 'my-bucket',
    'prefix': 'documents/',
    'aws_region': 'us-east-1'
}
```

**Features**:
- Real-time SQS event notifications (1-5s latency)
- Automatic fallback to periodic refresh
- SNS wrapper support (S3→SNS→SQS)
- Retry with exponential backoff
- Prefix/suffix filtering
- Statistics tracking

**Documentation**: See `../S3-SQS-SETUP.md`

---

### AlfrescoDetector

- **Library**: `python-alfresco-api`, `cmislib` (optional)
- **Mode**: Dual mode - Event-based (real-time) + Polling (fallback)
- **Status**: ✅ Production ready

**Configuration (Basic)**:
```python
{
    'url': 'http://localhost:8080',
    'username': 'admin',
    'password': 'admin',
    'path': '/Company Home/Sites/mysite/documentLibrary',
    'recursive': True,
    'polling_interval': 300  # 5 minutes (used if events unavailable)
}
```

**Configuration (Monitor Specific Nodes)**:
```python
{
    'url': 'http://localhost:8080',
    'username': 'admin',
    'password': 'admin',
    'nodeIds': [
        'e8680e58-0701-4b64-a5a9-40c517a1c3ac',  # Folder ID (UUID from REST API)
        'f2341abc-1234-5678-9abc-def012345678'   # Document ID (UUID from REST API)
    ],
    'recursive': True,
    'event_mode': None  # Auto-detect (True=force events, False=force polling)
}
```

**Configuration (From ACA/ADF UI)**:
```python
{
    'url': 'http://localhost:8080',
    'username': 'admin',
    'password': 'admin',
    'nodeDetails': [
        {
            'id': 'e8680e58-0701-4b64-a5a9-40c517a1c3ac',
            'name': 'Documents',
            'path': '/Company Home/Sites/mysite/documentLibrary',
            'isFile': False,
            'isFolder': True
        }
    ],
    'recursive': True
}
```

**Features**:
- **Event Mode (Real-time)**:
  - Alfresco Event Gateway (Enterprise) or ActiveMQ (Community)
  - Near-instant detection (< 1 second)
  - Auto-detects available event system
- **Polling Mode (Fallback)**:
  - Configurable interval (default: 5 minutes)
  - Works with any Alfresco version
- Detects CREATE, UPDATE, DELETE events
- Path-based or node-based monitoring (by UUID)
- Recursive folder monitoring
- Node ID filtering for targeted monitoring

**Mode Selection**:
- `event_mode: None` - Auto-detect (default, recommended)
- `event_mode: True` - Force event mode (fails if unavailable)
- `event_mode: False` - Force polling mode

---

### AzureBlobDetector

- **Library**: `azure-storage-blob`, `azure-storage-blob-changefeed` (MIT)
- **Mode**: Change feed + Periodic fallback
- **Status**: ✅ Ready for testing

**Configuration**:
```python
{
    'container_name': 'documents',
    'connection_string': 'DefaultEndpointsProtocol=https;...',  # Option 1
    # OR
    'account_url': 'https://myaccount.blob.core.windows.net',  # Option 2
    'account_key': '...',                                       # Option 2
    'prefix': 'folder/',  # Optional
    'enable_change_feed': True
}
```

**Features**:
- Azure Blob Change Feed for real-time detection
- Continuation token support for resuming
- Automatic fallback to periodic refresh
- Blob created, deleted, and updated events

---

### GCSDetector

- **Library**: `google-cloud-storage`, `google-cloud-pubsub` (Apache 2.0)
- **Mode**: Pub/Sub notifications + Periodic fallback
- **Status**: ✅ Ready for testing

**Configuration**:
```python
{
    'bucket': 'my-bucket',
    'prefix': 'documents/',  # Optional
    'project_id': 'my-project',
    'pubsub_subscription': 'my-subscription',  # Optional, for event mode
    'service_account_key': {...},  # Optional (dict)
    'service_account_key_path': '/path/to/key.json'  # Optional
}
```

**Features**:
- Real-time Pub/Sub notifications
- Automatic fallback to periodic refresh
- Object finalize (create/update), delete, and archive events
- Generation tracking for create vs update detection

---

### GoogleDriveDetector

- **Library**: `google-api-python-client` (Apache 2.0)
- **Mode**: Changes API (polling)
- **Status**: ✅ Ready for testing

**Configuration**:
```python
{
    'folder_id': '...',  # Optional, monitors all if not set
    'credentials': {...},  # Service account key dict
    # OR
    'credentials_path': '/path/to/credentials.json',
    # OR
    'token_path': '/path/to/token.json',  # OAuth token
    'polling_interval': 60,  # Seconds
    'recursive': True
}
```

**Features**:
- Changes API with delta tracking
- Page token for efficient polling
- Service account or OAuth authentication
- Folder-based filtering
- Recursive subfolder monitoring

---

### BoxDetector

- **Library**: `boxsdk` (Apache 2.0)
- **Mode**: Events API (polling)
- **Status**: ✅ Ready for testing

**Configuration (Developer Token)**:
```python
{
    'folder_id': '0',  # '0' = root
    'access_token': '...',
    'polling_interval': 30,
    'recursive': True
}
```

**Configuration (JWT)**:
```python
{
    'folder_id': '0',
    'jwt_config_path': '/path/to/config.json',
    'polling_interval': 30,
    'recursive': True
}
```

**Configuration (CCG)**:
```python
{
    'folder_id': '0',
    'client_id': '...',
    'client_secret': '...',
    'enterprise_id': '...',  # OR user_id
    'polling_interval': 30,
    'recursive': True
}
```

**Features**:
- Box Events API with stream position tracking
- JWT, Developer Token, CCG, and OAuth2 authentication
- Upload, modify, delete, rename, and move events
- Folder-based filtering
- Recursive subfolder monitoring

---

### MicrosoftGraphDetector

- **Library**: `msgraph-sdk`, `azure-identity` (MIT)
- **Mode**: Delta Query (polling)
- **Status**: ✅ Ready for testing (simplified implementation)

**Configuration**:
```python
{
    'client_id': '...',
    'client_secret': '...',
    'tenant_id': '...',
    'drive_id': '...',  # Specific drive
    # OR
    'site_id': '...',  # SharePoint site
    # OR
    'user_id': 'me',  # User's OneDrive
    'folder_path': 'Documents/Folder',  # Optional
    'polling_interval': 60
}
```

**Features**:
- Delta query for incremental changes
- Supports OneDrive, OneDrive for Business, and SharePoint
- Client secret authentication
- Delta link tracking for efficient polling

**Note**: This is a simplified implementation. Full production use would benefit from:
- Webhook subscriptions for true real-time updates
- Better file download implementation
- OAuth token refresh handling

---

## Planned Detectors

All major cloud storage and collaboration platforms are now implemented!

### Future Enhancements

While all major detectors are implemented, future improvements could include:

1. **Microsoft Graph Webhooks**: Currently using polling with Delta Query. Could add webhook subscriptions for true real-time updates (requires public HTTPS endpoint and domain verification).

2. **Google Drive Push Notifications**: Currently using Changes API polling. Could add Watch API with push notifications (requires public HTTPS endpoint and domain verification).

3. **Box Webhooks v2**: Currently using Events API polling. Could add webhook subscriptions for true real-time updates (requires public HTTPS endpoint).

## Testing

Unit tests are located in `../test_s3_detector.py` (to be split per detector).

Run tests:
```bash
pytest test_s3_detector.py -v
```

## Architecture

### Base Classes

All detectors inherit from `ChangeDetector` and implement:

- `async start()` - Initialize and start monitoring
- `async stop()` - Stop monitoring and cleanup
- `async list_all_files()` - List all files (periodic mode)
- `async get_changes()` - Stream change events (event mode)
- `async load_file_content(path)` - Load file content

### Event Flow

```
Data Source → Detector.get_changes() → ChangeEvent → Engine → Processing
```

### Change Types

- `CREATE` - New file detected
- `UPDATE` - Existing file modified
- `DELETE` - File removed

## Benefits of Modular Structure

✅ **Maintainability**: Each detector in its own file  
✅ **Testability**: Easy to test individual detectors  
✅ **Extensibility**: Simple to add new detectors  
✅ **Clarity**: Clear separation of concerns  
✅ **Independence**: Changes to one detector don't affect others  
✅ **Documentation**: Each detector has its own docs

## Migration from Old Structure

The old monolithic `detectors.py` has been split into:

- `base.py` - Base classes and interfaces
- `filesystem_detector.py` - Filesystem monitoring
- `s3_detector.py` - S3 change detection
- `factory.py` - Detector creation

Old code will continue to work via compatibility imports in `detectors_old.py`, but should be updated to use the new package:

```python
# Old (still works)
from incremental_updates.detectors import FilesystemDetector

# New (preferred)
from incremental_updates.detectors import FilesystemDetector
```

The import path is the same, but now uses the package instead of a single file.
