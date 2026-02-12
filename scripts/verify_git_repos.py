
import sys
from pathlib import Path

# Add src to path if running from repo root
repo_root = Path(__file__).parent.parent
if (repo_root / "src").exists():
    sys.path.insert(0, str(repo_root / "src"))

from session_siphon.config import load_config
from session_siphon.processor.indexer import TypesenseIndexer

def verify():
    config = load_config()
    indexer = TypesenseIndexer(config.typesense)
    client = indexer.client
    
    print("Verifying 'conversations' collection...")
    results = client.collections['conversations'].documents.search({
        'q': '*',
        'filter_by': 'git_repo:!=null',
        'per_page': 5
    })
    
    hits = results.get('hits', [])
    print(f"Found {results.get('found', 0)} conversations with git_repo set.")
    for hit in hits:
        doc = hit['document']
        print(f" - [{doc['machine_id']}] {doc['project']} -> {doc.get('git_repo')}")

    print("\nVerifying 'messages' collection...")
    results = client.collections['messages'].documents.search({
        'q': '*',
        'filter_by': 'git_repo:!=null',
        'per_page': 5
    })
    
    hits = results.get('hits', [])
    print(f"Found {results.get('found', 0)} messages with git_repo set.")
    for hit in hits:
        doc = hit['document']
        print(f" - [{doc['machine_id']}] {doc['project']} -> {doc.get('git_repo')}")

if __name__ == "__main__":
    verify()
