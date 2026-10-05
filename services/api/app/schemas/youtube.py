from typing import Literal

from pydantic import BaseModel, Field


YouTubePrivacy = Literal["private", "unlisted", "public"]


class YouTubeStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    channel_id: str | None = None
    channel_title: str | None = None
    public_uploads_allowed: bool = False


class YouTubeConnectResponse(BaseModel):
    authorization_url: str


class YouTubePublishRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    privacy: YouTubePrivacy = "private"
    tags: list[str] = Field(default_factory=list, max_length=30)
    category_id: str = Field(default="22", max_length=8)
    publish_at: str | None = Field(default=None, max_length=64)


class YouTubePublishResponse(BaseModel):
    video_id: str
    youtube_url: str
    privacy: YouTubePrivacy
    title: str
