#!/bin/bash
# Set refresh interval for all datasources
# Usage: 
#   ./set-refresh-interval.sh --hours 1
#   ./set-refresh-interval.sh --minutes 30
#   ./set-refresh-interval.sh --seconds 120
#   ./set-refresh-interval.sh --hours 1 --minutes 30 --seconds 45
#   ./set-refresh-interval.sh 120  # Legacy: direct seconds

# Default values
HOURS=0
MINUTES=0
SECONDS=0
API_URL="http://localhost:8000"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --hours)
            HOURS="$2"
            shift 2
            ;;
        --minutes)
            MINUTES="$2"
            shift 2
            ;;
        --seconds)
            SECONDS="$2"
            shift 2
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --hours N       Set hours component"
            echo "  --minutes N     Set minutes component"
            echo "  --seconds N     Set seconds component"
            echo "  --api-url URL   API URL (default: http://localhost:8000)"
            echo ""
            echo "Examples:"
            echo "  $0 --hours 1"
            echo "  $0 --minutes 30"
            echo "  $0 --hours 1 --minutes 30 --seconds 45"
            echo "  $0 120  # Legacy: direct seconds"
            exit 0
            ;;
        *)
            # Legacy mode: first arg is seconds
            if [[ "$1" =~ ^[0-9]+$ ]] && [[ $SECONDS -eq 0 ]]; then
                SECONDS="$1"
                shift
            elif [[ -n "$1" ]] && [[ $SECONDS -eq 0 ]]; then
                API_URL="$1"
                shift
            else
                echo "Unknown argument: $1"
                exit 1
            fi
            ;;
    esac
done

# Calculate total seconds
TOTAL_SECONDS=$((HOURS * 3600 + MINUTES * 60 + SECONDS))

# Default to 60 seconds if nothing specified
if [ $TOTAL_SECONDS -eq 0 ]; then
    TOTAL_SECONDS=60
    echo "No interval specified, using default of 60 seconds"
fi

# Build human-readable string
INTERVAL_STR=""
if [ $HOURS -gt 0 ]; then
    INTERVAL_STR="${HOURS} hour(s)"
fi
if [ $MINUTES -gt 0 ]; then
    [ -n "$INTERVAL_STR" ] && INTERVAL_STR="${INTERVAL_STR}, "
    INTERVAL_STR="${INTERVAL_STR}${MINUTES} minute(s)"
fi
if [ $SECONDS -gt 0 ]; then
    [ -n "$INTERVAL_STR" ] && INTERVAL_STR="${INTERVAL_STR}, "
    INTERVAL_STR="${INTERVAL_STR}${SECONDS} second(s)"
fi
[ -z "$INTERVAL_STR" ] && INTERVAL_STR="${TOTAL_SECONDS} seconds"

echo "Setting refresh interval to ${INTERVAL_STR} (${TOTAL_SECONDS} total seconds) for all datasources..."

response=$(curl -s -X POST "$API_URL/api/datasource/update-all-refresh-intervals?seconds=$TOTAL_SECONDS")

if [ $? -eq 0 ]; then
    echo "✓ SUCCESS: Refresh interval updated."
    echo "$response" | jq . 2>/dev/null || echo "$response"
else
    echo "✗ ERROR: Failed to update refresh interval"
    exit 1
fi
