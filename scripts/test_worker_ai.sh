set -a; source .env; set +a; curl -X POST "https://gateway.ai.cloudflare.com/v1/${CLOUDFLARE_ACCOUNT_ID}/${CLOUDFLARE_GATEWAY_NAME}/compat/chat/completions" \
  --header "cf-aig-authorization: Bearer ${CLOUDFLARE_AI_GATEWAY_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "messages": [
      {
        "role": "user",
        "content": "What is Cloudflare?"
      }
    ]
  }'
