from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Credential(TimestampMixin, Base):
    """A sign-in Compass keeps for a data source, e.g. "mail:outlook" with kind "microsoft".

    `secret` and `pending` are encrypted with COMPASS_SECRET_KEY (app.crypto) and never leave the
    server: no API response or log contains them."""

    __tablename__ = "credentials"

    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    # Tokens of a finished sign-in (refresh token, access token and its expiry).
    secret: Mapped[str | None] = mapped_column(Text)
    # A sign-in in progress (the device code), cleared when it ends.
    pending: Mapped[str | None] = mapped_column(Text)
    # Who signed in, as the provider names them (a mail address). Shown in the app.
    signed_in_as: Mapped[str | None] = mapped_column(String(320))
    # Why the last sign-in or token refresh failed; set means the account has to sign in again.
    error: Mapped[str | None] = mapped_column(String(500))
