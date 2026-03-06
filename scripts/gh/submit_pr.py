import os
import sys
import json
import time
import subprocess
import requests

# --- Configuration ---
CLOUDFLARE_API_TOKEN = os.getenv("CF_API_TOKEN")
ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "jmbish04"
REPO_NAME = "dopamine-hardware"
AI_MODEL = "@cf/meta/llama-3.1-8b-instruct"

def run_cmd(command):
    """Executes a shell command safely."""
    try:
        if isinstance(command, str):
            result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        else:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {command}\nError: {e.stderr.strip()}")
        sys.exit(1)

def get_git_state():
    """Stages all changes and extracts the diff and current branch."""
    print("📦 Staging local changes...")
    run_cmd("git add .")
    
    # Exclude binaries from the diff so we don't blow out the AI context window
    diff = run_cmd("git diff --staged -- diff-filter=d")
    if not diff:
        print("⚠️ No changes to commit. Exiting.")
        sys.exit(0)
        
    base_branch = run_cmd("git rev-parse --abbrev-ref HEAD")
    return diff, base_branch

def generate_pr_content(diff):
    """Calls Cloudflare Workers AI to generate PR metadata from the git diff."""
    print("🧠 Analyzing diff with Cloudflare Workers AI...")
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{AI_MODEL}"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "You are a Codex Senior Engineer. Analyze the provided git diff and generate a Pull Request title and description. "
        "The description must be formatted in Markdown and MUST include a specific section titled '## System Exports' "
        "that explicitly lists any environment variables, exported modules, updated dependencies, or configuration constants "
        "found in the diff."
    )
    
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Git Diff:\n{diff[:5000]}"} 
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "type": "object",
                "properties": {
                    "title": { "type": "string" },
                    "description": { "type": "string" }
                },
                "required": ["title", "description"]
            }
        }
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"❌ Cloudflare API Error: {response.status_code} - {response.text}")
        sys.exit(1)
        
    response_data = response.json().get("result", {}).get("response", "")
    
    if isinstance(response_data, dict):
        data = response_data
    else:
        # Fallback: Clean markdown wrappers and parse with strict=False to allow unescaped newlines
        cleaned = response_data.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
            
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
            
        cleaned = cleaned.strip()
        
        try:
            data = json.loads(cleaned, strict=False)
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse AI response as JSON: {e}")
            print("Raw output:")
            print(response_data)
            sys.exit(1)
            
    title = data.get("title", "Automated PR")
    description = data.get("description", "No description provided.")
    
    print("\n✨ --- AI Generated Pull Request --- ✨")
    print(f"✨ Title: {title}\n")
    print(f"✨ Description:\n{description}\n✨ --------------------------------- ✨\n")
    
    return title, description

def create_github_pr(title, description, head_branch, base_branch):
    """Opens a PR using the GitHub REST API."""
    print(f"📝 Opening Pull Request against '{base_branch}'...")
    gh_url = f"[https://api.github.com/repos/](https://api.github.com/repos/){REPO_OWNER}/{REPO_NAME}/pulls"
    gh_headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    gh_payload = {
        "title": title,
        "body": description,
        "head": head_branch,
        "base": base_branch
    }
    
    gh_response = requests.post(gh_url, headers=gh_headers, json=gh_payload)
    
    if gh_response.status_code == 201:
        pr_url = gh_response.json().get("html_url")
        print(f"✅ Successfully opened PR: {pr_url}")
    else:
        print(f"❌ Failed to open PR: {gh_response.status_code} - {gh_response.text}")

def main():
    if not all([CLOUDFLARE_API_TOKEN, ACCOUNT_ID, GITHUB_TOKEN]):
        print("❌ Missing required environment variables: CF_API_TOKEN, CF_ACCOUNT_ID, GITHUB_TOKEN")
        sys.exit(1)
        
    diff, base_branch = get_git_state()
    title, description = generate_pr_content(diff)
    
    branch_name = f"feature/auto-pr-{int(time.time())}"
    
    print(f"🌿 Creating and switching to branch: {branch_name}")
    run_cmd(f"git checkout -b {branch_name}")
    
    print(f"💾 Committing changes with AI-generated title...")
    run_cmd(["git", "commit", "-m", title])
    
    print(f"🚀 Pushing branch to origin...")
    run_cmd(f"git push -u origin {branch_name}")
    
    create_github_pr(title, description, branch_name, base_branch)

if __name__ == "__main__":
    main()
