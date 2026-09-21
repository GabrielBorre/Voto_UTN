import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
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
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    ListaCandidatos,
    ParticipacionPartido,
    PuestoEleccion,
)
from apps.usuarios.models import AsignacionRol, PerfilUsuario


PRESENTACIONES_DEMO = (
    {
        "codigo": "docentes-sistemas-lista-3",
        "claustro": "Docentes",
        "numero": "3",
        "nombre": "SISTEMAS",
        "apoderado": "Andrés Fabián Carosella",
        "listas": (
            ("directivo", (("1090", "REINOSA, Enrique Jose"), ("1159", "SACLIER, Lucas Javier"))),
            ("departamental", (("453", "ESTAYNO, Marcelo Gustavo"), ("1370", "ZAKHEM, Yamila Ariadna"))),
        ),
    },
    {
        "codigo": "docentes-dasuten-lista-3",
        "claustro": "Docentes",
        "numero": "3",
        "nombre": "INTEGRACIÓN DOCENTE",
        "apoderado": "Nicolás Zabrana",
        "listas": (
            ("dasuten", (("1181", "SANCHEZ, Pablo Cesar Vicente"), ("114", "BARBERIO LAJE, Milena Trinidad"))),
        ),
    },
    {
        "codigo": "nodocentes-lista-9",
        "claustro": "No docentes",
        "numero": "9",
        "nombre": "UNIÓN Y PARTICIPACIÓN",
        "apoderado": "Mariano De Luca",
        "listas": (
            ("directivo", (("25", "BONANNI, Pablo Fabián"), ("188", "SACK, María Eugenia"))),
            ("dasuten", (("171", "RIPOLL, Walter Adrian"), ("94", "IBARROLA, Lidia Valentina"))),
        ),
    },
    {
        "codigo": "estudiantes-lista-19",
        "claustro": "Estudiantes",
        "numero": "19",
        "nombre": "19 DE AGOSTO",
        "apoderado": "Malena Rivas",
        "listas": (
            ("directivo", (("21523", "RIVAS, Malena"), ("18858", "PALAVECINO, Sofía Ornella"))),
            ("departamental", (("26336", "VENCE, Joaquin"), ("16352", "MELCHIORI CALLEGHER, Lautaro Agustín"))),
        ),
    },
    {
        "codigo": "estudiantes-lista-3",
        "claustro": "Estudiantes",
        "numero": "3",
        "nombre": "FRANJA MORADA TECNOLÓGICA",
        "apoderado": "Franco Licciardi",
        "listas": (
            ("directivo", (("23388", "SANTOS, Ana"), ("20286", "PORMI, Matias Ezequiel"))),
            ("departamental", (("20286", "PORMI, Matias Ezequiel"), ("16673", "MICELI, Catriel Baltasar"))),
        ),
    },
    {
        "codigo": "estudiantes-lista-10",
        "claustro": "Estudiantes",
        "numero": "10",
        "nombre": "INNOVACIÓN TECNOLÓGICA",
        "apoderado": "Gustavo Gabriel Niz",
        "listas": (
            ("directivo", (("8349", "ESCALANTE GONZALEZ, Braian Victor"), ("11910", "GUGLIELMINO, Santiago"))),
            ("departamental", (("16520", "MENDOZA QUISPE, Ariel Marcelo"), ("18585", "OSA POCHELU, Valentín Rodrigo"))),
        ),
    },
    {
        "codigo": "estudiantes-lista-16",
        "claustro": "Estudiantes",
        "numero": "16",
        "nombre": "La UES",
        "apoderado": "Ignacio Nicolás Brandariz",
        "listas": (
            ("directivo", (("ues-est-1", "BRANDARIZ, Ignacio Nicolas"), ("ues-est-2", "ROLDAN, Leila Sofia"))),
            ("departamental", (("ues-sis-1", "BRANDARIZ, Ignacio Nicolas"), ("ues-sis-2", "TADIC, Facundo Agustin"))),
        ),
    },
    {
        "codigo": "graduados-lista-19",
        "claustro": "Graduados",
        "numero": "19",
        "nombre": "19 DE AGOSTO",
        "apoderado": "Malena Rivas",
        "listas": (
            ("directivo", (("14257", "LOPEZ BISIO, Martina Azul"), ("314", "AGUIRRE DAUD, Juan Manuel"))),
            ("departamental", (("7555", "DIGON, Hernan Gabriel"), ("1158", "ARCE JOFRE, Fabian Leandro"))),
        ),
    },
    {
        "codigo": "graduados-lista-3",
        "claustro": "Graduados",
        "numero": "3",
        "nombre": "INTEGRACIÓN - CLUB DEL GRADUADO",
        "apoderado": "Damián Salinas",
        "listas": (
            ("directivo", (("10229", "GARCIA CUNIGLIO, Debora Alicia"), ("7091", "DELLA PITTIMA, Marcos Alberto"))),
            ("departamental", (("9526", "FRANZO, Paula Romina"), ("6406", "D'ALESSANDRO, Juan Jose"))),
        ),
    },
    {
        "codigo": "graduados-lista-10",
        "claustro": "Graduados",
        "numero": "10",
        "nombre": "MOGRAT / La UES",
        "apoderado": "Héctor Bargiela",
        "listas": (
            ("directivo", (("1912", "BARGIELA, Héctor Marcelo"), ("20687", "RIBERA, Emilio José Ramón"))),
            ("departamental", (("26111", "WEJEMAN, Pablo Maximiliano"), ("16180", "MENDIETA, Nancy Mabel"))),
        ),
    },
)


