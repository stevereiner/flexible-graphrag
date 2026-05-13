"""
Neptune Database Wrapper for LlamaIndex Integration

This module provides a wrapper for Neptune Database PropertyGraphStore to handle
summary API limitations when statistics are disabled.

The wrapper addresses:
1. Neptune Database's Summary API requirement for engine version >= 1.2.1.0
2. Statistics being disabled on Neptune instances
3. LlamaIndex's attempts to refresh schema using get_propertygraph_summary()
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NeptuneDatabaseNoSummaryWrapper:
    """
    Wrapper for Neptune Database PropertyGraphStore that handles Summary API errors.
    
    This wrapper is necessary because:
    1. Neptune Database Summary API requires statistics to be enabled
    2. Statistics not available on lowest cost neptune instance classes (db.t3.medium and db.t4g.medium)
    3. Neptune Database Summary API requires engine version >= 1.2.1.0 (not likely latest is 1.4.6.3.R1)
    4. Neptune LlamaIndex code calls the get summary api unconditionally
    """
    
    def __init__(self, wrapped_store):
        self._wrapped = wrapped_store
        logger.info("Neptune Database: Wrapper initialized - schema refresh errors will be handled gracefully")
        logger.info(f"Neptune Database: Wrapping object of type: {type(wrapped_store)}")
        
        # Runtime override the _get_summary method directly on the wrapped object
        # This is necessary because internal method calls don't go through __getattribute__
        original_get_summary = wrapped_store._get_summary
        
        def patched_get_summary():
            logger.info("Neptune Database: Patched _get_summary called")
            try:
                result = original_get_summary()
                # Log the results from the real Summary API
                node_labels = result.get("nodeLabels", [])
                edge_labels = result.get("edgeLabels", [])
                logger.info(f"Neptune Database: Real Summary API returned {len(node_labels)} node labels: {node_labels}")
                logger.info(f"Neptune Database: Real Summary API returned {len(edge_labels)} edge labels: {edge_labels}")
                return result
            except Exception as e:
                error_str = str(e)
                if 'Summary API is not available' in error_str or 'Statistics are disabled' in error_str:
                    logger.warning("Neptune Database: Summary API not available - querying graph directly for summary")
                    
                    # Query the graph directly to get actual node labels and edge labels
                    try:
                        # Get actual node labels from the graph
                        node_labels_query = """
                        MATCH (n)
                        WITH DISTINCT labels(n) AS labels
                        UNWIND labels AS label
                        RETURN DISTINCT label
                        LIMIT 1000
                        """
                        
                        # Get actual edge labels (relationship types) from the graph
                        edge_labels_query = """
                        MATCH ()-[r]->()
                        RETURN DISTINCT type(r) AS relType
                        LIMIT 1000
                        """
                        
                        node_labels = []
                        edge_labels = []
                        
                        # Query node labels
                        try:
                            node_result = wrapped_store.query(node_labels_query)
                            for record in node_result:
                                if hasattr(record, 'get'):
                                    label = record.get('label')
                                elif isinstance(record, dict):
                                    label = record.get('label')
                                else:
                                    label = record[0] if len(record) > 0 else None
                                
                                if label and label not in node_labels:
                                    node_labels.append(label)
                            logger.info(f"Neptune Database: Workaround query found {len(node_labels)} node labels: {node_labels}")
                        except Exception as ne:
                            logger.warning(f"Neptune Database: Could not query node labels: {ne}")
                        
                        # Query edge labels
                        try:
                            edge_result = wrapped_store.query(edge_labels_query)
                            for record in edge_result:
                                if hasattr(record, 'get'):
                                    rel_type = record.get('relType')
                                elif isinstance(record, dict):
                                    rel_type = record.get('relType')
                                else:
                                    rel_type = record[0] if len(record) > 0 else None
                                
                                if rel_type and rel_type not in edge_labels:
                                    edge_labels.append(rel_type)
                            logger.info(f"Neptune Database: Workaround query found {len(edge_labels)} edge labels: {edge_labels}")
                        except Exception as ee:
                            logger.warning(f"Neptune Database: Could not query edge labels: {ee}")
                        
                        logger.info(f"Neptune Database: Workaround returning summary - nodeLabels: {node_labels}, edgeLabels: {edge_labels}")
                        return {
                            "nodeLabels": node_labels,
                            "edgeLabels": edge_labels
                        }
                        
                    except Exception as query_error:
                        logger.error(f"Neptune Database: Failed to query graph for summary: {query_error}")
                        # Return empty lists as fallback
                        return {
                            "nodeLabels": [],
                            "edgeLabels": []
                        }
                else:
                    logger.error(f"Neptune Database: Unexpected error in _get_summary: {e}")
                    raise
        
        wrapped_store._get_summary = patched_get_summary
        logger.info("Neptune Database: Runtime override applied to _get_summary method")
    
    def __getattr__(self, name):
        """Delegate all attribute access to the wrapped store"""
        return getattr(self._wrapped, name)
