#!/usr/bin/env python3
"""
Script to create the 'flexible_graphrag' space in NebulaGraph.
This script connects to NebulaGraph and creates the required space for Flexible GraphRAG.
"""

import sys
import time
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

def create_nebula_space():
    """Create the flexible_graphrag space in NebulaGraph"""
    
    # Configuration
    config = Config()
    config.max_connection_pool_size = 10
    
    # Connection parameters
    host = "localhost"
    port = 9669
    username = "root"
    password = "nebula"
    space_name = "flexible_graphrag"
    
    # Initialize connection pool
    connection_pool = ConnectionPool()
    
    try:
        # Connect to NebulaGraph
        print(f"Connecting to NebulaGraph at {host}:{port}...")
        if not connection_pool.init([(host, port)], config):
            print("ERROR: Failed to initialize connection pool")
            return False
        
        # Get session
        session = connection_pool.get_session(username, password)
        if session is None:
            print("ERROR: Failed to get session")
            return False
        
        print("Connected successfully!")
        
        # Check if space already exists
        print("Checking existing spaces...")
        result = session.execute("SHOW SPACES;")
        if not result.is_succeeded():
            print(f"ERROR: Failed to show spaces: {result.error_msg()}")
            return False
        
        existing_spaces = []
        if result.data():
            for row in result.data():
                space_info = row.values[0].as_string()  # Space name is in first column
                existing_spaces.append(space_info)
                print(f"  Found space: {space_info}")
        
        if space_name in existing_spaces:
            print(f"Space '{space_name}' already exists!")
            return True
        
        # Create the space
        print(f"Creating space '{space_name}'...")
        create_space_query = f"""
        CREATE SPACE IF NOT EXISTS {space_name} (
            partition_num = 15,
            replica_factor = 1,
            vid_type = FIXED_STRING(64)
        ) COMMENT = "Flexible GraphRAG knowledge graph space";
        """
        
        result = session.execute(create_space_query)
        if not result.is_succeeded():
            print(f"ERROR: Failed to create space: {result.error_msg()}")
            return False
        
        print(f"Space '{space_name}' created successfully!")
        
        # Wait a moment for the space to be ready
        print("Waiting for space to be ready...")
        time.sleep(3)
        
        # Verify the space was created
        result = session.execute("SHOW SPACES;")
        if result.is_succeeded() and result.data():
            spaces_after = []
            for row in result.data():
                space_info = row.values[0].as_string()
                spaces_after.append(space_info)
            
            if space_name in spaces_after:
                print(f"✅ Verification successful: Space '{space_name}' is now available!")
                return True
            else:
                print(f"❌ Verification failed: Space '{space_name}' not found after creation")
                return False
        
        return True
        
    except Exception as e:
        print(f"ERROR: Exception occurred: {str(e)}")
        return False
    
    finally:
        # Clean up
        if 'session' in locals():
            session.release()
        connection_pool.close()

def main():
    """Main function"""
    print("NebulaGraph Space Creation Script")
    print("=" * 40)
    
    success = create_nebula_space()
    
    if success:
        print("\n✅ SUCCESS: NebulaGraph space setup completed!")
        print("\nYou can now use NebulaGraph with Flexible GraphRAG.")
        print("Make sure your .env file has:")
        print('GRAPH_DB=nebula')
        print('GRAPH_DB_CONFIG={"space": "flexible_graphrag", "address": "localhost", "port": 9669, "username": "root", "password": "nebula"}')
        sys.exit(0)
    else:
        print("\n❌ FAILED: Could not create NebulaGraph space")
        print("\nTroubleshooting:")
        print("1. Make sure NebulaGraph is running (docker-compose up nebula-metad nebula-storaged nebula-graphd)")
        print("2. Check that port 9669 is accessible")
        print("3. Verify the credentials (username: root, password: nebula)")
        sys.exit(1)

if __name__ == "__main__":
    main()
