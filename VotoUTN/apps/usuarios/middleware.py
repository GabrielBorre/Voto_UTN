class KeycloakSessionUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        datos_usuario = request.session.get("keycloak_user", {})
        if getattr(user, "is_authenticated", False) and getattr(user, "es_elector", False):
            for campo in ("dni", "username", "first_name", "last_name", "email", "subject"):
                valor = datos_usuario.get(campo)
                if valor:
                    if campo == "username":
                        user._username = valor
                    else:
                        setattr(user, campo, valor)
        return self.get_response(request)
