from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustroDepartamento
from apps.mesas.models import Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.usuarios.models import AsignacionRol, PerfilUsuario


USUARIOS = {
    "administrador_junta": {
        "username": "juanb",
        "first_name": "Juan M",
        "last_name": "Bal",
        "email": "juanb@frba.utn.edu.ar",
        "dni": "35444111",
        "legajo": "1111110",
        "rol": AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    },
    "administrativo_junta": {
        "username": "administrativojunta",
        "first_name": "Administrativo",
        "last_name": "Junta",
        "email": "administrativojunta@frba.utn.edu.ar",
        "dni": "22555777",
        "legajo": "2222221",
        "rol": AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
    },
    "autoridad_mesa": {
        "username": "autmesa",
        "first_name": "Mesa",
        "last_name": "Entrada",
        "email": "autmesa@frba.utn.edu.ar",
        "dni": "28111333",
        "legajo": "3333332",
    },
    "elector": {
        "username": "alumnocg",
        "first_name": "Carlos",
        "last_name": "Gomez",
        "email": "alumnocg@frba.utn.edu.ar",
        "dni": "38999222",
        "legajo": "4444443",
    },
}


class Command(BaseCommand):
    help = "Carga identidades locales de prueba compatibles con usuarios de Keycloak."

    def add_arguments(self, parser):
        parser.add_argument(
            "--asignar-autoridad",
            action="store_true",
            help="Asigna la candidatura de autmesa a la primera mesa demo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        eleccion = Eleccion.objects.filter(nombre="Eleccion Demo 2026").first()
        if eleccion is None:
            raise CommandError("No existe Eleccion Demo 2026. Ejecuta antes seed_demo_data.")

        configuracion = EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro__eleccion=eleccion,
        ).first()
        sede = eleccion.elecciones_sede.select_related("sede").first()
        mesa = Mesa.objects.filter(eleccion=eleccion).order_by("numero").first()
        if configuracion is None or sede is None or mesa is None:
            raise CommandError("La Eleccion Demo 2026 no tiene configurados padron, sede y mesa.")

        admin_junta = self._crear_usuario_interno(USUARIOS["administrador_junta"], eleccion, sede.sede)
        administrativo = self._crear_usuario_interno(USUARIOS["administrativo_junta"], eleccion, sede.sede)

        autoridad = self._crear_elector(USUARIOS["autoridad_mesa"], eleccion, configuracion, sede.sede)
        elector = self._crear_elector(USUARIOS["elector"], eleccion, configuracion, sede.sede)
        candidatura, _ = CandidaturaAutoridad.objects.get_or_create(
            registro_padron=autoridad[1],
            defaults={"cargada_por": admin_junta},
        )

        if options["asignar_autoridad"]:
            AsignacionAutoridad.objects.update_or_create(
                registro_padron=autoridad[1],
                defaults={
                    "candidatura": candidatura,
                    "mesa": mesa,
                    "asignada_por": admin_junta,
                },
            )

        self.stdout.write(self.style.SUCCESS("Datos locales de Keycloak cargados correctamente."))
        self.stdout.write("Usuarios internos: juanb (administrador de junta), administrativojunta (administrativo de junta).")
        self.stdout.write("Identidades virtuales: autmesa (candidata a autoridad), alumnocg (elector).")
        self.stdout.write("Use --asignar-autoridad para asignar autmesa a la primera mesa demo.")

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

    def _crear_elector(self, data, eleccion, configuracion, sede):
        elector, _ = Elector.objects.update_or_create(
            dni=data["dni"],
            defaults={
                "legajo": data["legajo"],
                "nombre": f"{data['first_name']} {data['last_name']}",
                "correo_electronico": data["email"],
            },
        )
        registro, _ = RegistroPadron.objects.update_or_create(
            elector=elector,
            eleccion=eleccion,
            defaults={
                "eleccion_claustro_departamento": configuracion,
                "sede": sede,
                "activo": True,
            },
        )
        return elector, registro
