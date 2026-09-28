from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth import get_user_model
from django.utils.crypto import salted_hmac

from apps.padron.models import Elector

from .models import PerfilUsuario


class ElectorUser(AbstractBaseUser):
    """Identidad autenticada por Keycloak que no se persiste en auth_user."""

    def __init__(self, dni, first_name="", last_name="", email="", subject="", username=""):
        super().__init__()
        dni_limpio = str(dni).removeprefix("elector:")
        self.dni = dni_limpio
        self.pk = int(dni_limpio)
        self._username = username or self.dni
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
        return self._username

    def get_username(self):
        return self.username

    def get_session_auth_hash(self):
        return salted_hmac("apps.usuarios.ElectorUser", self.dni).hexdigest()

    def save(self, *args, **kwargs):
        return None


class ElectorBackend(BaseBackend):
    def authenticate(self, request, dni=None, first_name=None, last_name=None, email=None, subject="", username=None):
        if not dni:
            return None

        perfil = PerfilUsuario.objects.select_related("usuario").filter(dni=dni, activo=True).first()
        if perfil is not None and perfil.usuario.is_active:
            return perfil.usuario

        return ElectorUser(dni, first_name, last_name, email, subject, username)

    def get_user(self, user_id):
        user_id = str(user_id)
        if user_id.startswith("elector:"):
            user_id = user_id.removeprefix("elector:")

        try:
            pk = int(user_id)
        except (TypeError, ValueError):
            return None

        try:
            return get_user_model().objects.get(pk=pk)
        except get_user_model().DoesNotExist:
            if user_id and user_id.isdigit():
                return ElectorUser(str(pk))
            return None