from pydantic import BaseModel, Field


class BillingPack(BaseModel):
    id: str
    label: str
    credit_seconds: int
    available: bool


class BillingCatalogResponse(BaseModel):
    enabled: bool
    enforce_credits: bool
    packs: list[BillingPack]


class BillingMeResponse(BaseModel):
    workspace_id: str
    enabled: bool
    enforce_credits: bool
    balance_seconds: int
    email: str | None = None
    stripe_customer_id: str | None = None


class CreateCheckoutRequest(BaseModel):
    pack_id: str = Field(..., min_length=1, max_length=32)


class CreateCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class CheckoutStatusResponse(BaseModel):
    session_id: str
    paid: bool
    balance_seconds: int


class BillingPortalResponse(BaseModel):
    portal_url: str
