from urllib.parse import urlencode

import jwt
import requests
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import SuspiciousOperation
from django.http import JsonResponse
from django.shortcuts import redirect
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError


URL_KEYCLOAK = "http://localhost:8080"
URL_VOTOUTN = "http://localhost:8000"
KEYCLOAK_REALM = "FRBA"
KEYCLOAK_CLIENT_ID = "VOTOUTN"


def keycloak_login_view(request):
    base_url = f"{URL_KEYCLOAK}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
    params = {
        "client_id": KEYCLOAK_CLIENT_ID,
        "redirect_uri": f"{URL_VOTOUTN}/callback",
        "response_type": "code",
        "scope": "openid",
    }
    return redirect(f"{base_url}?{urlencode(params)}")


def keycloak_login_callback_view(request):
    code = request.GET.get("code")
    if not code:
        return JsonResponse({"error": "No code in callback"}, status=400)

    issuer = f"{URL_KEYCLOAK}/realms/{KEYCLOAK_REALM}"
    token_url = f"{issuer}/protocol/openid-connect/token"
    data = {
        "client_id": KEYCLOAK_CLIENT_ID,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": f"{URL_VOTOUTN}/callback",
    }

    try:
        response = requests.post(token_url, data=data, timeout=10)
        response.raise_for_status()
        tokens = response.json()
        id_token = tokens["id_token"]
        signing_key = PyJWKClient(f"{issuer}/protocol/openid-connect/certs").get_signing_key_from_jwt(id_token)
        decoded = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=KEYCLOAK_CLIENT_ID,
            issuer=issuer,
        )
    except (KeyError, jwt.InvalidTokenError, PyJWKClientError, requests.RequestException) as error:
        raise SuspiciousOperation("La autenticacion de Keycloak no es valida") from error

    user = authenticate(
        request,
        dni=decoded.get("dni"),
        username=decoded.get("preferred_username") or decoded.get("username", ""),
        first_name=decoded.get("given_name", ""),
        last_name=decoded.get("family_name", ""),
        email=decoded.get("email", ""),
        subject=decoded.get("sub", ""),
    )
    if user is None:
        return JsonResponse({"error": "No autenticado"}, status=401)

    backend = "apps.usuarios.backend_auth.ElectorBackend" if getattr(user, "es_elector", False) else "django.contrib.auth.backends.ModelBackend"
    login(request, user, backend=backend)
    request.session["keycloak_id_token"] = id_token
    if getattr(user, "es_elector", False):
        request.session["keycloak_user"] = {
            "dni": user.dni,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "subject": user.subject,
        }
    if getattr(user, "es_elector", False):
        return redirect("inicio-autenticado")
    return redirect("inicio-autenticado")


def keycloak_logout_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "El logout requiere POST"}, status=405)

    id_token = request.session.get("keycloak_id_token")
    logout(request)

    params = {
        "post_logout_redirect_uri": f"{URL_VOTOUTN}",
        "client_id": KEYCLOAK_CLIENT_ID,
    }
    if id_token:
        params["id_token_hint"] = id_token

    return redirect(f"{URL_KEYCLOAK}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/logout?{urlencode(params)}")
