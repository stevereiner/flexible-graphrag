#!/bin/bash
# Trigger immediate sync for all datasources with auto-sync enabled
# Usage: 
#   ./sync-now.sh
#   ./sync-now.sh --config-id alfresco_12345
#   ./sync-now.sh --config-id alfresco_12345 --api-url http://localhost:8000

# Default values
CONFIG_ID=""
API_URL="http://localhost:8000"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --config-id)
            CONFIG_ID="$2"
            shift 2
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --config-id ID  Sync specific datasource config (optional)"
            echo "  --api-url URL   API URL (default: http://localhost:8000)"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Sync all datasources"
            echo "  $0 --config-id alfresco_12345         # Sync specific datasource"
            exit 0
            ;;
        *)
            # Legacy mode: first arg is config_id
            if [[ -z "$CONFIG_ID" ]]; then
                CONFIG_ID="$1"
                shift
            else
                echo "Unknown argument: $1"
                exit 1
            fi
            ;;
    esac
done

if [ -n "$CONFIG_ID" ]; then
    echo "Triggering immediate sync for datasource: $CONFIG_ID..."
    ENDPOINT="$API_URL/api/datasource/$CONFIG_ID/sync-now"
else
    echo "Triggering immediate sync for all datasources with auto-sync enabled..."
    ENDPOINT="$API_URL/api/datasource/sync-now-all"
fi

response=$(curl -s -X POST "$ENDPOINT")

if [ $? -eq 0 ]; then
    echo "✓ SUCCESS: Sync triggered."
    echo "$response" | jq . 2>/dev/null || echo "$response"
else
    echo "✗ ERROR: Failed to trigger sync"
    exit 1
fi
