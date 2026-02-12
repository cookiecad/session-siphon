#!/usr/bin/env python3
"""
Backfill script to populate git_repo field in Typesense.

Run this script on each machine where source code is located (p16, office-desktop, home-pc).
It connects to the centralized Typesense instance, finds conversations belonging to this machine,
resolves the git repository for each project path locally, and updates the Typesense index.
"""

import sys
import subprocess
import shlex
from functools import lru_cache
from pathlib import Path

# Add src to path if running from repo root
repo_root = Path(__file__).parent.parent
if (repo_root / "src").exists():
    sys.path.insert(0, str(repo_root / "src"))

from session_siphon.config import load_config
from session_siphon.logging import setup_logging, get_logger
from session_siphon.processor.indexer import TypesenseIndexer
from session_siphon.processor.git_utils import get_git_repo_info

logger = get_logger("backfill")

@lru_cache(maxsize=1024)
def get_remote_git_repo_info(machine_id: str, project_path: str) -> str | None:
    """Get git repo info from a remote machine via SSH."""
    cmd = f"git -C {shlex.quote(project_path)} config --get remote.origin.url"
    ssh_cmd = ["ssh", machine_id, cmd]
    
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=5,  # Short timeout for responsiveness
            check=False
        )
        
        url = result.stdout.strip()
        if url:
             # Parse URL to get owner/repo
             # Remove .git suffix
            if url.endswith(".git"):
                url = url[:-4]
            
            parts = url.split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
            return parts[-1]
            
    except Exception as e:
        logger.debug("Remote git check failed for %s:%s - %s", machine_id, project_path, e)
        
    return None

def backfill():
    setup_logging("backfill")
    config = load_config()
    
    logger.info("Starting centralized backfill from machine: %s", config.machine_id)
    
    indexer = TypesenseIndexer(config.typesense)
    client = indexer.client
    
    # Verify connection
    try:
        client.collections.retrieve()
        logger.info("Connected to Typesense at %s:%s", config.typesense.host, config.typesense.port)
    except Exception as e:
        logger.error("Failed to connect to Typesense: %s", e)
        return

    # Process 'conversations' collection
    process_collection(client, "conversations", config.machine_id)
    
    # Process 'messages' collection
    process_collection(client, "messages", config.machine_id)

def process_collection(client, collection_name, local_machine_id):
    logger.info("Processing collection: %s", collection_name)
    
    # Cache for project path -> git repo
    # Key: (machine_id, project_path) -> git_repo
    repo_cache = {}
    
    page = 1
    per_page = 200
    updated_count = 0
    
    while True:
        # Search for ALL docs (remove machine_id filter)
        search_params = {
            "q": "*",
            "per_page": per_page,
            "page": page,
        }
        
        try:
            results = client.collections[collection_name].documents.search(search_params)
        except Exception as e:
            logger.error("Search failed: %s", e)
            break
            
        hits = results.get("hits", [])
        if not hits:
            break
            
        logger.info("Page %d: Found %d documents", page, len(hits))
        
        batch_updates = []
        
        for hit in hits:
            doc = hit["document"]
            doc_id = doc["id"]
            project = doc.get("project", "")
            machine_id = doc.get("machine_id", "unknown")
            
            if not project or not machine_id:
                continue
                
            # Check cache
            cache_key = (machine_id, project)
            if cache_key in repo_cache:
                git_repo = repo_cache[cache_key]
            else:
                if machine_id == local_machine_id:
                    git_repo = get_git_repo_info(project)
                else:
                    git_repo = get_remote_git_repo_info(machine_id, project)
                
                repo_cache[cache_key] = git_repo
                if git_repo:
                     logger.debug("Resolved %s:%s -> %s", machine_id, project, git_repo)
            
            # If we found a repo and it's different/missing, update
            current_repo = doc.get("git_repo")
            if git_repo and git_repo != current_repo:
                batch_updates.append({"id": doc_id, "git_repo": git_repo})
        
        if batch_updates:
            logger.info("Updating %d documents in this batch...", len(batch_updates))
            try:
                client.collections[collection_name].documents.import_(batch_updates, {"action": "update"})
                updated_count += len(batch_updates)
            except Exception as e:
                logger.error("Batch update failed: %s", e)
        
        # Next page
        if len(hits) < per_page:
            break
        page += 1

    logger.info("Finished collection %s. Updated %d total.", collection_name, updated_count)

if __name__ == "__main__":
    backfill()