class Command(BaseCommand):
    help = "Carga los parámetros estándar y una elección demo integral, de forma idempotente."

    @transaction.atomic
    def handle(self, *args, **options):
        counters = {"created": 0, "updated": 0}

        call_command("cargar_parametros_estandar", stdout=self.stdout)
        sede_central, turno_manana, turno_tarde, claustros, departamento_sistemas = self._seed_catalogos()
        eleccion, elecciones_claustro, configuraciones_departamento = self._seed_eleccion(
            sede_central,
            turno_manana,
            turno_tarde,
            claustros,
            departamento_sistemas,
            counters,
        )
        eleccion_claustro = elecciones_claustro["Docentes"]
        configuracion_departamento = configuraciones_departamento["Docentes"]
        mesas = self._seed_mesas(eleccion, configuracion_departamento, sede_central, turno_manana, turno_tarde, counters)
        usuarios = self._seed_usuarios_y_roles(eleccion, sede_central, mesas, counters)
        padrones = self._seed_electores_y_padron(eleccion, configuracion_departamento, sede_central, mesas, counters)
        puestos = self._seed_puestos(elecciones_claustro, configuraciones_departamento, counters)
        self._seed_presentaciones(eleccion, elecciones_claustro, configuraciones_departamento, puestos, counters)

        tipo_justificativo, fecha_admin, plantilla = self._seed_configuracion_operativa(claustros["Docentes"], counters)
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

    def _seed_catalogos(self):
        claustros = {
            nombre: Claustro.objects.get(nombre=nombre)
            for nombre in ("Docentes", "Estudiantes", "Graduados", "No docentes")
        }
        return (
            Sede.objects.get(nombre="Campus"),
            Turno.objects.get(nombre="Mañana"),
            Turno.objects.get(nombre="Tarde"),
            claustros,
            Departamento.objects.get(codigo="K"),
        )

    def _seed_eleccion(self, sede, turno_manana, turno_tarde, claustros, departamento, counters):
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
        self._get_or_create(counters, EleccionTurno.objects, eleccion=eleccion, turno=turno_manana)
        self._get_or_create(counters, EleccionTurno.objects, eleccion=eleccion, turno=turno_tarde)
        elecciones_claustro = {}
        configuraciones_departamento = {}
        for nombre, claustro in claustros.items():
            eleccion_claustro = self._upsert(
                counters,
                EleccionClaustro.objects,
                eleccion=eleccion,
                claustro=claustro,
                defaults={"fecha_votacion": inicio.date(), "maximo_votantes_por_mesa": 500},
            )
            elecciones_claustro[nombre] = eleccion_claustro
            self._get_or_create(
                counters,
                EleccionClaustroSede.objects,
                eleccion_claustro=eleccion_claustro,
                sede=sede,
            )
            if nombre == "No docentes":
                continue
            configuracion_departamento = self._get_or_create(
                counters,
                EleccionClaustroDepartamento.objects,
                eleccion_claustro=eleccion_claustro,
                departamento=departamento,
            )
            configuraciones_departamento[nombre] = configuracion_departamento
            self._get_or_create(
                counters,
                EleccionClaustroDepartamentoSede.objects,
                eleccion_claustro_departamento=configuracion_departamento,
                sede=sede,
            )

        return eleccion, elecciones_claustro, configuraciones_departamento

    def _seed_puestos(self, elecciones_claustro, configuraciones_departamento, counters):
        cargos = {
            "directivo": CargoElectivo.objects.get(
                organo__nombre="Consejo Directivo",
                nombre="Consejero/a directivo/a",
            ),
            "departamental": CargoElectivo.objects.get(
                organo__nombre="Consejo Departamental",
                nombre="Consejero/a departamental",
            ),
            "dasuten": CargoElectivo.objects.get(
                organo__nombre="Consejo DASUTeN",
                nombre="Consejero/a DASUTeN",
            ),
        }
        cantidades = {
            "Docentes": {"directivo": 2, "departamental": 10, "dasuten": 2},
            "No docentes": {"directivo": 2, "dasuten": 2},
            "Estudiantes": {"directivo": 10, "departamental": 6},
            "Graduados": {"directivo": 10, "departamental": 4},
        }
        puestos = {}
        for claustro_nombre, configuracion in cantidades.items():
            for tipo, cantidad in configuracion.items():
                alcance_departamental = (
                    configuraciones_departamento[claustro_nombre]
                    if tipo == "departamental"
                    else None
                )
                puestos[(claustro_nombre, tipo)] = self._upsert(
                    counters,
                    PuestoEleccion.objects,
                    puesto=cargos[tipo],
                    eleccion_claustro=elecciones_claustro[claustro_nombre],
                    eleccion_claustro_departamento=alcance_departamental,
                    defaults={
                        "cantidad_titulares": cantidad,
                        "cantidad_suplentes": 0,
                        "activo": True,
                    },
                )
        return puestos

    def _seed_presentaciones(
        self,
        eleccion,
        elecciones_claustro,
        configuraciones_departamento,
        puestos,
        counters,
    ):
        for datos in PRESENTACIONES_DEMO:
            claustro_nombre = datos["claustro"]
            eleccion_claustro = elecciones_claustro[claustro_nombre]
            presentacion = self._upsert(
                counters,
                ParticipacionPartido.objects,
                eleccion=eleccion,
                codigo_presentacion=datos["codigo"],
                defaults={
                    "partido": None,
                    "eleccion_claustro": eleccion_claustro,
                    "numero_lista": datos["numero"],
                    "nombre_lista": datos["nombre"],
                    "apoderado_nombre": datos["apoderado"],
                    "apoderado_email": "",
                    "activa": True,
                },
            )
            for tipo_puesto, candidatos in datos["listas"]:
                puesto_eleccion = puestos[(claustro_nombre, tipo_puesto)]
                alcance_departamental = (
                    configuraciones_departamento[claustro_nombre]
                    if tipo_puesto == "departamental"
                    else None
                )
                lista = self._upsert(
                    counters,
                    ListaCandidatos.objects,
                    participacion=presentacion,
                    puesto_eleccion=puesto_eleccion,
                    defaults={
                        "eleccion_claustro": eleccion_claustro,
                        "eleccion_claustro_departamento": alcance_departamental,
                        "nombre": f"Lista {datos['numero']} - {datos['nombre']}",
                        "activa": True,
                    },
                )
                for orden, (identificador, nombre) in enumerate(candidatos, 1):
                    self._upsert(
                        counters,
                        Candidato.objects,
                        lista=lista,
                        tipo=Candidato.Tipo.TITULAR,
                        orden=orden,
                        defaults={
                            "elector": None,
                            "nombre": nombre,
                            "identificador_persona": identificador,
                            "dni": "",
                            "correo_electronico": "",
                            "cargo": puesto_eleccion.puesto.nombre,
                            "activo": True,
                        },
                    )

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
