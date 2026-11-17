from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.elecciones.models import Eleccion
from apps.usuarios.models import AsignacionRol, PerfilUsuario


USUARIOS = {
    "administrador_junta_juan": {
        "username": "juanb",
        "first_name": "Juan",
        "last_name": "Bal",
        "email": "juanb@frba.utn.edu.ar",
        "dni": "20111222",
        "legajo": "1111110",
        "rol": AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    },
    "administrador_junta": {
        "username": "adminjunta",
        "first_name": "Admin",
        "last_name": "Junta",
        "email": "adminjunta@frba.utn.edu.ar",
        "dni": "20222333",
        "legajo": "3334440",
        "rol": AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    },
    "administrador_junta_1": {
        "username": "adminjunta1",
        "first_name": "Admin",
        "last_name": "Junta",
        "email": "adminjunta1@frba.utn.edu.ar",
        "dni": "20333444",
        "legajo": "4445550",
        "rol": AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    },
    "administrativo_junta": {
        "username": "administrativojunta",
        "first_name": "Administrativo",
        "last_name": "Junta",
        "email": "administrativojunta@frba.utn.edu.ar",
        "dni": "25111222",
        "legajo": "5556660",
        "rol": AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
    },
    "administrativo_junta_1": {
        "username": "administrativojunta1",
        "first_name": "Administrativo",
        "last_name": "Junta",
        "email": "administrativojunta1@frba.utn.edu.ar",
        "dni": "25222333",
        "legajo": "6667770",
        "rol": AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
    },
}


class Command(BaseCommand):
    help = "Carga las cuentas internas definidas en USUARIOS para la elección demo."

    @transaction.atomic
    def handle(self, *args, **options):
        eleccion = Eleccion.objects.filter(nombre="Eleccion Demo 2026").first()
        if eleccion is None:
            raise CommandError("No existe Eleccion Demo 2026. Ejecuta antes seed_demo_data.")

        sede = eleccion.elecciones_sede.select_related("sede").first()
        if sede is None:
            raise CommandError("La Elección Demo 2026 no tiene una sede configurada.")

        for datos in USUARIOS.values():
            self._crear_usuario_interno(datos, eleccion, sede.sede)

        self.stdout.write(self.style.SUCCESS("Cuentas de demostración creadas o actualizadas."))
        nombres = ", ".join(datos["username"] for datos in USUARIOS.values())
        self.stdout.write(f"Usuarios internos creados o actualizados: {nombres}.")

    def _crear_usuario_interno(self, data, eleccion, sede):
        User = get_user_model()
        usuario, _ = User.objects.update_or_create(
            username=data["username"],
            defaults={
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data["email"],
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )
        usuario.set_unusable_password()
        usuario.save(update_fields=("first_name", "last_name", "email", "is_active", "is_staff", "is_superuser", "password"))
        PerfilUsuario.objects.update_or_create(
            usuario=usuario,
            defaults={"dni": data["dni"], "activo": True, "elector": None},
        )
        AsignacionRol.objects.update_or_create(
            usuario=usuario,
            rol=data["rol"],
            eleccion=eleccion,
            defaults={"sede": sede, "mesa": None, "activo": True},
        )
        return usuario
