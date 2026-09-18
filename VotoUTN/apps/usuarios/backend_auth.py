from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth import get_user_model
from .models import PerfilUsuario


class ElectorUser(AbstractBaseUser):
    """Identidad autenticada por Keycloak que no se persiste en auth_user."""

    def __init__(self, dni, first_name="", last_name="", email="", subject=""):
        super().__init__()
        self.pk = f"elector:{dni}"
        self.dni = dni
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.subject = subject
        self.es_elector = True
        self.is_active = True
        self.is_staff = False
        self.is_superuser = False

    @property
    def username(self):
        return self.dni

    def get_username(self):
        return self.dni

    def get_session_auth_hash(self):
        return ""

    def save(self, *args, **kwargs):
        return None


class ElectorBackend(BaseBackend):
    def authenticate(self, request, dni=None, first_name=None, last_name=None, email=None, subject=""):
        if not dni:
            return None

        perfil = PerfilUsuario.objects.select_related("usuario").filter(dni=dni, activo=True).first()
        if perfil is not None and perfil.usuario.is_active:
            return perfil.usuario

        return ElectorUser(dni, first_name, last_name, email, subject)

    def get_user(self, user_id):
        user_id = str(user_id)
        if user_id.startswith("elector:"):
            return ElectorUser(user_id.removeprefix("elector:"))

        try:
            return get_user_model().objects.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None