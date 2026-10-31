"""Built-in OAuth 2.1 authorization server for the MCP endpoint.

Compass has exactly one user, so instead of running a separate identity provider this
implements the SDK's OAuthAuthorizationServerProvider on top of Postgres. The SDK handles
discovery metadata, dynamic client registration (which assistants use), PKCE and the token
endpoint; this class stores clients, codes and tokens, and sends /authorize to the owner
login page in app.mcp.login.
"""

import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta

import anyio.to_thread
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.mcp.db import session_scope
from app.models.oauth import OAuthClient, OAuthCode, OAuthRequest
from app.models.oauth import OAuthToken as TokenRow

SCOPE = "compass"
OWNER = "owner"
REQUEST_TTL = timedelta(minutes=10)
CODE_TTL = timedelta(minutes=5)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


class PendingRequest:
    """An authorization request shown on the login page."""

    def __init__(self, request_id: str, client: OAuthClientInformationFull, params: dict) -> None:
        self.id = request_id
        self.client = client
        self.params = AuthorizationParams.model_validate(params)

    @property
    def client_name(self) -> str:
        return self.client.client_name or self.client.client_id or "?"

    @property
    def redirect_host(self) -> str:
        return self.params.redirect_uri.host or str(self.params.redirect_uri)


class CompassOAuthProvider:
    def __init__(self) -> None:
        settings = get_settings()
        self.public_url = settings.mcp_public_url.rstrip("/")
        self.resource_url = settings.mcp_resource_url
        self.access_ttl = settings.mcp_access_token_ttl
        self.refresh_ttl = settings.mcp_refresh_token_ttl

    # --- Clients ---------------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        def load() -> OAuthClientInformationFull | None:
            with session_scope() as session:
                row = session.get(OAuthClient, client_id)
                return OAuthClientInformationFull.model_validate(row.info) if row else None

        return await anyio.to_thread.run_sync(load)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        def store() -> None:
            with session_scope() as session:
                session.add(
                    OAuthClient(
                        client_id=client_info.client_id,
                        info=client_info.model_dump(mode="json", exclude_none=True),
                    )
                )

        await anyio.to_thread.run_sync(store)

    # --- Authorization ---------------------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        request_id = secrets.token_urlsafe(32)

        def store() -> None:
            with session_scope() as session:
                session.execute(delete(OAuthRequest).where(OAuthRequest.expires_at < _now()))
                session.add(
                    OAuthRequest(
                        id=request_id,
                        client_id=client.client_id,
                        params=params.model_dump(mode="json"),
                        expires_at=_now() + REQUEST_TTL,
                    )
                )

        await anyio.to_thread.run_sync(store)
        return f"{self.public_url}/oauth/login?request={request_id}"

    def get_pending(self, request_id: str) -> PendingRequest | None:
        with session_scope() as session:
            row = session.get(OAuthRequest, request_id)
            if row is None or row.expires_at < _now():
                return None
            client = session.get(OAuthClient, row.client_id)
            if client is None:
                return None
            return PendingRequest(
                row.id, OAuthClientInformationFull.model_validate(client.info), row.params
            )

    def approve(self, request_id: str) -> str | None:
        """Owner approved: issue an authorization code and return the client redirect URL."""
        with session_scope() as session:
            row = session.get(OAuthRequest, request_id)
            if row is None or row.expires_at < _now():
                return None
            params = AuthorizationParams.model_validate(row.params)
            code = secrets.token_urlsafe(32)
            data = AuthorizationCode(
                code="",
                scopes=params.scopes or [SCOPE],
                expires_at=time.time() + CODE_TTL.total_seconds(),
                client_id=row.client_id,
                code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri,
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=params.resource,
                subject=OWNER,
            )
            session.add(
                OAuthCode(
                    code_hash=_hash(code),
                    client_id=row.client_id,
                    data=data.model_dump(mode="json", exclude={"code"}),
                    expires_at=_now() + CODE_TTL,
                )
            )
            session.delete(row)
            return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    def deny(self, request_id: str) -> str | None:
        with session_scope() as session:
            row = session.get(OAuthRequest, request_id)
            if row is None:
                return None
            params = AuthorizationParams.model_validate(row.params)
            session.delete(row)
            return construct_redirect_uri(
                str(params.redirect_uri), error="access_denied", state=params.state
            )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        def load() -> AuthorizationCode | None:
            with session_scope() as session:
                row = session.get(OAuthCode, _hash(authorization_code))
                if row is None or row.client_id != client.client_id or row.expires_at < _now():
                    return None
                return AuthorizationCode.model_validate({**row.data, "code": authorization_code})

        return await anyio.to_thread.run_sync(load)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        def exchange() -> OAuthToken:
            with session_scope() as session:
                # Codes are single use: delete first, fail if someone else already did.
                deleted = session.execute(
                    delete(OAuthCode).where(OAuthCode.code_hash == _hash(authorization_code.code))
                ).rowcount
                if not deleted:
                    raise TokenError("invalid_grant", "authorization code was already used")
                return self._issue(
                    session,
                    client.client_id or "",
                    authorization_code.scopes,
                    authorization_code.resource,
                    authorization_code.subject,
                )

        return await anyio.to_thread.run_sync(exchange)

    # --- Tokens ----------------------------------------------------------------------------

    def _issue(
        self,
        session: Session,
        client_id: str,
        scopes: list[str],
        resource: str | None,
        subject: str | None,
    ) -> OAuthToken:
        grant_id = secrets.token_hex(16)
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        now = _now()
        for kind, value, ttl in (
            ("access", access, self.access_ttl),
            ("refresh", refresh, self.refresh_ttl),
        ):
            session.add(
                TokenRow(
                    token_hash=_hash(value),
                    kind=kind,
                    client_id=client_id,
                    grant_id=grant_id,
                    scopes=scopes,
                    resource=resource,
                    subject=subject,
                    expires_at=now + timedelta(seconds=ttl),
                )
            )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=self.access_ttl,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    def _load(self, session: Session, token: str, kind: str) -> TokenRow | None:
        row = session.get(TokenRow, _hash(token))
        if row is None or row.kind != kind or row.revoked:
            return None
        if row.expires_at is not None and row.expires_at < _now():
            return None
        return row

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        def load() -> RefreshToken | None:
            with session_scope() as session:
                row = self._load(session, refresh_token, "refresh")
                if row is None or row.client_id != client.client_id:
                    return None
                return RefreshToken(
                    token=refresh_token,
                    client_id=row.client_id,
                    scopes=list(row.scopes),
                    expires_at=int(row.expires_at.timestamp()) if row.expires_at else None,
                    resource=row.resource,
                    subject=row.subject,
                )

        return await anyio.to_thread.run_sync(load)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        def exchange() -> OAuthToken:
            with session_scope() as session:
                row = self._load(session, refresh_token.token, "refresh")
                if row is None:
                    raise TokenError("invalid_grant", "refresh token is not valid")
                # Rotation: the old access and refresh token stop working.
                session.execute(
                    update(TokenRow).where(TokenRow.grant_id == row.grant_id).values(revoked=True)
                )
                granted = [s for s in scopes if s in row.scopes] if scopes else list(row.scopes)
                return self._issue(
                    session, row.client_id, granted, refresh_token.resource, refresh_token.subject
                )

        return await anyio.to_thread.run_sync(exchange)

    async def load_access_token(self, token: str) -> AccessToken | None:
        def load() -> AccessToken | None:
            with session_scope() as session:
                row = self._load(session, token, "access")
                if row is None:
                    return None
                # Tokens are bound to this server: refuse one issued for another resource.
                if row.resource and row.resource.rstrip("/") != self.resource_url.rstrip("/"):
                    return None
                return AccessToken(
                    token=token,
                    client_id=row.client_id,
                    scopes=list(row.scopes),
                    expires_at=int(row.expires_at.timestamp()) if row.expires_at else None,
                    resource=row.resource,
                    subject=row.subject,
                )

        return await anyio.to_thread.run_sync(load)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        def revoke() -> None:
            with session_scope() as session:
                row = session.get(TokenRow, _hash(token.token))
                if row is not None:
                    session.execute(
                        update(TokenRow)
                        .where(TokenRow.grant_id == row.grant_id)
                        .values(revoked=True)
                    )

        await anyio.to_thread.run_sync(revoke)

    async def exchange_identity_assertion(self, client, params) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "identity assertions are not supported")


def revoke_all_tokens() -> int:
    """Log out every client (e.g. after a leaked token). Returns the number of tokens revoked."""
    with session_scope() as session:
        return session.execute(
            update(TokenRow).where(TokenRow.revoked.is_(False)).values(revoked=True)
        ).rowcount
