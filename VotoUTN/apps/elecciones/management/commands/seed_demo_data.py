import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionSede,
    EleccionTurno,
    FechaAdministrativaEleccion,
)
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.mesas.models import AsignacionMesa, Mesa
from apps.notificaciones.models import EnvioNotificacion, PlantillaNotificacion
from apps.padron.models import Elector, ErrorImportacionPadron, ImportacionPadron, RegistroPadron
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno
from apps.usuarios.models import AsignacionRol, PerfilUsuario


class Command(BaseCommand):
    help = "Carga un conjunto reducido de datos demo en los modelos principales del sistema."

    @transaction.atomic
    def handle(self, *args, **options):
        counters = {"created": 0, "updated": 0}

        sede_central, turno_manana, turno_tarde, claustro_docentes, departamento_sistemas = self._seed_catalogos(counters)
        eleccion, eleccion_claustro, configuracion_departamento = self._seed_eleccion(
            sede_central,
            turno_manana,
            turno_tarde,
            claustro_docentes,
            departamento_sistemas,
            counters,
        )
        mesas = self._seed_mesas(eleccion, configuracion_departamento, sede_central, turno_manana, turno_tarde, counters)
        usuarios = self._seed_usuarios_y_roles(eleccion, sede_central, mesas, counters)
        padrones = self._seed_electores_y_padron(eleccion, configuracion_departamento, sede_central, mesas, counters)

        tipo_justificativo, fecha_admin, plantilla = self._seed_configuracion_operativa(claustro_docentes, counters)
        self._seed_registros_operativos(
            eleccion,
            eleccion_claustro,
            usuarios,
            padrones,
            mesas,
            turno_manana,
            tipo_justificativo,
            fecha_admin,
            plantilla,
            counters,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Seed demo completado. "
                f"Registros creados: {counters['created']}. "
                f"Registros actualizados: {counters['updated']}."
            )
        )

    def _upsert(self, counters, manager, defaults=None, **lookup):
        instance, created = manager.update_or_create(defaults=defaults or {}, **lookup)
        counters["created" if created else "updated"] += 1
        return instance

    def _get_or_create(self, counters, manager, defaults=None, **lookup):
        instance, created = manager.get_or_create(defaults=defaults or {}, **lookup)
        counters["created" if created else "updated"] += 1
        return instance

    def _seed_catalogos(self, counters):
        sede_central = self._upsert(counters, Sede.objects, nombre="Campus Central", defaults={"activa": True})
        claustro_docentes = self._upsert(counters, Claustro.objects, nombre="Docentes", defaults={"activo": True})
        departamento_sistemas = self._upsert(
            counters,
            Departamento.objects,
            codigo="DSI",
            defaults={"nombre": "Departamento de Sistemas", "activo": True},
        )
        turno_manana = self._upsert(
            counters,
            Turno.objects,
            nombre="Manana",
            defaults={"hora_inicio": "08:00", "hora_fin": "12:00", "activo": True},
        )
        turno_tarde = self._upsert(
            counters,
            Turno.objects,
            nombre="Tarde",
            defaults={"hora_inicio": "13:00", "hora_fin": "17:00", "activo": True},
        )
        return sede_central, turno_manana, turno_tarde, claustro_docentes, departamento_sistemas

    def _seed_eleccion(self, sede, turno_manana, turno_tarde, claustro, departamento, counters):
        now = timezone.now()
        inicio = now + timedelta(days=3)
        fin = inicio + timedelta(days=1)

        eleccion = self._upsert(
            counters,
            Eleccion.objects,
            nombre="Eleccion Demo 2026",
            defaults={
                "fecha_inicio": inicio,
                "fecha_fin": fin,
                "fecha_apertura_padron_provisorio": (inicio - timedelta(days=20)).date(),
                "fecha_cierre_padron_provisorio": (inicio - timedelta(days=15)).date(),
                "fecha_cierre_candidaturas": (inicio - timedelta(days=10)).date(),
                "fecha_publicacion_padron_definitivo": (inicio - timedelta(days=7)).date(),
                "fecha_limite_justificacion_autoridades": (fin + timedelta(days=3)).date(),
                "fecha_limite_justificacion_electores": (fin + timedelta(days=5)).date(),
                "estado": Eleccion.Estado.PREPARADA,
                "habilitada": True,
                "maximo_autoridades_por_mesa": 2,
            },
        )

        self._get_or_create(counters, EleccionSede.objects, eleccion=eleccion, sede=sede)
        eleccion_claustro = self._get_or_create(
            counters,
            EleccionClaustro.objects,
            eleccion=eleccion,
            claustro=claustro,
            defaults={"fecha_votacion": inicio.date(), "maximo_votantes_por_mesa": 500},
        )
        self._get_or_create(counters, EleccionTurno.objects, eleccion=eleccion, turno=turno_manana)
        self._get_or_create(counters, EleccionTurno.objects, eleccion=eleccion, turno=turno_tarde)
        self._get_or_create(counters, EleccionClaustroSede.objects, eleccion_claustro=eleccion_claustro, sede=sede)
        configuracion_departamento = self._get_or_create(
            counters,
            EleccionClaustroDepartamento.objects,
            eleccion_claustro=eleccion_claustro,
            departamento=departamento,
        )
        self._get_or_create(
            counters,
            EleccionClaustroDepartamentoSede.objects,
            eleccion_claustro_departamento=configuracion_departamento,
            sede=sede,
        )

        return eleccion, eleccion_claustro, configuracion_departamento

    def _seed_mesas(self, eleccion, configuracion_departamento, sede, turno_manana, turno_tarde, counters):
        mesa_1 = self._upsert(
            counters,
            Mesa.objects,
            eleccion=eleccion,
            numero=1,
            defaults={
                "eleccion_claustro_departamento": configuracion_departamento,
                "sede": sede,
                "turno": turno_manana,
                "generada_automaticamente": False,
            },
        )
        mesa_2 = self._upsert(
            counters,
            Mesa.objects,
            eleccion=eleccion,
            numero=2,
            defaults={
                "eleccion_claustro_departamento": configuracion_departamento,
                "sede": sede,
                "turno": turno_tarde,
                "generada_automaticamente": False,
            },
        )
        return {"mesa_1": mesa_1, "mesa_2": mesa_2}

    def _get_or_create_user(self, counters, username, *, email, first_name, last_name, password, is_staff=False, is_superuser=False):
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
            },
        )
        counters["created" if created else "updated"] += 1

        dirty = False
        for field, value in {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "is_staff": is_staff,
            "is_superuser": is_superuser,
            "is_active": True,
        }.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                dirty = True

        if not user.check_password(password):
            user.set_password(password)
            dirty = True

        if dirty:
            user.save()
        return user

    def _seed_usuarios_y_roles(self, eleccion, sede, mesas, counters):
        usuarios = {
            "admin_sistema": self._get_or_create_user(
                counters,
                "admin_sistema_demo",
                email="admin.sistema.demo@utn.local",
                first_name="Admin",
                last_name="Sistema",
                password="demo1234",
                is_staff=True,
                is_superuser=True,
            ),
            "admin_junta": self._get_or_create_user(
                counters,
                "admin_junta_demo",
                email="admin.junta.demo@utn.local",
                first_name="Admin",
                last_name="Junta",
                password="demo1234",
                is_staff=True,
            ),
            "administrativo": self._get_or_create_user(
                counters,
                "administrativo_demo",
                email="administrativo.demo@utn.local",
                first_name="Operador",
                last_name="Junta",
                password="demo1234",
            ),
            "autoridad": self._get_or_create_user(
                counters,
                "autoridad_demo",
                email="autoridad.demo@utn.local",
                first_name="Ana",
                last_name="Autoridad",
                password="demo1234",
            ),
            "elector": self._get_or_create_user(
                counters,
                "elector_demo",
                email="elector.demo@utn.local",
                first_name="Eva",
                last_name="Electora",
                password="demo1234",
            ),
        }

        self._upsert(
            counters,
            AsignacionRol.objects,
            usuario=usuarios["admin_sistema"],
            rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA,
            eleccion=None,
            sede=None,
            mesa=None,
            defaults={"activo": True},
        )
        self._upsert(
            counters,
            AsignacionRol.objects,
            usuario=usuarios["admin_junta"],
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=eleccion,
            sede=sede,
            mesa=None,
            defaults={"activo": True},
        )
        self._upsert(
            counters,
            AsignacionRol.objects,
            usuario=usuarios["administrativo"],
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
            eleccion=eleccion,
            sede=sede,
            mesa=None,
            defaults={"activo": True},
        )
        self._upsert(
            counters,
            AsignacionRol.objects,
            usuario=usuarios["autoridad"],
            rol=AsignacionRol.Rol.AUTORIDAD_MESA,
            eleccion=eleccion,
            sede=sede,
            mesa=mesas["mesa_1"],
            defaults={"activo": True},
        )
        self._upsert(
            counters,
            AsignacionRol.objects,
            usuario=usuarios["elector"],
            rol=AsignacionRol.Rol.ELECTOR,
            eleccion=eleccion,
            sede=None,
            mesa=None,
            defaults={"activo": True},
        )

        return usuarios

    def _seed_electores_y_padron(self, eleccion, configuracion_departamento, sede, mesas, counters):
        electores_data = [
            {"legajo": "990001", "nombre": "Ana Autoridad", "dni": "40000001", "correo": "ana.autoridad@utn.local", "mesa": mesas["mesa_1"]},
            {"legajo": "990002", "nombre": "Eva Electora", "dni": "40000002", "correo": "eva.electora@utn.local", "mesa": mesas["mesa_1"]},
            {"legajo": "990003", "nombre": "Carlos Votante", "dni": "40000003", "correo": "carlos.votante@utn.local", "mesa": mesas["mesa_2"]},
        ]

        padrones = {}
        for data in electores_data:
            elector = self._upsert(
                counters,
                Elector.objects,
                legajo=data["legajo"],
                defaults={
                    "nombre": data["nombre"],
                    "dni": data["dni"],
                    "correo_electronico": data["correo"],
                },
            )
            padron = self._upsert(
                counters,
                RegistroPadron.objects,
                elector=elector,
                eleccion=eleccion,
                defaults={
                    "eleccion_claustro_departamento": configuracion_departamento,
                    "sede": sede,
                    "activo": True,
                },
            )
            self._upsert(counters, AsignacionMesa.objects, registro_padron=padron, defaults={"mesa": data["mesa"]})
            padrones[data["legajo"]] = padron

        return padrones

    def _seed_configuracion_operativa(self, claustro, counters):
        tipo_justificativo = self._upsert(
            counters,
            TipoJustificativo.objects,
            nombre="Certificado medico",
            defaults={"activo": True},
        )
        fecha_admin = self._upsert(
            counters,
            FechaAdministrativa.objects,
            codigo="apertura-justificativos-demo",
            nombre="Apertura de justificativos",
            defaults={
                "roles_destinatarios": [
                    FechaAdministrativa.RolDestinatario.ADMINISTRADOR_JUNTA,
                    FechaAdministrativa.RolDestinatario.ELECTOR,
                ],
                "descripcion": "Apertura de justificativos de la elección de demostración.",
                "modalidad_sugerida": FechaAdministrativa.ModalidadSugerida.FECHA_UNICA,
                "alcance_todos_claustros": False,
                "criterio_destinatarios": FechaAdministrativa.CriterioDestinatarios.TODOS_EN_ALCANCE,
                "activa": True,
            },
        )
        fecha_admin.claustros.set([claustro])

        plantilla = self._upsert(
            counters,
            PlantillaNotificacion.objects,
            codigo="notificacion-demo",
            nombre="Notificacion demo",
            defaults={
                "categoria": PlantillaNotificacion.Categoria.MANUAL,
                "descripcion": "Plantilla manual para datos de demostración.",
                "asunto": "Recordatorio de votacion",
                "contenido": "Tu mesa y turno ya estan disponibles en el sistema.",
                "roles_destinatarios": [
                    FechaAdministrativa.RolDestinatario.ELECTOR,
                    FechaAdministrativa.RolDestinatario.AUTORIDAD_MESA,
                ],
                "permite_envio_manual": True,
                "activa": True,
            },
        )
        plantilla.claustros.set([claustro])

        return tipo_justificativo, fecha_admin, plantilla

    def _seed_registros_operativos(
        self,
        eleccion,
        eleccion_claustro,
        usuarios,
        padrones,
        mesas,
        turno_manana,
        tipo_justificativo,
        fecha_admin,
        plantilla,
        counters,
    ):
        padron_autoridad = padrones["990001"]
        padron_electora = padrones["990002"]
        padron_otro = padrones["990003"]

        self._upsert(counters, PerfilUsuario.objects, usuario=usuarios["autoridad"], defaults={"elector": padron_autoridad.elector, "activo": True})
        self._upsert(counters, PerfilUsuario.objects, usuario=usuarios["elector"], defaults={"elector": padron_electora.elector, "activo": True})

        candidatura = self._upsert(
            counters,
            CandidaturaAutoridad.objects,
            registro_padron=padron_autoridad,
            defaults={"cargada_por": usuarios["admin_junta"]},
        )
        self._upsert(
            counters,
            AsignacionAutoridad.objects,
            registro_padron=padron_autoridad,
            defaults={
                "candidatura": candidatura,
                "mesa": mesas["mesa_1"],
                "estado": AsignacionAutoridad.Estado.CONFIRMADA,
                "asignada_por": usuarios["admin_junta"],
                "respondida_en": timezone.now(),
            },
        )
        self._upsert(
            counters,
            PreferenciaAutoridad.objects,
            registro_padron=padron_autoridad,
            defaults={
                "sede_preferida": padron_autoridad.sede,
                "turno_preferido": turno_manana,
                "disponible": True,
            },
        )

        justificativo = self._upsert(
            counters,
            JustificativoAusencia.objects,
            registro_padron=padron_otro,
            tipo=tipo_justificativo,
            defaults={
                "detalle": "No podra asistir por viaje academico.",
                "estado": JustificativoAusencia.Estado.APROBADO,
                "resuelta_por": usuarios["administrativo"],
                "resuelta_en": timezone.now(),
                "observacion_resolucion": "Documentacion validada.",
            },
        )
        if justificativo.estado != JustificativoAusencia.Estado.APROBADO:
            justificativo.estado = JustificativoAusencia.Estado.APROBADO
            justificativo.resuelta_por = usuarios["administrativo"]
            justificativo.resuelta_en = timezone.now()
            justificativo.observacion_resolucion = "Documentacion validada."
            justificativo.save(update_fields=["estado", "resuelta_por", "resuelta_en", "observacion_resolucion"])

        self._upsert(
            counters,
            RegistroParticipacion.objects,
            registro_padron=padron_electora,
            defaults={
                "mesa": mesas["mesa_1"],
                "registrada_por": usuarios["autoridad"],
                "metodo": RegistroParticipacion.Metodo.MANUAL,
            },
        )
        contenido_padron = b"legajo,nombre,dni\n990001,Ana Autoridad,40000001\n990002,Eva Electora,40000002\n"
        huella = hashlib.sha256(contenido_padron).hexdigest()
        importacion = self._get_or_create(
            counters,
            ImportacionPadron.objects,
            eleccion=eleccion,
            eleccion_claustro=eleccion_claustro,
            nombre_archivo="padron_demo.csv",
            defaults={
                "huella_archivo": huella,
                "estado": ImportacionPadron.Estado.CONFIRMADA,
                "cantidad_filas": 2,
                "cantidad_validas": 2,
                "cantidad_errores": 0,
                "usuario": usuarios["admin_junta"],
            },
        )
        importacion.huella_archivo = huella
        importacion.estado = ImportacionPadron.Estado.CONFIRMADA
        importacion.cantidad_filas = 2
        importacion.cantidad_validas = 2
        importacion.cantidad_errores = 1
        importacion.usuario = usuarios["admin_junta"]
        if not importacion.archivo:
            importacion.archivo.save("padron_demo.csv", ContentFile(contenido_padron), save=False)
        importacion.save()

        self._upsert(
            counters,
            ErrorImportacionPadron.objects,
            importacion=importacion,
            fila=4,
            campo="dni",
            defaults={"mensaje": "DNI duplicado en padron original."},
        )

        self._upsert(
            counters,
            FechaAdministrativaEleccion.objects,
            eleccion=eleccion,
            fecha_administrativa=fecha_admin,
            defaults={"fecha": eleccion.fecha_inicio.date()},
        )

        self._upsert(
            counters,
            EnvioNotificacion.objects,
            plantilla=plantilla,
            eleccion=eleccion,
            destinatario=usuarios["elector"],
            asunto=plantilla.asunto,
            defaults={
                "contenido": "Recordatorio automatico para la eleccion demo.",
                "estado": EnvioNotificacion.Estado.ENVIADO,
                "error": "",
            },
        )
