"""
Neptune Analytics Wrapper for LlamaIndex Integration

This module provides a wrapper for Neptune Analytics PropertyGraphStore to handle
vector operation limitations and compatibility issues with LlamaIndex.

The wrapper addresses:
1. Neptune Analytics' non-atomic vector index limitations
2. LlamaIndex's attempts to perform vector operations on Neptune Analytics
3. Property value serialization issues specific to Neptune Analytics
"""

import logging
import uuid
from typing import List, Any, Dict

logger = logging.getLogger(__name__)


class NeptuneAnalyticsNoVectorWrapper:
    """
    Wrapper for Neptune Analytics PropertyGraphStore that blocks vector operations
    and handles Neptune Analytics-specific limitations.
    
    This wrapper is necessary because:
    1. Neptune Analytics has non-atomic vector index updates
    2. LlamaIndex attempts vector operations even with embed_kg_nodes=False
    3. Neptune Analytics requires specific property value handling
    """
    
    def __init__(self, wrapped_store):
        self._wrapper_id = str(uuid.uuid4())[:8]
        self._wrapped = wrapped_store
        # Force disable vector support
        self.supports_vector_queries = False
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} initialized - all vector operations will be blocked")
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} wrapping object of type: {type(wrapped_store)}")
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} wrapped object methods: {[m for m in dir(wrapped_store) if not m.startswith('_')]}")
    
    def __getattr__(self, name):
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} __getattr__ called for '{name}'")
        # Block any vector-related methods completely
        if any(keyword in name.lower() for keyword in ['vector', 'embedding']):
            def blocked_method(*args, **kwargs):
                logger.warning(f"Neptune Analytics: Wrapper {self._wrapper_id} blocked vector operation '{name}' - vectors handled by separate VECTOR_DB")
                return None
            return blocked_method
        return getattr(self._wrapped, name)
    
    def __getattribute__(self, name):
        # Use object.__getattribute__ to avoid infinite recursion for internal attributes
        if name in ['_wrapped', 'supports_vector_queries', '_wrapper_id']:
            return object.__getattribute__(self, name)
        
        # Get wrapper ID for logging
        wrapper_id = object.__getattribute__(self, '_wrapper_id')
        
        # Log ALL attribute access attempts
        logger.info(f"Neptune Analytics: Wrapper {wrapper_id} __getattribute__ called for '{name}'")
        
        # Check if this is a method we want to override
        if name in ['upsert_nodes', 'upsert_llama_nodes', 'upsert_relations', 'get_llama_nodes', 'get_schema', 'vector_query', 'structured_query', 'query', 'get', 'add_node_embedding']:
            logger.info(f"Neptune Analytics: Wrapper {wrapper_id} returning overridden method '{name}'")
            return object.__getattribute__(self, name)
        
        # For other attributes, delegate to wrapped object
        return getattr(object.__getattribute__(self, '_wrapped'), name)
    
    def structured_query(self, query: str, param_map=None):
        """Override structured_query to block vector operations"""
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} structured_query called with query length: {len(query)}")
        # Check if this is a vector-related query
        if 'neptune.algo.vectors' in query or 'embedding' in query.lower():
            logger.warning(f"Neptune Analytics: Wrapper {self._wrapper_id} BLOCKED vector query - vectors handled by separate VECTOR_DB")
            logger.warning(f"Wrapper {self._wrapper_id} blocked query snippet: {query[:200]}...")
            # Return a successful empty result to avoid errors
            return []
        
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} allowing non-vector query to proceed")
        # Allow non-vector queries to proceed
        return self._wrapped.structured_query(query, param_map)
    
    def upsert_nodes(self, nodes):
        """Override upsert_nodes to completely block vector operations"""
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} upsert_nodes called with {len(nodes)} nodes")
        
        # CRITICAL: Override the upsert_nodes method to prevent ANY vector operations
        # Based on source code analysis, this method contains the problematic CALL neptune.algo.vectors.upsert
        
        try:
            # Create Neptune Analytics-compatible node storage queries directly
            for i, node in enumerate(nodes):
                # Create a basic node storage query without vector operations
                # Neptune Analytics requires individual SET statements for each property
                node_id = getattr(node, 'id_', getattr(node, 'id', f'node_{i}'))
                
                # Neptune Analytics: Handle labels differently than Neptune Database
                # Neptune Analytics uses single labels, Neptune Database uses multiple (__Node__, __Entity__, TYPE)
                node_label = "Entity"  # Default label for Neptune Analytics
                
                # Extract label from node if available - DEBUG LOGGING
                logger.debug(f"Neptune Analytics: Node {i+1} debug info:")
                logger.debug(f"  - Node type: {type(node)}")
                logger.debug(f"  - Node hasattr label: {hasattr(node, 'label')}")
                logger.debug(f"  - Node __dict__ keys: {list(node.__dict__.keys()) if hasattr(node, '__dict__') else 'No __dict__'}")
                
                if hasattr(node, 'label') and node.label:
                    node_label = str(node.label).replace(' ', '_').replace('-', '_')
                    logger.debug(f"  - Found node.label: '{node.label}' -> using '{node_label}'")
                elif hasattr(node, '__dict__') and 'label' in node.__dict__:
                    node_label = str(node.__dict__['label']).replace(' ', '_').replace('-', '_')
                    logger.debug(f"  - Found __dict__['label']: '{node.__dict__['label']}' -> using '{node_label}'")
                else:
                    logger.debug(f"  - No label found, using default 'Entity'")
                
                # Start with basic MERGE with Neptune Analytics label format
                node_query = f"MERGE (n:{node_label} {{id: $node_id}})"
                params = {'node_id': node_id}
                
                logger.info(f"Neptune Analytics: Using label '{node_label}' for node '{node_id}'")
                
                # Prepare node data without embeddings and complex objects
                simple_properties = []
                
                # Handle different node structures (some have direct properties, others have nested)
                node_data = {}
                if hasattr(node, '__dict__'):
                    node_data = node.__dict__
                elif hasattr(node, 'properties') and isinstance(node.properties, dict):
                    node_data = node.properties
                
                # Process all properties
                for k, v in node_data.items():
                    if k in ['embedding', '_embedding', 'id', 'id_']:
                        continue
                    # Skip complex objects that aren't JSON serializable
                    if k in ['relationships', 'excluded_embed_metadata_keys', 'excluded_llm_metadata_keys']:
                        continue
                    
                    # Handle simple data types
                    if isinstance(v, (str, int, float, bool, type(None))) and v is not None:
                        # Sanitize property name for Cypher
                        safe_key = k.replace('-', '_').replace(' ', '_')
                        param_name = f"prop_{safe_key}"
                        simple_properties.append(f"SET n.{safe_key} = ${param_name}")
                        params[param_name] = v
                    elif isinstance(v, dict):
                        # Flatten dict properties with prefixes (handle nested properties)
                        def flatten_dict(d, prefix=""):
                            for sub_k, sub_v in d.items():
                                full_key = f"{prefix}_{sub_k}" if prefix else sub_k
                                if isinstance(sub_v, (str, int, float, bool, type(None))) and sub_v is not None:
                                    safe_key = full_key.replace('-', '_').replace(' ', '_')
                                    param_name = f"prop_{safe_key}"
                                    simple_properties.append(f"SET n.{safe_key} = ${param_name}")
                                    params[param_name] = sub_v
                                elif isinstance(sub_v, dict):
                                    # Recursively flatten nested dicts
                                    flatten_dict(sub_v, full_key)
                                else:
                                    logger.debug(f"Skipping complex nested property: {full_key} (type: {type(sub_v)})")
                        
                        flatten_dict(v, k)
                    else:
                        logger.debug(f"Skipping complex property: {k} (type: {type(v)})")
                
                # Add all SET clauses to the query
                if simple_properties:
                    node_query += "\n" + "\n".join(simple_properties)
                
                node_query += "\nRETURN n"
                
                logger.debug(f"Neptune Analytics: Wrapper {self._wrapper_id} storing node {i+1}/{len(nodes)} without vectors")
                logger.debug(f"Neptune Analytics: Final query: {node_query}")
                logger.debug(f"Neptune Analytics: Final params: {params}")
                
                result = self._wrapped.structured_query(node_query, params)
                logger.debug(f"Neptune Analytics: Query result: {result}")
            
            logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} successfully stored {len(nodes)} nodes without vector operations")
            return None
            
        except Exception as e:
            logger.error(f"Neptune Analytics: Wrapper {self._wrapper_id} error in custom upsert_nodes: {e}")
            logger.error(f"Neptune Analytics: Error type: {type(e)}")
            import traceback
            logger.error(f"Neptune Analytics: Full traceback: {traceback.format_exc()}")
            
            # Instead of falling back to the problematic original method, let's try a simpler approach
            logger.info("Neptune Analytics: Attempting simplified node storage without fallback to original method")
            try:
                for i, node in enumerate(nodes):
                    # Ultra-simple approach: just store the node ID and basic info
                    simple_query = "MERGE (n {id: $node_id}) SET n.stored = true RETURN n"
                    node_id = getattr(node, 'id_', getattr(node, 'id', f'node_{i}'))
                    simple_params = {'node_id': str(node_id)}
                    
                    logger.debug(f"Neptune Analytics: Simplified storage for node {i+1}/{len(nodes)}: {node_id}")
                    self._wrapped.structured_query(simple_query, simple_params)
                
                logger.info(f"Neptune Analytics: Successfully stored {len(nodes)} nodes with simplified approach")
                return None
            except Exception as e2:
                logger.error(f"Neptune Analytics: Even simplified approach failed: {e2}")
                # Last resort: return None to avoid calling the original problematic method
                return None
    
    def upsert_llama_nodes(self, nodes):
        """Override upsert_llama_nodes to completely block vector operations"""
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} upsert_llama_nodes called with {len(nodes)} nodes")
        
        # CRITICAL: This is the method that's actually being called by LlamaIndex!
        # It contains the same problematic CALL neptune.algo.vectors.upsert
        
        try:
            # Create Neptune Analytics-compatible node storage queries directly
            for i, node in enumerate(nodes):
                # Create a basic node storage query without vector operations
                # Neptune Analytics requires individual SET statements for each property
                node_id = getattr(node, 'id_', getattr(node, 'id', f'node_{i}'))
                
                # Neptune Analytics: Handle labels differently than Neptune Database
                # Neptune Analytics uses single labels, Neptune Database uses multiple (__Node__, __Entity__, TYPE)
                node_label = "Entity"  # Default label for Neptune Analytics
                
                # Extract label from node if available - DEBUG LOGGING
                logger.debug(f"Neptune Analytics: Node {i+1} debug info:")
                logger.debug(f"  - Node type: {type(node)}")
                logger.debug(f"  - Node hasattr label: {hasattr(node, 'label')}")
                logger.debug(f"  - Node __dict__ keys: {list(node.__dict__.keys()) if hasattr(node, '__dict__') else 'No __dict__'}")
                
                if hasattr(node, 'label') and node.label:
                    node_label = str(node.label).replace(' ', '_').replace('-', '_')
                    logger.debug(f"  - Found node.label: '{node.label}' -> using '{node_label}'")
                elif hasattr(node, '__dict__') and 'label' in node.__dict__:
                    node_label = str(node.__dict__['label']).replace(' ', '_').replace('-', '_')
                    logger.debug(f"  - Found __dict__['label']: '{node.__dict__['label']}' -> using '{node_label}'")
                else:
                    logger.debug(f"  - No label found, using default 'Entity'")
                
                # Start with basic MERGE with Neptune Analytics label format
                node_query = f"MERGE (n:{node_label} {{id: $node_id}})"
                params = {'node_id': node_id}
                
                logger.info(f"Neptune Analytics: Using label '{node_label}' for node '{node_id}'")
                
                # Prepare node data without embeddings and complex objects
                simple_properties = []
                
                # Handle different node structures (some have direct properties, others have nested)
                node_data = {}
                if hasattr(node, '__dict__'):
                    node_data = node.__dict__
                elif hasattr(node, 'properties') and isinstance(node.properties, dict):
                    node_data = node.properties
                
                # Process all properties
                for k, v in node_data.items():
                    if k in ['embedding', '_embedding', 'id', 'id_']:
                        continue
                    # Skip complex objects that aren't JSON serializable
                    if k in ['relationships', 'excluded_embed_metadata_keys', 'excluded_llm_metadata_keys']:
                        continue
                    
                    # Handle simple data types
                    if isinstance(v, (str, int, float, bool, type(None))) and v is not None:
                        # Sanitize property name for Cypher
                        safe_key = k.replace('-', '_').replace(' ', '_')
                        param_name = f"prop_{safe_key}"
                        simple_properties.append(f"SET n.{safe_key} = ${param_name}")
                        params[param_name] = v
                    elif isinstance(v, dict):
                        # Flatten dict properties with prefixes (handle nested properties)
                        def flatten_dict(d, prefix=""):
                            for sub_k, sub_v in d.items():
                                full_key = f"{prefix}_{sub_k}" if prefix else sub_k
                                if isinstance(sub_v, (str, int, float, bool, type(None))) and sub_v is not None:
                                    safe_key = full_key.replace('-', '_').replace(' ', '_')
                                    param_name = f"prop_{safe_key}"
                                    simple_properties.append(f"SET n.{safe_key} = ${param_name}")
                                    params[param_name] = sub_v
                                elif isinstance(sub_v, dict):
                                    # Recursively flatten nested dicts
                                    flatten_dict(sub_v, full_key)
                                else:
                                    logger.debug(f"Skipping complex nested property: {full_key} (type: {type(sub_v)})")
                        
                        flatten_dict(v, k)
                    else:
                        logger.debug(f"Skipping complex property: {k} (type: {type(v)})")
                
                # Add all SET clauses to the query
                if simple_properties:
                    node_query += "\n" + "\n".join(simple_properties)
                
                node_query += "\nRETURN n"
                
                logger.debug(f"Neptune Analytics: Wrapper {self._wrapper_id} storing llama node {i+1}/{len(nodes)} without vectors")
                self._wrapped.structured_query(node_query, params)
            
            logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} successfully stored {len(nodes)} llama nodes without vector operations")
            return None
            
        except Exception as e:
            logger.error(f"Neptune Analytics: Wrapper {self._wrapper_id} error in custom upsert_llama_nodes: {e}")
            # Fallback: try to clean nodes and call original method
            clean_nodes = []
            for node in nodes:
                if hasattr(node, 'embedding'):
                    node.embedding = None
                clean_nodes.append(node)
            return self._wrapped.upsert_llama_nodes(clean_nodes)
    
    def get_llama_nodes(self, node_ids, **kwargs):
        """Override get_llama_nodes to ensure no vector operations"""
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} get_llama_nodes called for {len(node_ids) if hasattr(node_ids, '__len__') else 'unknown'} node IDs")
        
        # Allow get operations to proceed normally - they shouldn't involve vector operations
        return self._wrapped.get_llama_nodes(node_ids, **kwargs)
    
    def upsert_relations(self, relations):
        """Override upsert_relations to handle Neptune Analytics relationship format"""
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} upsert_relations called with {len(relations)} relations")
        
        # Allow relationship operations to proceed normally - they typically don't involve vector operations
        # But add logging to debug any issues
        try:
            result = self._wrapped.upsert_relations(relations)
            logger.info(f"Neptune Analytics: Successfully stored {len(relations)} relations")
            return result
        except Exception as e:
            logger.error(f"Neptune Analytics: Error in upsert_relations: {e}")
            logger.error(f"Neptune Analytics: Relations data: {relations}")
            raise
    
    def get_schema(self, refresh: bool = False):
        """Override get_schema to handle Neptune Analytics schema format"""
        logger.info(f"Neptune Analytics: Wrapper {self._wrapper_id} get_schema called (refresh={refresh})")
        
        try:
            result = self._wrapped.get_schema(refresh)
            logger.info(f"Neptune Analytics: get_schema successful, result type: {type(result)}")
            logger.debug(f"Neptune Analytics: Schema result: {result}")
            return result
        except Exception as e:
            logger.error(f"Neptune Analytics: Error in get_schema: {e}")
            logger.error(f"Neptune Analytics: Error type: {type(e)}")
            import traceback
            logger.error(f"Neptune Analytics: Full traceback: {traceback.format_exc()}")
            
            # Return a minimal schema to avoid breaking the system
            logger.warning("Neptune Analytics: Returning minimal schema due to error")
            return ""
    
    # Override any other methods that might be called
    def query(self, *args, **kwargs):
        logger.info("Neptune Analytics: query method called")
        return self._wrapped.query(*args, **kwargs)
    
    def get(self, *args, **kwargs):
        logger.info("Neptune Analytics: get method called")  
        return self._wrapped.get(*args, **kwargs)
    
    # Block all vector-related methods explicitly
    def vector_query(self, query, **kwargs):
        """Override vector_query to completely block vector operations"""
        logger.warning(f"Neptune Analytics: Wrapper {self._wrapper_id} BLOCKED vector_query - vectors handled by separate VECTOR_DB")
        logger.warning(f"Blocked vector_query with query: {query}")
        # Return empty result to avoid errors
        return ([], [])
    
    def add_node_embedding(self, *args, **kwargs):
        logger.warning("Neptune Analytics: add_node_embedding blocked - use separate VECTOR_DB")
        return None
    
    def get_node_embedding(self, *args, **kwargs):
        logger.warning("Neptune Analytics: get_node_embedding blocked - use separate VECTOR_DB")
        return None
