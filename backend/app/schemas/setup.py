from pydantic import BaseModel, Field


class SetupRead(BaseModel):
    first_run: bool = Field(description="An empty install that has not seen the welcome page")
    timezone: str
    language: str = Field(description="COMPASS_LANGUAGE, the language of the server's own texts")
    sources: dict[str, bool]
