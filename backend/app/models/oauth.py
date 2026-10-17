"""Storage for the built-in OAuth server that protects the MCP endpoint.

Secrets (codes, tokens) are only stored as SHA-256 hashes, so a database dump does not
contain usable credentials.
"""

from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    # Full RFC 7591 client information as returned by registration. The SDK compares the
    # client secret itself, so it is stored as issued.
    info: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthRequest(Base):
    """An /authorize request waiting for the owner to log in and approve it."""

    __tablename__ = "oauth_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE")
    )
    params: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthCode(Base):
    __tablename__ = "oauth_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE")
    )
    data: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # "access" or "refresh"
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), index=True
    )
    # Access and refresh token issued together share a grant id, so revoking one revokes both.
    grant_id: Mapped[str] = mapped_column(String(64), index=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(60)))
    resource: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Every MCP tool call that changes data."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor: Mapped[str] = mapped_column(String(100))  # e.g. "mcp:<client_id>"
    action: Mapped[str] = mapped_column(String(60))
    arguments: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    ok: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str | None] = mapped_column(Text)
