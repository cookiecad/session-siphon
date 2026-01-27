"""Parsers for different AI conversation transcript formats."""

from .antigravity import AntigravityParser
from .base import CanonicalMessage, Parser, ParserRegistry, content_hash, generate_message_id
from .claude_code import ClaudeCodeParser
from .codex import CodexParser
from .gemini import GeminiParser
from .opencode import OpenCodeParser
from .vscode import VSCodeCopilotParser

__all__ = [
    "AntigravityParser",
    "CanonicalMessage",
    "ClaudeCodeParser",
    "CodexParser",
    "GeminiParser",
    "OpenCodeParser",
    "Parser",
    "ParserRegistry",
    "VSCodeCopilotParser",
    "content_hash",
    "generate_message_id",
]

# Register parsers
ParserRegistry.register(AntigravityParser())
ParserRegistry.register(ClaudeCodeParser())
ParserRegistry.register(CodexParser())
ParserRegistry.register(GeminiParser())
ParserRegistry.register(OpenCodeParser())
ParserRegistry.register(VSCodeCopilotParser())
