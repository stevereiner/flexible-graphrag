"""
Logging configuration for incremental update system.

Provides structured logging with proper formatting and levels.
"""

import logging
import sys
from pathlib import Path


class SuppressLlamaIndexRefDocWarning(logging.Filter):
    """Filter to suppress 'ref_doc_id not found, nothing deleted' warnings from LlamaIndex"""
    
    def filter(self, record):
        # Suppress the specific "ref_doc_id not found" warning
        if record.levelname == 'WARNING' and 'not found, nothing deleted' in record.getMessage():
            return False
        return True


def setup_logging(
    log_level: str = "INFO",
    log_file: str = None,
    enable_console: bool = True,
    enable_file: bool = True
):
    """
    Set up logging for the incremental update system.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (default: ./logs/incremental.log)
        enable_console: Enable console logging
        enable_file: Enable file logging
    """
    
    # Create logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Add custom filter to suppress specific LlamaIndex warnings
    suppress_filter = SuppressLlamaIndexRefDocWarning()
    
    # Create formatter with local timezone
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Note: %(asctime)s automatically uses local timezone
    
    simple_formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    # Note: Time shown is in your system's local timezone (EST if that's your system setting)
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        console_handler.addFilter(suppress_filter)  # Add filter
        root_logger.addHandler(console_handler)
    
    # File handler
    if enable_file:
        if log_file is None:
            log_file = "./logs/incremental.log"
        
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        file_handler.addFilter(suppress_filter)  # Add filter
        root_logger.addHandler(file_handler)
    
    # Set specific logger levels to reduce verbosity
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Suppress verbose LlamaIndex loggers
    logging.getLogger("llama_index").setLevel(logging.WARNING)
    logging.getLogger("llama_index.core").setLevel(logging.WARNING)
    logging.getLogger("llama_index.core.indices").setLevel(logging.WARNING)
    logging.getLogger("llama_index.core.indices.base").setLevel(logging.WARNING)
    logging.getLogger("llama_index.core.indices.property_graph").setLevel(logging.WARNING)
    
    # Apply filter to LlamaIndex loggers to suppress ref_doc not found warnings
    for llama_logger_name in ["llama_index", "llama_index.core", "llama_index.core.indices", 
                               "llama_index.core.indices.base", "llama_index.core.indices.property_graph"]:
        llama_logger = logging.getLogger(llama_logger_name)
        llama_logger.addFilter(suppress_filter)
    
    # Suppress database client verbose logging
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("neo4j.io").setLevel(logging.WARNING)
    logging.getLogger("neo4j.pool").setLevel(logging.WARNING)
    logging.getLogger("elastic_transport").setLevel(logging.WARNING)
    logging.getLogger("elasticsearch").setLevel(logging.WARNING)
    
    # Keep our own loggers at the requested level
    logging.getLogger("flexible_graphrag").setLevel(getattr(logging, log_level.upper()))
    
    return root_logger


def get_logger(name: str):
    """Get a logger for a specific module"""
    return logging.getLogger(name)


# Logging helpers
def log_operation_start(logger, operation: str, details: str = ""):
    """Log the start of an operation"""
    msg = f"▶️  Starting {operation}"
    if details:
        msg += f": {details}"
    logger.info(msg)


def log_operation_success(logger, operation: str, details: str = "", duration: float = None):
    """Log successful completion of an operation"""
    msg = f"✅ {operation} completed"
    if details:
        msg += f": {details}"
    if duration:
        msg += f" in {duration:.2f}s"
    logger.info(msg)


def log_operation_error(logger, operation: str, error: Exception, details: str = ""):
    """Log operation failure"""
    msg = f"❌ {operation} failed"
    if details:
        msg += f": {details}"
    msg += f" - {str(error)}"
    logger.error(msg)


def log_skip(logger, reason: str, details: str = ""):
    """Log skipped operation"""
    msg = f"⏭️  Skipping: {reason}"
    if details:
        msg += f" ({details})"
    logger.info(msg)


def log_processing(logger, item: str, action: str = "Processing"):
    """Log item processing"""
    logger.info(f"🔄 {action} {item}...")


def log_delete(logger, item: str):
    """Log deletion"""
    logger.info(f"🗑️  Deleting {item}...")


def log_update(logger, target: str, item: str = ""):
    """Log update operation"""
    msg = f"  📝 Updating {target}"
    if item:
        msg += f" for {item}"
    logger.info(msg)


def log_stats(logger, stats: dict):
    """Log statistics"""
    logger.info("📊 Statistics:")
    for key, value in stats.items():
        logger.info(f"    {key}: {value}")
