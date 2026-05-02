import base64
import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Optional
from urllib.parse import quote, urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
import logging

from app.api.routes.schemas import UserCreate, UserResponse, Token, LoginRequest, TokenRefreshRequest
from app.db.session import get_db
from app.db.models.user import User, UserRole
from app.core import security

router = APIRouter()
logger = logging.getLogger(__name__)

APPID_SCOPE = "openid email profile"
APPID_PROVIDER_GOOGLE = "google"
APPID_PROVIDER_CLOUD_DIRECTORY = "cloud_directory"
_APPID_DISCOVERY_CACHE: Optional[dict[str, Any]] = None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{name} is not configured.",
        )
    return value


def _get_frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000").strip().rstrip("/")


def _get_appid_redirect_uri() -> str:
    return os.getenv(
        "IBM_APPID_REDIRECT_URI",
        "http://localhost:8000/api/v1/auth/appid/callback",
    ).strip()


def _encode_base64_url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _decode_base64_url(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _sign_appid_state(payload: dict[str, Any]) -> str:
    state_payload = {
        **payload,
        "nonce": secrets.token_urlsafe(18),
    }
    raw = _encode_base64_url(json.dumps(state_payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(security.SECRET_KEY.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).digest()
    return f"{raw}.{_encode_base64_url(signature)}"


def _verify_appid_state(state: str) -> dict[str, Any]:
    try:
        raw, signature = state.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid App ID state.")

    expected = hmac.new(security.SECRET_KEY.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(signature, _encode_base64_url(expected)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid App ID state.")

    try:
        decoded = json.loads(_decode_base64_url(raw).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid App ID state.")
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid App ID state.")
    return decoded


def _get_appid_discovery_url() -> str:
    discovery_url = os.getenv("IBM_APPID_DISCOVERY_URL", "").strip()
    if discovery_url:
        return discovery_url

    oauth_server_url = os.getenv("IBM_APPID_OAUTH_SERVER_URL", "").strip().rstrip("/")
    if oauth_server_url:
        return f"{oauth_server_url}/.well-known/openid-configuration"

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="IBM_APPID_DISCOVERY_URL or IBM_APPID_OAUTH_SERVER_URL is not configured.",
    )


async def _get_appid_discovery() -> dict[str, Any]:
    global _APPID_DISCOVERY_CACHE
    if _APPID_DISCOVERY_CACHE is not None:
        return _APPID_DISCOVERY_CACHE

    discovery_url = _get_appid_discovery_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(discovery_url, headers={"Accept": "application/json"})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("App ID discovery failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach IBM App ID discovery endpoint.",
        )

    discovery = response.json()
    if not isinstance(discovery, dict):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Invalid App ID discovery document.")

    issuer = str(discovery.get("issuer", "")).rstrip("/")
    if issuer:
        discovery.setdefault("authorization_endpoint", f"{issuer}/authorization")
        discovery.setdefault("token_endpoint", f"{issuer}/token")
        discovery.setdefault("jwks_uri", f"{issuer}/publickeys")

    required_keys = ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer")
    if any(not discovery.get(key) for key in required_keys):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="App ID discovery document is missing required OIDC endpoints.",
        )

    _APPID_DISCOVERY_CACHE = discovery
    return discovery


def _get_appid_management_url(discovery: dict[str, Any]) -> str:
    override = os.getenv("IBM_APPID_MANAGEMENT_URL", "").strip().rstrip("/")
    if override:
        return override

    issuer = str(discovery.get("issuer", "")).rstrip("/")
    parsed = urlparse(issuer)
    tenant_id = os.getenv("IBM_APPID_TENANT_ID", "").strip() or issuer.rsplit("/", 1)[-1]
    if not parsed.scheme or not parsed.netloc or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to derive App ID management URL.",
        )
    return f"{parsed.scheme}://{parsed.netloc}/management/v4/{tenant_id}"


async def _exchange_appid_authorization_code(code: str) -> dict[str, Any]:
    discovery = await _get_appid_discovery()
    client_id = _get_required_env("IBM_APPID_CLIENT_ID")
    client_secret = _get_required_env("IBM_APPID_CLIENT_SECRET")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _get_appid_redirect_uri(),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                str(discovery["token_endpoint"]),
                data=data,
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.error("App ID authorization-code exchange failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to exchange App ID code.")

    if response.status_code >= 400:
        logger.warning("App ID authorization-code exchange rejected: %s", response.text[:300])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="App ID authentication failed.")
    return response.json()


async def _exchange_appid_password_credentials(email: str, password: str) -> dict[str, Any]:
    discovery = await _get_appid_discovery()
    client_id = _get_required_env("IBM_APPID_CLIENT_ID")
    client_secret = _get_required_env("IBM_APPID_CLIENT_SECRET")
    data = {
        "grant_type": "password",
        "username": email,
        "password": password,
        "scope": APPID_SCOPE,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                str(discovery["token_endpoint"]),
                data=data,
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.error("App ID Cloud Directory login failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to reach IBM App ID.")

    if response.status_code >= 400:
        logger.warning("App ID Cloud Directory login rejected for %s: %s", email, response.text[:300])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Cloud Directory credentials.")
    return response.json()


async def _get_ibm_iam_token() -> str:
    api_key = os.getenv("IBM_APPID_IAM_API_KEY", "").strip() or os.getenv("IBM_CLOUD_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IBM_APPID_IAM_API_KEY is required for Cloud Directory registration.",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://iam.cloud.ibm.com/identity/token",
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": api_key,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
    except httpx.HTTPError as exc:
        logger.error("IBM IAM token exchange failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to reach IBM IAM.")

    if response.status_code >= 400:
        logger.warning("IBM IAM token exchange rejected: %s", response.text[:300])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="IBM IAM API key was rejected.")

    access_token = response.json().get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="IBM IAM did not return an access token.")
    return str(access_token)


async def _create_appid_cloud_directory_user(email: str, password: str) -> None:
    discovery = await _get_appid_discovery()
    management_url = _get_appid_management_url(discovery)
    iam_token = await _get_ibm_iam_token()
    payload = {
        "active": True,
        "emails": [{"value": email, "primary": True}],
        "userName": email,
        "password": password,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{management_url}/cloud_directory/sign_up?shouldCreateProfile=true&language=en",
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {iam_token}",
                },
            )
    except httpx.HTTPError as exc:
        logger.error("App ID Cloud Directory sign-up failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to create App ID user.")

    if response.status_code in (400, 409):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered in Cloud Directory.")
    if response.status_code >= 400:
        logger.warning("App ID Cloud Directory sign-up rejected for %s: %s", email, response.text[:300])
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Cloud Directory registration failed.")


async def _decode_appid_identity(tokens: dict[str, Any]) -> dict[str, Any]:
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="App ID did not return an identity token.")

    discovery = await _get_appid_discovery()
    client_id = _get_required_env("IBM_APPID_CLIENT_ID")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            jwks_response = await client.get(str(discovery["jwks_uri"]), headers={"Accept": "application/json"})
            jwks_response.raise_for_status()
        jwks = jwks_response.json()
        header = jwt.get_unverified_header(str(id_token))
        key = next((item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")), None)
        if key is None:
            raise JWTError("Matching App ID signing key not found.")
        return jwt.decode(
            str(id_token),
            key,
            algorithms=[str(header.get("alg", "RS256"))],
            audience=client_id,
            issuer=str(discovery["issuer"]).rstrip("/"),
        )
    except (JWTError, httpx.HTTPError) as exc:
        logger.error("App ID identity token validation failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid App ID identity token.")


async def _fetch_appid_userinfo(access_token: str) -> dict[str, Any]:
    discovery = await _get_appid_discovery()
    userinfo_endpoint = discovery.get("userinfo_endpoint")
    if not userinfo_endpoint:
        issuer = str(discovery["issuer"]).rstrip("/")
        userinfo_endpoint = f"{issuer}/userinfo"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                str(userinfo_endpoint),
                headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("App ID userinfo lookup failed: %s", exc)
        return {}

    data = response.json()
    return data if isinstance(data, dict) else {}


async def _get_appid_profile(tokens: dict[str, Any]) -> dict[str, Any]:
    claims = await _decode_appid_identity(tokens)
    if not claims.get("email") and tokens.get("access_token"):
        claims.update(await _fetch_appid_userinfo(str(tokens["access_token"])))
    return claims


def _extract_appid_email(profile: dict[str, Any]) -> str:
    email = profile.get("email") or profile.get("preferred_username")
    if not email and isinstance(profile.get("identities"), list):
        for identity in profile["identities"]:
            if isinstance(identity, dict) and identity.get("email"):
                email = identity["email"]
                break
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="App ID profile did not include an email.")
    return _normalize_email(str(email))


def _get_default_appid_role() -> UserRole:
    configured_role = os.getenv("IBM_APPID_DEFAULT_ROLE", UserRole.ANALYST.value).strip().lower()
    for role in UserRole:
        if role.value == configured_role:
            return role
    return UserRole.ANALYST


async def _sync_appid_user(db: AsyncSession, profile: dict[str, Any]) -> User:
    email = _extract_appid_email(profile)
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalars().first()
    if user:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is inactive")
        return user

    new_user = User(
        email=email,
        hashed_password=security.get_password_hash(f"appid:{secrets.token_urlsafe(32)}"),
        role=_get_default_appid_role(),
        org_id=os.getenv("IBM_APPID_DEFAULT_ORG_ID", "org_001"),
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


def _build_auth_response(user: User) -> dict[str, Any]:
    access_token = security.create_access_token(subject=user.id)
    refresh_token = security.create_refresh_token(subject=user.id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.email.split("@")[0],
            "role": user.role.value if user.role else UserRole.ANALYST.value,
        },
    }


def _build_frontend_success_redirect(auth_payload: dict[str, Any]) -> str:
    user = auth_payload.get("user", {})
    fragment = urlencode(
        {
            "access_token": auth_payload["access_token"],
            "refresh_token": auth_payload["refresh_token"],
            "email": user.get("email", ""),
            "name": user.get("name", ""),
            "role": user.get("role", UserRole.ANALYST.value),
        }
    )
    return f"{_get_frontend_url()}/auth/callback#{fragment}"


def _build_frontend_error_redirect(message: str) -> str:
    return f"{_get_frontend_url()}/login?auth_error={quote(message)}"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        normalized_email = _normalize_email(user_in.email)

        # Check if user already exists
        result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
        user = result.scalars().first()
        if user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        
        # Create new user
        new_user = User(
            email=normalized_email,
            hashed_password=security.get_password_hash(user_in.password),
            role=user_in.role,
            org_id=user_in.org_id
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.post("/login", response_model=Token)
async def login(login_req: LoginRequest, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        normalized_email = _normalize_email(login_req.email)

        # Authenticate user
        result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found. Please sign up first.")
        if not security.verify_password(login_req.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is inactive")
        
        # Generate tokens
        access_token = security.create_access_token(subject=user.id)
        refresh_token = security.create_refresh_token(subject=user.id)
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging in user: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_req: TokenRefreshRequest, db: AsyncSession = Depends(get_db)) -> Any:
    # Minimal logic for now
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Token refresh not fully implemented")

@router.post("/logout")
async def logout() -> dict[str, str]:
    return {"message": "Successfully logged out"}


@router.get("/appid/status")
async def appid_status() -> dict[str, Any]:
    return {
        "enabled": bool(os.getenv("IBM_APPID_CLIENT_ID") and os.getenv("IBM_APPID_CLIENT_SECRET")),
        "cloud_directory": True,
        "google": True,
        "redirect_uri": _get_appid_redirect_uri(),
    }


@router.get("/appid/login")
async def appid_login(
    provider: str = Query(APPID_PROVIDER_GOOGLE),
    mode: str = Query("login"),
) -> RedirectResponse:
    try:
        provider_normalized = provider.strip().lower()
        if provider_normalized not in {APPID_PROVIDER_GOOGLE, APPID_PROVIDER_CLOUD_DIRECTORY}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported App ID provider.")

        discovery = await _get_appid_discovery()
        auth_params = {
            "client_id": _get_required_env("IBM_APPID_CLIENT_ID"),
            "response_type": "code",
            "scope": APPID_SCOPE,
            "redirect_uri": _get_appid_redirect_uri(),
            "state": _sign_appid_state({"provider": provider_normalized, "mode": mode}),
        }
        if provider_normalized == APPID_PROVIDER_GOOGLE:
            auth_params["idp"] = APPID_PROVIDER_GOOGLE

        return RedirectResponse(url=f"{discovery['authorization_endpoint']}?{urlencode(auth_params)}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error starting App ID login: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/appid/callback")
async def appid_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        if error:
            return RedirectResponse(url=_build_frontend_error_redirect(f"App ID rejected login: {error}"))
        if not code or not state:
            return RedirectResponse(url=_build_frontend_error_redirect("App ID callback is missing code or state."))

        _verify_appid_state(state)
        tokens = await _exchange_appid_authorization_code(code)
        profile = await _get_appid_profile(tokens)
        user = await _sync_appid_user(db, profile)
        return RedirectResponse(url=_build_frontend_success_redirect(_build_auth_response(user)))
    except HTTPException as exc:
        return RedirectResponse(url=_build_frontend_error_redirect(str(exc.detail)))
    except Exception as exc:
        logger.error("Error completing App ID callback: %s", exc, exc_info=True)
        return RedirectResponse(url=_build_frontend_error_redirect("App ID login failed."))


@router.post("/appid/cloud-directory/login")
async def appid_cloud_directory_login(login_req: LoginRequest, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        normalized_email = _normalize_email(login_req.email)
        tokens = await _exchange_appid_password_credentials(normalized_email, login_req.password)
        profile = await _get_appid_profile(tokens)
        profile.setdefault("email", normalized_email)
        user = await _sync_appid_user(db, profile)
        return _build_auth_response(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error logging in with App ID Cloud Directory: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/appid/cloud-directory/register", status_code=status.HTTP_201_CREATED)
async def appid_cloud_directory_register(login_req: LoginRequest, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        normalized_email = _normalize_email(login_req.email)
        await _create_appid_cloud_directory_user(normalized_email, login_req.password)
        tokens = await _exchange_appid_password_credentials(normalized_email, login_req.password)
        profile = await _get_appid_profile(tokens)
        profile.setdefault("email", normalized_email)
        user = await _sync_appid_user(db, profile)
        return _build_auth_response(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error registering with App ID Cloud Directory: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
