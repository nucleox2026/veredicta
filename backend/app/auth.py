from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from .settings import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.auth_required:
        return {"email": "dev@local", "development": True}

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Autenticação Google obrigatória")

    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID não configurado no backend")

    try:
        payload = id_token.verify_oauth2_token(
            credentials.credentials,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token Google inválido") from exc

    email = str(payload.get("email", "")).lower()
    if not payload.get("email_verified") or not email:
        raise HTTPException(status_code=403, detail="E-mail Google não verificado")

    email_allowed = email in settings.allowed_email_set
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    domain_allowed = domain in settings.allowed_domain_set

    if settings.allowed_email_set or settings.allowed_domain_set:
        if not (email_allowed or domain_allowed):
            raise HTTPException(status_code=403, detail="Usuário não autorizado para o JurisIA")
    else:
        raise HTTPException(status_code=500, detail="Configure ALLOWED_EMAILS ou ALLOWED_EMAIL_DOMAINS")

    return {"email": email, "name": payload.get("name"), "sub": payload.get("sub")}
