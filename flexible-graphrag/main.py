import os
import logging
import sys
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
import asyncio
from pathlib import Path
import uvicorn
import shutil
from dotenv import load_dotenv
import importlib.metadata
import nest_asyncio
from config import Settings, DataSourceType
from backend import get_backend

# Load environment variables
load_dotenv()

# Fix for async event loop issues with containers and LlamaIndex
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    # Docker/Linux environments - use default policy but ensure proper loop handling
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# Apply nest_asyncio to allow nested event loops (required for LlamaIndex in FastAPI)
nest_asyncio.apply()

# Ensure we have a proper event loop for Docker containers
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Configure logging with both file and console output
log_filename = f'flexible-graphrag-api-{datetime.now().strftime("%Y%m%d-%H%M%S")}.log'

# Force logging to work properly with uvicorn
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configure root logger (prevent duplicate handlers)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear any existing handlers to prevent duplicates
root_logger.handlers.clear()

# Add our handlers
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.info(f"Starting application with log file: {log_filename}")

# Force flush
file_handler.flush()
console_handler.flush()

# Initialize FastAPI app
app = FastAPI(
    title="Flexible GraphRAG API",
    description="API for processing documents with configurable hybrid search (vector, graph, full-text)",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class CmisConfig(BaseModel):
    url: str
    username: str
    password: str
    folder_path: str

class AlfrescoConfig(BaseModel):
    url: str
    username: str
    password: str
    path: str

class WebConfig(BaseModel):
    url: str

class WikipediaConfig(BaseModel):
    query: str
    language: Optional[str] = "en"
    max_docs: Optional[int] = 1

class YouTubeConfig(BaseModel):
    url: str
    chunk_size_seconds: Optional[int] = 60

class S3Config(BaseModel):
    bucket_name: str  # Modern approach - required bucket name
    prefix: Optional[str] = None
    access_key: str
    secret_key: str
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    region_name: Optional[str] = "us-east-1"

class GCSConfig(BaseModel):
    bucket_name: str
    project_id: str
    credentials: str
    prefix: Optional[str] = None
    folder_name: Optional[str] = None

class AzureBlobConfig(BaseModel):
    container_name: str
    account_url: str
    blob: Optional[str] = None  # renamed from blob_name to match LlamaCloud
    prefix: Optional[str] = None
    account_name: str
    account_key: str

class OneDriveConfig(BaseModel):
    user_principal_name: str  # Required field from LlamaCloud
    client_id: str
    client_secret: str
    tenant_id: str
    folder_path: Optional[str] = None
    folder_id: Optional[str] = None
    file_ids: Optional[List[str]] = []

class SharePointConfig(BaseModel):
    client_id: str
    client_secret: str
    tenant_id: str
    site_name: str  # Changed from site_url to site_name (LlamaCloud compatible)
    site_id: Optional[str] = None  # Optional: for Sites.Selected permission
    folder_path: Optional[str] = None
    folder_id: Optional[str] = None  # Changed from document_library to folder_id

class BoxConfig(BaseModel):
    folder_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    developer_token: Optional[str] = None
    box_folder_id: Optional[str] = "0"
    box_file_ids: Optional[List[str]] = []
    access_token: Optional[str] = None

class GoogleDriveConfig(BaseModel):
    folder_id: Optional[str] = None
    file_ids: Optional[List[str]] = []
    query: Optional[str] = ""
    credentials: Optional[str] = None
    credentials_path: Optional[str] = None
    token_path: Optional[str] = None

class IngestRequest(BaseModel):
    paths: Optional[List[str]] = None  # overrides config
    data_source: Optional[str] = None  # filesystem, cmis, alfresco, web, wikipedia, youtube, s3, gcs, azure_blob, onedrive, sharepoint, box, google_drive
    cmis_config: Optional[CmisConfig] = None
    alfresco_config: Optional[AlfrescoConfig] = None
    web_config: Optional[WebConfig] = None
    wikipedia_config: Optional[WikipediaConfig] = None
    youtube_config: Optional[YouTubeConfig] = None
    s3_config: Optional[S3Config] = None
    gcs_config: Optional[GCSConfig] = None
    azure_blob_config: Optional[AzureBlobConfig] = None
    onedrive_config: Optional[OneDriveConfig] = None
    sharepoint_config: Optional[SharePointConfig] = None
    box_config: Optional[BoxConfig] = None
    google_drive_config: Optional[GoogleDriveConfig] = None

class QueryRequest(BaseModel):
    query: str
    top_k: int = 10
    query_type: Optional[str] = "hybrid"  # hybrid, qa

class TextIngestRequest(BaseModel):
    content: str
    source_name: Optional[str] = "sample-test"

class Document(BaseModel):
    id: str
    name: str
    content: str

# Initialize system
settings = Settings()
backend_instance = get_backend()

# Lifecycle events for proper resource cleanup
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when the application shuts down."""
    logger.info("Application shutdown: cleaning up resources")

# API Endpoints
@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.post("/api/ingest")
async def ingest(request: IngestRequest):
    try:
        logger.info(f"Starting async document ingestion: {request}")
        logger.info(f"Data source: {request.data_source}, Paths: {request.paths}")
        
        data_source = request.data_source or str(settings.data_source)
        paths = request.paths
        
        # Prepare additional kwargs for data source configs
        kwargs = {}
        if request.cmis_config:
            kwargs['cmis_config'] = request.cmis_config.dict()
        if request.alfresco_config:
            kwargs['alfresco_config'] = request.alfresco_config.dict()
        if request.web_config:
            kwargs['web_config'] = request.web_config.dict()
        if request.wikipedia_config:
            kwargs['wikipedia_config'] = request.wikipedia_config.dict()
        if request.youtube_config:
            kwargs['youtube_config'] = request.youtube_config.dict()
        if request.s3_config:
            kwargs['s3_config'] = request.s3_config.dict()
        if request.gcs_config:
            kwargs['gcs_config'] = request.gcs_config.dict()
        if request.azure_blob_config:
            kwargs['azure_blob_config'] = request.azure_blob_config.dict()
        if request.onedrive_config:
            kwargs['onedrive_config'] = request.onedrive_config.dict()
        if request.sharepoint_config:
            kwargs['sharepoint_config'] = request.sharepoint_config.dict()
        if request.box_config:
            kwargs['box_config'] = request.box_config.dict()
        if request.google_drive_config:
            kwargs['google_drive_config'] = request.google_drive_config.dict()
        
        result = await backend_instance.ingest_documents(data_source=data_source, paths=paths, **kwargs)
        
        logger.info(f"Document ingestion started with ID: {result['processing_id']}")
        return result
            
    except Exception as e:
        logger.error(f"Error starting document ingestion: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def cleanup_uploads(keep_recent_files: int = 0):
    """Clean up uploaded files, optionally keeping most recent files"""
    try:
        upload_dir = Path("./uploads")
        if not upload_dir.exists():
            return
        
        # Get all files sorted by modification time (newest first)
        files = sorted(upload_dir.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Remove files beyond the keep_recent_files limit
        for file_path in files[keep_recent_files:]:
            if file_path.is_file():
                file_path.unlink()
                logger.info(f"Cleaned up uploaded file: {file_path.name}")
                
        logger.info(f"Upload cleanup completed - kept {min(len(files), keep_recent_files)} recent files")
    except Exception as e:
        logger.warning(f"Error during upload cleanup: {str(e)}")

@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload files and store them in upload directory for processing"""
    try:
        # Create upload directory if it doesn't exist
        upload_dir = Path("./uploads")
        upload_dir.mkdir(exist_ok=True)
        
        uploaded_files = []
        skipped_files = []
        
        # File size limit (100MB per file)
        MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB in bytes
        
        for file in files:
            # Validate file type (basic validation)
            if not file.filename:
                continue
            
            # Read file content to check size
            content = await file.read()
            
            # Check file size
            if len(content) > MAX_FILE_SIZE:
                skipped_files.append({
                    "filename": file.filename,
                    "reason": f"File too large ({len(content) / 1024 / 1024:.1f}MB > 100MB)"
                })
                continue
                
            # Check if file type is supported
            supported_extensions = {'.pdf', '.docx', '.xlsx', '.pptx', '.txt', '.md', '.html', '.csv', '.png', '.jpg', '.jpeg'}
            file_extension = Path(file.filename).suffix.lower()
            
            if file_extension not in supported_extensions:
                skipped_files.append({
                    "filename": file.filename,
                    "reason": f"Unsupported file type: {file_extension}"
                })
                continue
            
            # Save file to upload directory (overwrite if exists)
            file_path = upload_dir / file.filename
            
            # Write file content (content already read for size validation)
            # This will overwrite existing files with the same name
            with open(file_path, "wb") as buffer:
                buffer.write(content)
            
            uploaded_files.append({
                "filename": file.filename,
                "saved_as": file_path.name,  # Now always matches original filename
                "path": str(file_path),
                "size": len(content)
            })
            
            logger.info(f"Uploaded file: {file.filename} -> {file_path}")
        
        response_message = f"Successfully uploaded {len(uploaded_files)} files"
        if skipped_files:
            response_message += f", skipped {len(skipped_files)} files"
        
        return {
            "success": True,
            "message": response_message,
            "files": uploaded_files,
            "skipped": skipped_files
        }
        
    except Exception as e:
        logger.error(f"Error uploading files: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def search(request: QueryRequest):
    try:
        logger.info(f"Processing {request.query_type} query: {request.query}")
        
        if request.query_type == "qa":
            # Q&A query - return answer
            result = await backend_instance.qa_query(request.query)
            if result["success"]:
                logger.info("Q&A query completed successfully")
                return {"success": True, "answer": result["answer"]}
            else:
                raise HTTPException(500, result["error"])
        else:
            # Hybrid search - return results
            result = await backend_instance.search_documents(request.query, request.top_k)
            if result["success"]:
                logger.info("Hybrid search completed successfully")
                return {"success": True, "results": result["results"]}
            else:
                raise HTTPException(500, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query")
async def query_graph(request: QueryRequest):
    try:
        logger.info(f"Processing query: {request.query}")
        result = await backend_instance.query_documents(request.query, request.top_k)
        
        if result["success"]:
            logger.info("Query processing completed successfully")
            return {"status": "success", "answer": result["answer"]}
        else:
            raise HTTPException(500, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying system: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
async def get_status():
    try:
        logger.info("Fetching system status")
        result = backend_instance.get_system_status()
        
        if result["success"]:
            logger.info("Status fetched successfully")
            return {"status": "success", "system_status": result["status"]}
        else:
            raise HTTPException(500, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test-sample")
async def test_sample_default():
    """Test endpoint with configurable sample text using async processing."""
    try:
        content = settings.sample_text
        source_name = "sample-test"
        
        logger.info("Starting async sample text processing")
        result = await backend_instance.ingest_text(content=content, source_name=source_name)
        
        # Return the async processing response (same format as ingest-text)
        logger.info(f"Sample text processing started with ID: {result['processing_id']}")
        return result
    except Exception as e:
        logger.error(f"Error starting sample text processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest-text")
async def ingest_custom_text(request: TextIngestRequest):
    """Start async text ingestion and return processing ID."""
    try:
        logger.info(f"Starting async text ingestion: source='{request.source_name}'")
        result = await backend_instance.ingest_text(content=request.content, source_name=request.source_name)
        
        logger.info(f"Text ingestion started with ID: {result['processing_id']}")
        return result
    except Exception as e:
        logger.error(f"Error starting text ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/processing-status/{processing_id}")
async def get_processing_status(processing_id: str):
    """Get processing status by ID."""
    try:
        logger.info(f"Checking processing status for ID: {processing_id}")
        result = backend_instance.get_processing_status(processing_id)
        
        if result["success"]:
            logger.info(f"Status retrieved for {processing_id}: {result['processing']['status']}")
            return result["processing"]
        else:
            raise HTTPException(404, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting processing status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cancel-processing/{processing_id}")
async def cancel_processing(processing_id: str):
    """Cancel processing by ID."""
    try:
        logger.info(f"Cancelling processing for ID: {processing_id}")
        result = backend_instance.cancel_processing(processing_id)
        
        if result["success"]:
            logger.info(f"Processing {processing_id} cancelled successfully")
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(400, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cleanup-uploads")
async def cleanup_uploads_endpoint(keep_recent: int = 0):
    """Clean up uploaded files, optionally keeping most recent files"""
    try:
        cleanup_uploads(keep_recent_files=keep_recent)
        return {
            "success": True,
            "message": f"Upload cleanup completed - kept {keep_recent} recent files"
        }
    except Exception as e:
        logger.error(f"Error during upload cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/processing-events/{processing_id}")
async def processing_events(processing_id: str):
    """Server-Sent Events for real-time processing updates (UI clients only)."""
    from fastapi.responses import StreamingResponse
    import json
    import time
    
    def event_stream():
        while True:
            result = backend_instance.get_processing_status(processing_id)
            if result["success"]:
                status_data = result["processing"]
                yield f"data: {json.dumps(status_data)}\n\n"
                
                # Stop streaming if completed or failed
                if status_data["status"] in ["completed", "failed"]:
                    break
            else:
                yield f"data: {json.dumps({'error': result['error']})}\n\n"
                break
                
            time.sleep(2)  # Poll every 2 seconds
    
    return StreamingResponse(
        event_stream(), 
        media_type="text/plain",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/api/info")
async def get_api_info():
    """Get API information and available endpoints"""
    return {
        "name": "Flexible GraphRAG API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "ingest": "/api/ingest",
            "search": "/api/search", 
            "query": "/api/query",
            "status": "/api/status",
            "test_sample": "/api/test-sample",
            "python_info": "/api/python-info",
            "graph": "/api/graph"
        },
        "frontends": {
            "angular": "/angular",
            "react": "/react", 
            "vue": "/vue"
        },
        "mcp_server": "Available as separate fastmcp-server.py"
    }

@app.get("/api/graph")
async def get_graph_data(limit: int = 50):
    """Get graph data for visualization (nodes and relationships)"""
    try:
        # Check if system is initialized and has graph store
        if not hasattr(backend_instance, '_system') or backend_instance._system is None:
            return {"error": "System not initialized - please ingest documents first"}
        
        if not hasattr(backend_instance.system, 'graph_store') or backend_instance.system.graph_store is None:
            return {"error": "Graph database not configured"}
        
        # Check if it's Kuzu or Neo4j
        graph_store = backend_instance.system.graph_store
        
        # Detect database type
        graph_store_type = type(graph_store).__name__
        
        if "Kuzu" in graph_store_type or hasattr(graph_store, '_kuzu_db') or hasattr(graph_store, '_db'):
            # Try to get Kuzu database connection
            kuzu_db = None
            if hasattr(graph_store, 'db'):
                kuzu_db = graph_store.db
            elif hasattr(graph_store, '_kuzu_db'):
                kuzu_db = graph_store._kuzu_db
            elif hasattr(graph_store, '_db'):
                kuzu_db = graph_store._db
            elif hasattr(graph_store, 'client') and hasattr(graph_store.client, '_db'):
                kuzu_db = graph_store.client._db
            
            if kuzu_db is None:
                return {"error": f"Kuzu database not accessible in {graph_store_type}", "database": "kuzu"}
            
            try:
                # Query Kuzu database directly
                import kuzu
                conn = kuzu.Connection(kuzu_db)
                
                # Absolute simplest query - just check tables
                try:
                    # Use CALL statement to check database structure
                    result = conn.execute("CALL show_tables()")
                    tables_df = result.get_as_df()
                    tables = tables_df.to_dict('records') if not tables_df.empty else []
                    
                    return {
                        "database": "kuzu",
                        "store_type": graph_store_type,
                        "status": "connected",
                        "tables": tables,
                        "message": "Kuzu database accessible - use Kuzu Explorer at http://localhost:8002 for visualization"
                    }
                except Exception as table_error:
                    # Even simpler - just confirm connection works
                    return {
                        "database": "kuzu", 
                        "store_type": graph_store_type,
                        "status": "connected_basic",
                        "message": "Kuzu database connected but queries may have issues. Use Kuzu Explorer at http://localhost:8002",
                        "table_error": str(table_error)
                    }
            except Exception as e:
                return {"error": f"Error querying Kuzu: {str(e)}", "database": "kuzu", "store_type": graph_store_type}
                
        else:  # Neo4j or other
            return {"error": f"Graph visualization only implemented for Kuzu currently (detected: {graph_store_type})", "database": "other"}
            
    except Exception as e:
        return {"error": f"Error fetching graph data: {str(e)}"}

@app.get("/api/python-info")
async def python_info():
    """Return information about the Python interpreter being used."""
    # More reliable way to check if running in a virtual environment
    in_virtualenv = False
    venv_path = os.environ.get("VIRTUAL_ENV", "")
    
    # If VIRTUAL_ENV is set, use that
    if venv_path:
        in_virtualenv = True
    # Otherwise check if the Python executable is in a venv directory structure
    elif "venv" in sys.executable or "virtualenv" in sys.executable:
        in_virtualenv = True
        # Try to extract the venv path from the executable path
        venv_path = sys.executable
        if "\\Scripts\\" in venv_path:
            venv_path = venv_path.split("\\Scripts\\")[0]
        elif "/bin/" in venv_path:
            venv_path = venv_path.split("/bin/")[0]
    
    # Read requirements.txt
    requirements = []
    req_file_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if os.path.exists(req_file_path):
        with open(req_file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    requirements.append(line)
    
    # Get installed packages
    installed_packages: Dict[str, str] = {}
    try:
        for dist in importlib.metadata.distributions():
            try:
                name = dist.metadata["Name"].lower()
                installed_packages[name] = dist.version
            except (KeyError, AttributeError):
                # Skip packages with missing metadata
                pass
    except Exception as e:
        logger.warning(f"Error getting installed packages: {str(e)}")
        # Empty dict as fallback
        installed_packages = {}
    
    # Check requirements against installed packages
    req_status = []
    for req in requirements:
        original_req = req
        # Handle requirements with version specifiers
        if "==" in req:
            pkg_name, version_spec = req.split("==", 1)
            pkg_name = pkg_name.strip().lower()
        elif ">=" in req:
            pkg_name, version_spec = req.split(">=", 1)
            pkg_name = pkg_name.strip().lower()
        elif "[" in req:
            # Handle packages with extras like 'package[extra]'
            pkg_name = req.split("[", 1)[0].strip().lower()
        else:
            pkg_name = req.strip().lower()
        
        # For packages with extras, we need to check the base package name
        base_pkg_name = pkg_name.split("[")[0] if "[" in pkg_name else pkg_name
        
        installed_version = installed_packages.get(base_pkg_name)
        req_status.append({
            "name": pkg_name,
            "required": original_req,
            "installed": installed_version if installed_version else "Not installed"
        })
    
    return {
        "python_path": sys.executable,
        "python_version": sys.version,
        "virtual_env": venv_path if in_virtualenv else "Not in a virtual environment",
        "in_virtualenv": in_virtualenv,
        "requirements": req_status
    }

# Backend API only - no frontend serving
@app.get("/")
async def root():
    return {
        "message": "Flexible GraphRAG API", 
        "api": "/api",
        "info": "/api/info",
        "note": "Backend API only - use separate dev servers for UIs"
    }

if __name__ == "__main__":
    # Disable uvicorn's default logging to prevent duplicate messages
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_config=None,  # Disable uvicorn's default logging config
        access_log=False  # Disable access logging to reduce noise
    )
