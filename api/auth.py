"""Cosplay — API Token Verification

FastAPI dependencies to protect proxy and CLI routes.
"""

from fastapi import HTTPException, Request, Depends
import hmac
from config.settings import RuntimeSettingsManager

def verify_api_token(request: Request) -> str:
    """Verify the API/CLI Auth Token provided in the Authorization header.
    
    This dependency reads dynamically from RuntimeSettingsManager on every request.
    If the token is regenerated, existing sessions will instantly fail this check.
    
    Expected header:
        Authorization: Bearer <token>
    """
    settings = RuntimeSettingsManager().get()
    expected_token = settings.api_auth_token
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    token = auth_header.split(" ", 1)[1]
    
    # Use constant-time comparison to prevent timing attacks if possible
    # For now, a direct comparison is sufficient for local proxy auth
    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid API/CLI Auth Token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return token
