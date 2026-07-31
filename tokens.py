import subprocess
import os
import sys

def get_token(secret_name: str) -> str:
    """Fetch a token using the tokens cli."""
    try:
        result = subprocess.run(
            ['tokens', 'show', secret_name, '--value-only'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error fetching token {secret_name}: {e.stderr}", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print("Error: 'tokens' CLI not found. Make sure it's installed and in PATH.", file=sys.stderr)
        return ""

def get_cloudflare_account_id() -> str:
    return get_token('CLOUDFLARE_ACCOUNT_ID')

def get_cloudflare_wrangler_api_token() -> str:
    return get_token('CLOUDFLARE_WRANGLER_API_TOKEN')

if __name__ == "__main__":
    account_id = get_cloudflare_account_id()
    api_token = get_cloudflare_wrangler_api_token()
    
    if account_id:
        print(f"Successfully retrieved CLOUDFLARE_ACCOUNT_ID: {account_id[:5]}...")
    else:
        print("Failed to retrieve CLOUDFLARE_ACCOUNT_ID")
        
    if api_token:
        print(f"Successfully retrieved CLOUDFLARE_WRANGLER_API_TOKEN: {api_token[:5]}...")
    else:
        print("Failed to retrieve CLOUDFLARE_WRANGLER_API_TOKEN")
