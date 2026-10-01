import secrets
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import SuspiciousOperation
from django.http import JsonResponse
from django.shortcuts import redirect
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError


def _keycloak_url_publico(request):
    # Keycloak publica el puerto 8080 en la misma interfaz que la app; usar el host con el que
    # el navegador llego (PC por localhost/127.0.0.1, celular por la IP de la red Wi-Fi) permite
    # loguearse desde cualquiera de los dos sin fijar una URL unica en settings.
    host_navegador = request.get_host().split(":")[0]
    return f"http://{host_navegador}:8080"


def keycloak_login_view(request):
    estado = secrets.token_urlsafe(32)
    # El redirect_uri debe coincidir exactamente entre el pedido de autorizacion y el canje de
    # token, por eso se calcula segun el host real usado por el navegador y se guarda en sesion.
    redirect_uri = request.build_absolute_uri("/callback")
    keycloak_url_publico = _keycloak_url_publico(request)
    request.session["keycloak_estado"] = estado
    request.session["keycloak_redirect_uri"] = redirect_uri
    request.session["keycloak_url_publico"] = keycloak_url_publico
    base_url = f"{keycloak_url_publico}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/auth"
    params = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid",
        "state": estado,
    }
    return redirect(f"{base_url}?{urlencode(params)}")


def keycloak_login_callback_view(request):
    code = request.GET.get("code")
    estado_esperado = request.session.pop("keycloak_estado", None)
    redirect_uri = request.session.pop("keycloak_redirect_uri", None)
    keycloak_url_publico = request.session.pop("keycloak_url_publico", None)
    if not estado_esperado or request.GET.get("state") != estado_esperado or not redirect_uri or not keycloak_url_publico:
        raise SuspiciousOperation("El estado de la autenticacion de Keycloak no es valido")
    if not code:
        return JsonResponse({"error": "No code in callback"}, status=400)

    # Las llamadas server-to-server (token y certs) viajan por la red interna del contenedor,
    # pero se envia el Host publico para que Keycloak emita el mismo "iss" que vio el navegador.
    encabezado_host = {"Host": keycloak_url_publico.split("://", 1)[1]}
    issuer_interno = f"{settings.KEYCLOAK_URL_INTERNO}/realms/{settings.KEYCLOAK_REALM}"
    issuer_publico = f"{keycloak_url_publico}/realms/{settings.KEYCLOAK_REALM}"
    token_url = f"{issuer_interno}/protocol/openid-connect/token"
    data = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    try:
        response = requests.post(token_url, data=data, headers=encabezado_host, timeout=10)
        response.raise_for_status()
        tokens = response.json()
        id_token = tokens["id_token"]
        signing_key = PyJWKClient(
            f"{issuer_interno}/protocol/openid-connect/certs", headers=encabezado_host
        ).get_signing_key_from_jwt(id_token)
        decoded = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.KEYCLOAK_CLIENT_ID,
            issuer=issuer_publico,
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
        "post_logout_redirect_uri": request.build_absolute_uri("/"),
        "client_id": settings.KEYCLOAK_CLIENT_ID,
    }
    if id_token:
        params["id_token_hint"] = id_token

    keycloak_url_publico = _keycloak_url_publico(request)
    return redirect(f"{keycloak_url_publico}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/logout?{urlencode(params)}")
