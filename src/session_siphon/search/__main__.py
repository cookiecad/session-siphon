"""CLI entry point for search.

Allows searching messages and conversations via command line.
"""

import sys
from datetime import datetime
from typing import Any

import click

from session_siphon.config import load_config
from session_siphon.logging import setup_logging
from session_siphon.processor.indexer import TypesenseIndexer


def format_timestamp(ts: int) -> str:
    """Format timestamp for display."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def print_message(hit: dict[str, Any], verbose: bool = False) -> None:
    """Print a message search hit."""
    doc = hit["document"]
    highlights = hit.get("highlights", [])
    
    # Use highlighted snippet if available
    content = doc["content"]
    for hl in highlights:
        if hl["field"] == "content":
            content = hl["snippet"]
            break
            
    # Clean up snippet tags for terminal
    content = content.replace("<mark>", "\033[1m").replace("</mark>", "\033[0m")
    
    click.echo(f"\033[36m[{format_timestamp(doc['ts'])}]\033[0m \033[32m{doc['source']}\033[0m ({doc['role']})")
    click.echo(f"Conversation: {doc['conversation_id']}")
    if verbose:
        click.echo(f"Project: {doc['project']}")
        click.echo(f"Path: {doc.get('raw_path', 'unknown')}")
        
    click.echo(f"\n{content}\n")
    click.echo("-" * 40)


def print_conversation(hit: dict[str, Any], verbose: bool = False) -> None:
    """Print a conversation search hit."""
    doc = hit["document"]
    
    click.echo(f"\033[36m[{format_timestamp(doc['last_ts'])}]\033[0m \033[1m{doc['title']}\033[0m")
    click.echo(f"Source: \033[32m{doc['source']}\033[0m | Messages: {doc['message_count']}")
    click.echo(f"ID: {doc['conversation_id']}")
    if verbose:
        click.echo(f"Project: {doc['project']}")
        
    click.echo(f"Preview: {doc['preview']}")
    click.echo("-" * 40)


@click.group()
def cli() -> None:
    """Search session history."""
    setup_logging("search")


@cli.command()
@click.argument("query")
@click.option("--source", help="Filter by source (e.g. claude_code, codex)")
@click.option("--role", help="Filter by role (user, assistant)")
@click.option("--project", help="Filter by project path")
@click.option("--limit", "-n", default=10, help="Number of results")
@click.option("--verbose", "-v", is_flag=True, help="Show more details")
def messages(query: str, source: str | None, role: str | None, project: str | None, limit: int, verbose: bool) -> None:
    """Search individual messages."""
    config = load_config()
    indexer = TypesenseIndexer(config.typesense)
    
    filters = {}
    if source:
        filters["source"] = source
    if role:
        filters["role"] = role
    if project:
        filters["project"] = project
        
    try:
        results = indexer.search_messages(query, per_page=limit, filters=filters)
    except Exception as e:
        click.echo(f"Error searching messages: {e}", err=True)
        sys.exit(1)
        
    found = results.get("found", 0)
    hits = results.get("hits", [])
    
    click.echo(f"Found {found} messages (showing {len(hits)}):\n")
    
    for hit in hits:
        print_message(hit, verbose)


@cli.command()
@click.argument("query")
@click.option("--source", help="Filter by source")
@click.option("--project", help="Filter by project path")
@click.option("--limit", "-n", default=10, help="Number of results")
@click.option("--verbose", "-v", is_flag=True, help="Show more details")
def conversations(query: str, source: str | None, project: str | None, limit: int, verbose: bool) -> None:
    """Search conversations."""
    config = load_config()
    indexer = TypesenseIndexer(config.typesense)
    
    filters = {}
    if source:
        filters["source"] = source
    if project:
        filters["project"] = project
        
    try:
        results = indexer.search_conversations(query, per_page=limit, filters=filters)
    except Exception as e:
        click.echo(f"Error searching conversations: {e}", err=True)
        sys.exit(1)
        
    found = results.get("found", 0)
    hits = results.get("hits", [])
    
    click.echo(f"Found {found} conversations (showing {len(hits)}):\n")
    
    for hit in hits:
        print_conversation(hit, verbose)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
