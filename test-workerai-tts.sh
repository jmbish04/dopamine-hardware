#!/bin/bash
# ==============================================================================
# File: scripts/query-cloudflare-model.sh
# Description: Queries the Cloudflare REST API for Workers AI model details and 
#              schema for @cf/deepgram/aura-2-en.
# ==============================================================================

set -e

# 1. Dependency Check
if ! command -v jq &> /dev/null; then
    echo "Error: 'jq' is not installed. Please install jq to format the JSON output."
    exit 1
fi
if ! command -v curl &> /dev/null; then
    echo "Error: 'curl' is not installed. Please install curl to make API requests."
    exit 1
fi

echo "Retrieving Cloudflare credentials from vault..."

# 2. Credential Ingestion (Using specified vault commands)
ACCOUNT_ID=$(tokens show CLOUFLARE_ACCOUNT_ID --value-only)
API_TOKEN=$(tokens show CLOUFLARE_AI_GATEWAY_TOKEN --value-only)

if [ -z "$ACCOUNT_ID" ] || [ -z "$API_TOKEN" ]; then
    echo "Error: Failed to retrieve Cloudflare credentials. Verify your token vault."
    exit 1
fi

# 3. Model Configuration
MODEL="@cf/deepgram/aura-2-en"
# URL encode the model name since it contains '@' and '/' which break path/query parameters
ENCODED_MODEL="%40cf%2Fdeepgram%2Faura-2-en"

echo "========================================================================"
echo " Querying Cloudflare Workers AI"
echo " Target Model: $MODEL"
echo "========================================================================"

echo ""
echo "=> 1. Fetching Model Metadata (/ai/models/search) ..."
# The search endpoint returns general model registry data, limits, and operational status.
curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/ai/models/search?search=$ENCODED_MODEL" \
     -H "Authorization: Bearer $API_TOKEN" \
     -H "Content-Type: application/json" | jq '.'

echo ""
echo "=> 2. Fetching Model Input/Output Schema (/ai/models/schema) ..."
# The schema endpoint returns the precise OpenAPI-compatible JSON schema for prompt payloads.
curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/ai/models/schema?model=$ENCODED_MODEL" \
     -H "Authorization: Bearer $API_TOKEN" \
     -H "Content-Type: application/json" | jq '.'

echo ""
echo "========================================================================"
echo " Execution Complete."
echo "========================================================================"
