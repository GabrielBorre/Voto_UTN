from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.justificativos.models import TipoJustificativo
from apps.usuarios.management.commands.seed_keycloak_demo import USUARIOS
from apps.usuarios.models import AsignacionRol, PerfilUsuario


TIPOS_JUSTIFICATIVO_INICIALES = (
    "Certificado medico",
    "Enfermedad o accidente",
    "Obligaciones laborales",
    "Otro",
    "Cuidado de familiar",
)


class Command(BaseCommand):
    help = "Carga parametros e identidades de demostracion sin crear elecciones."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("cargar_parametros_estandar", stdout=self.stdout)
        for nombre in TIPOS_JUSTIFICATIVO_INICIALES:
            TipoJustificativo.objects.get_or_create(nombre=nombre, defaults={"activo": True})

        for datos in USUARIOS.values():
            usuario, creado = get_user_model().objects.get_or_create(
                username=datos["username"],
                defaults={
                    "first_name": datos["first_name"],
                    "last_name": datos["last_name"],
                    "email": datos["email"],
                },
            )
            if creado:
                usuario.set_unusable_password()
                usuario.save(update_fields=("password",))
            perfil = PerfilUsuario.objects.filter(usuario=usuario).first()
            if perfil and perfil.dni != datos["dni"]:
                raise CommandError(f"El usuario {datos['username']} tiene un DNI diferente.")
            if not creado and perfil is None:
                raise CommandError(f"El usuario {datos['username']} ya existe sin perfil electoral.")
            if PerfilUsuario.objects.filter(dni=datos["dni"]).exclude(usuario=usuario).exists():
                raise CommandError(f"El DNI de {datos['username']} pertenece a otro usuario.")
            if perfil is None:
                PerfilUsuario.objects.create(usuario=usuario, dni=datos["dni"])
            AsignacionRol.objects.get_or_create(
                usuario=usuario,
                rol=datos["rol"],
                eleccion=None,
                sede=None,
                mesa=None,
                defaults={"activo": True},
            )

        self.stdout.write(self.style.SUCCESS(
            "Parametros e identidades locales cargados; no se creo ninguna eleccion."
        ))
