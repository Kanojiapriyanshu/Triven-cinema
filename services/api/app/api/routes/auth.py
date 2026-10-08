from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import settings
from app.schemas.auth import AuthMeResponse, AuthUserResponse, RequestOtpRequest, RequestOtpResponse, VerifyOtpRequest
from app.services.auth_service import (
    AuthError,
    auth_user_from_request,
    clear_login_cookies,
    request_otp,
    set_login_cookies,
    verify_otp,
)
from app.services.email_service import EmailDeliveryError, send_otp_email
from app.services.identity_service import workspace_id_from_request


router = APIRouter()


def _user_response(user: dict) -> AuthUserResponse:
    return AuthUserResponse(
        id=str(user["id"]),
        email=str(user["email"]),
        workspace_id=str(user["workspace_id"]),
    )


@router.post("/otp/request", response_model=RequestOtpResponse)
def request_login_otp(payload: RequestOtpRequest) -> RequestOtpResponse:
    if not settings.auth_enabled or settings.auto_login_email.strip():
        raise HTTPException(status_code=404, detail="Cinema login is disabled.")
    if not settings.smtp_configured and not settings.demo_auth_show_otp:
        raise HTTPException(status_code=503, detail="Sign-in email is not configured on this server.")
    try:
        challenge_id, otp, ttl = request_otp(payload.email)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if settings.smtp_configured:
        try:
            send_otp_email(payload.email.strip(), otp, ttl)
        except EmailDeliveryError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RequestOtpResponse(
        challenge_id=challenge_id,
        expires_in_seconds=ttl,
        demo_otp=otp if settings.demo_auth_show_otp else None,
        demo_mode=settings.demo_auth_show_otp,
    )


@router.post("/otp/verify", response_model=AuthMeResponse)
def verify_login_otp(payload: VerifyOtpRequest, request: Request, response: Response) -> AuthMeResponse:
    if not settings.auth_enabled or settings.auto_login_email.strip():
        raise HTTPException(status_code=404, detail="Cinema login is disabled.")
    try:
        user = verify_otp(
            payload.email,
            payload.otp,
            preferred_workspace_id=workspace_id_from_request(request),
        )
        set_login_cookies(response, user)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthMeResponse(authenticated=True, user=_user_response(user))


@router.get("/me", response_model=AuthMeResponse)
def auth_me(request: Request) -> AuthMeResponse:
    if not settings.auth_enabled:
        return AuthMeResponse(authenticated=True, user=None)
    user = auth_user_from_request(request)
    if not user:
        return AuthMeResponse(authenticated=False, user=None)
    return AuthMeResponse(authenticated=True, user=_user_response(user), open_access=bool(settings.auto_login_email.strip()))


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_login_cookies(response)
    return {"ok": True}
