from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import settings
from app.schemas.billing import (
    BillingCatalogResponse,
    BillingMeResponse,
    BillingPack,
    BillingPortalResponse,
    CheckoutStatusResponse,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
)
from app.services.billing_service import (
    BillingError,
    catalog,
    create_billing_portal,
    create_checkout_session,
    credit_balance,
    customer_record,
    ensure_customer,
    process_webhook,
    verify_checkout_session,
)
from app.services.identity_service import ensure_workspace


router = APIRouter()


@router.get("/catalog", response_model=BillingCatalogResponse)
def billing_catalog() -> BillingCatalogResponse:
    packs = [
        BillingPack(
            id=item["id"],
            label=item["label"],
            credit_seconds=item["credit_seconds"],
            available=bool(item["price_id"]),
        )
        for item in catalog()
    ]
    return BillingCatalogResponse(
        enabled=settings.billing_enabled,
        enforce_credits=settings.billing_enforce_credits,
        packs=packs,
    )


@router.get("/me", response_model=BillingMeResponse)
def billing_me(request: Request, response: Response) -> BillingMeResponse:
    workspace_id = ensure_workspace(request, response)
    ensure_customer(workspace_id)
    customer = customer_record(workspace_id)
    return BillingMeResponse(
        workspace_id=workspace_id,
        enabled=settings.billing_enabled,
        enforce_credits=settings.billing_enforce_credits,
        balance_seconds=credit_balance(workspace_id),
        email=customer.get("email"),
        stripe_customer_id=customer.get("stripe_customer_id"),
    )


@router.post("/checkout", response_model=CreateCheckoutResponse)
def create_checkout(
    payload: CreateCheckoutRequest,
    request: Request,
    response: Response,
) -> CreateCheckoutResponse:
    workspace_id = ensure_workspace(request, response)
    try:
        session = create_checkout_session(workspace_id, payload.pack_id)
        return CreateCheckoutResponse(
            checkout_url=str(session["url"]),
            session_id=str(session["id"]),
        )
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/checkout/status", response_model=CheckoutStatusResponse)
def checkout_status(
    session_id: str,
    request: Request,
    response: Response,
) -> CheckoutStatusResponse:
    workspace_id = ensure_workspace(request, response)
    try:
        session = verify_checkout_session(workspace_id, session_id)
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CheckoutStatusResponse(
        session_id=session_id,
        paid=str(session.get("payment_status") or "") in {"paid", "no_payment_required"},
        balance_seconds=credit_balance(workspace_id),
    )


@router.post("/portal", response_model=BillingPortalResponse)
def billing_portal(request: Request, response: Response) -> BillingPortalResponse:
    workspace_id = ensure_workspace(request, response)
    try:
        return BillingPortalResponse(portal_url=create_billing_portal(workspace_id))
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event_type = process_webhook(payload, signature)
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"received": True, "type": event_type}
