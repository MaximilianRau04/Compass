"""The Compass MCP server: tools and prompts for AI assistants.

Tools reuse app.services, the same logic the REST API uses. Write tools are deliberately
limited (no deleting; cancelling a task is the undo), are rate limited per OAuth client and
recorded in the audit log.

This module puts the server together: core holds the instance, tools/* and prompts
register themselves on import, schemas and guards are shared by the tools.
"""

from app.mcp import prompts  # noqa: F401  (registers the prompts)
from app.mcp.core import mcp, provider
from app.mcp.tools import (  # noqa: F401  (each module registers its tools)
    briefs,
    calendar,
    finance,
    habits,
    health,
    journal,
    mail,
    news,
    notes,
    nutrition,
    search,
    tasks,
    training,
)

__all__ = ["mcp", "provider"]
