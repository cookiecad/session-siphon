#!/usr/bin/env python3
"""
Backfill script to populate git_repo field in Typesense.

Run this script on each machine where source code is located (p16, office-desktop, home-pc).
It connects to the centralized Typesense instance, finds conversations belonging to this machine,
resolves the git repository for each project path locally, and updates the Typesense index.
"""

import sys
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

def backfill():
    setup_logging()
    config = load_config()
    
    logger.info("Starting backfill for machine_id: %s", config.machine_id)
    
    indexer = TypesenseIndexer(config.typesense)
    client = indexer.client
    
    # Verify connection
    try:
        client.health.retrieve()
        logger.info("Connected to Typesense at %s:%s", config.typesense.host, config.typesense.port)
    except Exception as e:
        logger.error("Failed to connect to Typesense: %s", e)
        return

    # Process 'conversations' collection
    process_collection(client, "conversations", config.machine_id)
    
    # Process 'messages' collection
    # Note: This might be huge. We might want to optimize by caching project->git_repo mappings
    process_collection(client, "messages", config.machine_id)

def process_collection(client, collection_name, machine_id):
    logger.info("Processing collection: %s", collection_name)
    
    # Cache for project path -> git repo
    repo_cache = {}
    
    page = 1
    per_page = 200
    updated_count = 0
    
    while True:
        # Search for docs from this machine
        # We process everything, even if git_repo exists, in case mapped path changed? 
        # Or optimization: filter_by: machine_id:=... && git_repo:=[is_null] (Typesense syntax depends on version)
        # Using simple filter for machine_id for now.
        
        search_params = {
            "q": "*",
            "filter_by": f"machine_id:={machine_id}",
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
            
            if not project:
                continue
                
            # Check cache
            if project in repo_cache:
                git_repo = repo_cache[project]
            else:
                git_repo = get_git_repo_info(project)
                repo_cache[project] = git_repo
                if git_repo:
                     logger.debug("Resolved %s -> %s", project, git_repo)
            
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
