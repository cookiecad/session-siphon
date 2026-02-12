
import sys
from pathlib import Path

# Add src to path if running from repo root
repo_root = Path(__file__).parent.parent
if (repo_root / "src").exists():
    sys.path.insert(0, str(repo_root / "src"))

from session_siphon.config import load_config
from session_siphon.processor.indexer import TypesenseIndexer

def update_schema():
    config = load_config()
    indexer = TypesenseIndexer(config.typesense)
    client = indexer.client
    
    print("Updating schema for 'conversations'...")
    try:
        client.collections['conversations'].update({
            'fields': [
                {"name": "git_repo", "type": "string", "facet": True, "optional": True}
            ]
        })
        print("Updated 'conversations' schema.")
    except Exception as e:
        print(f"Failed to update 'conversations': {e}")

    print("Updating schema for 'messages'...")
    try:
        client.collections['messages'].update({
            'fields': [
                {"name": "git_repo", "type": "string", "facet": True, "optional": True}
            ]
        })
        print("Updated 'messages' schema.")
    except Exception as e:
        print(f"Failed to update 'messages': {e}")

if __name__ == "__main__":
    update_schema()
