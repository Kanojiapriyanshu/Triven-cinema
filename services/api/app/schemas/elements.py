from typing import Literal

from pydantic import BaseModel, Field, field_validator


ElementType = Literal["character", "prop", "location", "style"]
ElementStatus = Literal["active", "archived"]
ElementReferenceMode = Literal["identity", "start_frame"]
ElementWardrobePolicy = Literal["prompt", "reference"]
ElementAssetRole = Literal["primary", "face", "full_body", "profile", "costume", "object", "location", "style", "support"]
# "auto": a Character that is only tagged at the end of the prompt (never described in the
# shot) is kept out of the identity sheet when another Character is clearly the subject.
# "cast": the creator explicitly wants this Character in the shot.
ElementCastRole = Literal["auto", "cast"]


class ElementAssetResponse(BaseModel):
    id: str
    filename: str
    original_filename: str
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    role: ElementAssetRole = "support"
    asset_url: str
    created_at: str


class ElementVersionResponse(BaseModel):
    id: str
    version: int
    created_at: str


class ElementResponse(BaseModel):
    id: str
    name: str
    handle: str
    type: ElementType
    description: str = ""
    status: ElementStatus = "active"
    current_version_id: str
    current_version: int
    primary_asset_id: str | None = None
    assets: list[ElementAssetResponse] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ElementListResponse(BaseModel):
    elements: list[ElementResponse]
    count: int
    max_stored: int
    max_assets_per_element: int
    max_active_per_scene: int


class ElementUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    handle: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=1600)
    status: ElementStatus | None = None
    primary_asset_id: str | None = Field(default=None, max_length=64)

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.lstrip("@").strip()


class ElementBinding(BaseModel):
    element_id: str = Field(..., min_length=8, max_length=64)
    version_id: str | None = Field(default=None, min_length=8, max_length=64)
    handle: str = Field(..., min_length=1, max_length=40)
    reference_mode: ElementReferenceMode = "identity"
    wardrobe_policy: ElementWardrobePolicy = "prompt"
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    apply_to_all_scenes: bool = False
    cast_role: ElementCastRole = "auto"

    @field_validator("handle")
    @classmethod
    def normalize_binding_handle(cls, value: str) -> str:
        return value.lstrip("@").strip()


class ResolvedElementBinding(BaseModel):
    element_id: str
    version_id: str
    handle: str
    name: str
    type: ElementType
    description: str
    reference_mode: ElementReferenceMode
    wardrobe_policy: ElementWardrobePolicy
    strength: float
    apply_to_all_scenes: bool
    cast_role: ElementCastRole = "auto"
    primary_asset_path: str
    primary_asset_url: str
    reference_asset_paths: list[str] = Field(default_factory=list)
    reference_asset_urls: list[str] = Field(default_factory=list)
    reference_asset_roles: list[ElementAssetRole] = Field(default_factory=list)
