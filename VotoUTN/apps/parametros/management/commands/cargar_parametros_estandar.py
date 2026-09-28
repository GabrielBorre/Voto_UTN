from datetime import time

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.notificaciones.models import (
    ComunicacionFechaAdministrativa,
    PlantillaNotificacion,
    VarianteComunicacionFechaAdministrativa,
)
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno
from apps.partidos.models import CargoElectivo, OrganoElectivo


ROL_ELECTOR = [FechaAdministrativa.RolDestinatario.ELECTOR]
ROL_AUTORIDAD = [FechaAdministrativa.RolDestinatario.AUTORIDAD_MESA]

SEDES = ("Medrano", "Campus")
CLAUSTROS = ("Docentes", "Estudiantes", "Graduados", "No docentes")
TURNOS = (
    ("Mañana", time(8), time(13)),
    ("Tarde", time(13), time(18)),
    ("Noche", time(18), time(23)),
)
DEPARTAMENTOS = (
    ("Z", "Ciencias Básicas"),
    ("O", "Ingeniería Civil"),
    ("Q", "Ingeniería en Energía Eléctrica"),
    ("R", "Ingeniería Electrónica"),
    ("I", "Ingeniería Industrial"),
    ("S", "Ingeniería Mecánica"),
    ("U", "Ingeniería Naval"),
    ("V", "Ingeniería Química"),
    ("K", "Ingeniería en Sistemas de Información"),
    ("W", "Ingeniería Textil"),
)

ORGANOS_ELECTIVOS = (
    (
        "Consejo Directivo",
        "Órgano de gobierno de la Facultad Regional con representación de los claustros.",
    ),
    (
        "Consejo Departamental",
        "Órgano de gobierno de cada departamento académico.",
    ),
    (
        "Consejo DASUTeN",
        "Representación electoral ante la obra social universitaria.",
    ),
)

PUESTOS_ELECTIVOS = (
    (
        "Consejo Directivo",
        "Consejero/a directivo/a",
        True,
        False,
        "Puesto de representación general, configurable para uno o más claustros.",
    ),
    (
        "Consejo Departamental",
        "Consejero/a departamental",
        True,
        True,
        "Puesto configurable por claustro y por departamento de forma independiente.",
    ),
    (
        "Consejo DASUTeN",
        "Consejero/a DASUTeN",
        True,
        False,
        "Puesto configurable para los claustros que participan de la elección de DASUTeN.",
    ),
)

FECHAS = (
    ("exhibicion-padron-provisorio", "Exhibición del padrón provisorio", "duracion", 30, ROL_ELECTOR, "electores_activos_padron", "publicacion_padron"),
    ("publicacion-padron-definitivo", "Publicación del padrón definitivo", "fecha_unica", None, ROL_ELECTOR, "electores_activos_padron", "publicacion_padron"),
    ("justificacion-ausencia-electoral", "Justificación ausencia electoral", "duracion", 30, ROL_ELECTOR, "electores_ausentes_confirmados", "ausencia_electoral"),
    ("justificacion-ausencia-autoridad", "Justificación ausencia autoridad", "duracion", 15, ROL_AUTORIDAD, "autoridades_ausentes_confirmadas", "ausencia_autoridad"),
    ("cambio-turno-autoridades", "Cambio turno autoridades", "duracion", 15, ROL_AUTORIDAD, "autoridades_asignadas", "designacion_autoridad"),
    ("capacitacion-obligatoria-autoridades", "Capacitación obligatoria autoridades", "fecha_unica", None, ROL_AUTORIDAD, "autoridades_asignadas", "capacitacion_autoridad"),
)

PLANTILLAS = (
    ("padron-provisorio-apertura-general", "Padrón provisorio: apertura general", "calendario", ROL_ELECTOR, "Padrón provisorio disponible - {nombre_eleccion}", "El padrón provisorio se encuentra disponible del {fecha_inicio} al {fecha_fin}. Su sede preliminar es {sede}."),
    ("padron-provisorio-apertura-cambio-sede", "Padrón provisorio: apertura con cambio de sede", "calendario", ROL_ELECTOR, "Padrón provisorio disponible - {nombre_eleccion}", "El padrón provisorio se encuentra disponible del {fecha_inicio} al {fecha_fin}. Su sede preliminar es {sede}. Puede solicitar un cambio de sede hasta el {fecha_fin} desde {url_accion}."),
    ("padron-provisorio-recordatorio-cambio-sede", "Padrón provisorio: recordatorio de cambio de sede", "calendario", ROL_ELECTOR, "Recordatorio para solicitar cambio de sede - {nombre_eleccion}", "Su sede preliminar es {sede}. Puede solicitar un cambio de sede hasta el {fecha_fin} desde {url_accion}."),
    ("padron-provisorio-proximo-cierre", "Padrón provisorio: próximo cierre", "calendario", ROL_ELECTOR, "Próximo cierre de solicitudes de cambio de sede - {nombre_eleccion}", "El período finaliza el {fecha_fin}. Si todavía está habilitado, puede gestionar el cambio desde {url_accion}."),
    ("padron-provisorio-ultimo-dia-general", "Padrón provisorio: último día general", "calendario", ROL_ELECTOR, "Último día de exhibición del padrón provisorio - {nombre_eleccion}", "Hoy finaliza la exhibición del padrón provisorio. Su sede preliminar es {sede}."),
    ("padron-provisorio-ultimo-dia-cambio", "Padrón provisorio: último día con cambio de sede", "calendario", ROL_ELECTOR, "Último día de exhibición del padrón provisorio - {nombre_eleccion}", "Hoy es el último día para revisar el padrón provisorio y solicitar el cambio de sede desde {url_accion}."),
    ("padron-definitivo-publicado", "Padrón definitivo publicado", "calendario", ROL_ELECTOR, "Padrón definitivo publicado - {nombre_eleccion}", "La votación será el {fecha_votacion}. Su asignación definitiva es sede {sede}, mesa {mesa}, turno {turno} ({horario_turno})."),
    ("votacion-recordatorio-cinco-dias", "Votación: recordatorio cinco días antes", "jornada", ROL_ELECTOR, "Recordatorio de votación - {nombre_eleccion}", "La votación será el {fecha_votacion}. Le corresponde la sede {sede}, mesa {mesa}, turno {turno} ({horario_turno})."),
    ("votacion-recordatorio-hoy", "Votación: recordatorio del día", "jornada", ROL_ELECTOR, "Votación de hoy - {nombre_eleccion}", "Hoy se realiza la votación. Le corresponde la sede {sede}, mesa {mesa}, turno {turno} ({horario_turno})."),
    ("ausencia-electoral-apertura", "Ausencia electoral: apertura de justificación", "calendario", ROL_ELECTOR, "Período de justificación de ausencia electoral - {nombre_eleccion}", "No consta participación electoral registrada. Puede presentar su justificación del {fecha_inicio} al {fecha_fin} desde {url_accion}."),
    ("ausencia-electoral-recordatorio", "Ausencia electoral: recordatorio", "calendario", ROL_ELECTOR, "Recordatorio para justificar ausencia electoral - {nombre_eleccion}", "Todavía puede presentar su justificación hasta el {fecha_fin} desde {url_accion}."),
    ("ausencia-electoral-ultimo-dia", "Ausencia electoral: último día", "calendario", ROL_ELECTOR, "Último día para justificar la ausencia electoral - {nombre_eleccion}", "Hoy finaliza el período para presentar su justificación desde {url_accion}."),
    ("ausencia-autoridad-apertura", "Ausencia de autoridad: apertura de justificación", "calendario", ROL_AUTORIDAD, "Período de justificación de ausencia como autoridad - {nombre_eleccion}", "No consta asistencia registrada en su función del {fecha_votacion}, sede {sede}, mesa {mesa}, turno {turno}. Puede justificar del {fecha_inicio} al {fecha_fin} desde {url_accion}."),
    ("ausencia-autoridad-ultimo-dia", "Ausencia de autoridad: último día", "calendario", ROL_AUTORIDAD, "Último día para justificar la ausencia como autoridad - {nombre_eleccion}", "Hoy finaliza el período para justificar su ausencia como autoridad desde {url_accion}."),
    ("autoridad-designacion", "Autoridad: designación y cambio de turno", "calendario", ROL_AUTORIDAD, "Designación como autoridad de mesa - {nombre_eleccion}", "Fue designado para el {fecha_votacion}, sede {sede}, mesa {mesa}, turno {turno}. Puede confirmar, rechazar o solicitar cambio hasta el {fecha_fin} desde {url_accion}. La asignación actual permanece vigente hasta que la Junta resuelva."),
    ("autoridad-cambio-turno-ultimo-dia", "Autoridad: último día para cambio de turno", "calendario", ROL_AUTORIDAD, "Último día para solicitar cambio de turno - {nombre_eleccion}", "Hoy finaliza el período para solicitar un cambio de turno desde {url_accion}."),
    ("autoridad-capacitacion", "Autoridad: capacitación obligatoria", "calendario", ROL_AUTORIDAD, "Capacitación obligatoria para autoridades de mesa - {nombre_eleccion}", "La capacitación obligatoria será el {fecha_capacitacion} a las {hora_capacitacion}, en {lugar_capacitacion}. Consulte los detalles en {url_accion}."),
    ("cambio-sede-recepcion", "Cambio de sede: recepción", "transaccional", ROL_ELECTOR, "Solicitud de cambio de sede recibida - {nombre_eleccion}", "Recibimos su solicitud el {fecha_presentacion} para la sede {sede_solicitada}. Estado: {estado_solicitud}. Consulte {url_accion}."),
    ("cambio-sede-aprobacion", "Cambio de sede: aprobación", "transaccional", ROL_ELECTOR, "Solicitud de cambio de sede aprobada - {nombre_eleccion}", "Su nueva sede es {sede_solicitada}. Resolución: {observacion_resolucion}. Consulte {url_accion}."),
    ("cambio-sede-rechazo", "Cambio de sede: rechazo", "transaccional", ROL_ELECTOR, "Solicitud de cambio de sede rechazada - {nombre_eleccion}", "Se mantiene su sede actual. Motivo: {observacion_resolucion}. Consulte {url_accion}."),
    ("cambio-turno-recepcion", "Cambio de turno: recepción", "transaccional", ROL_AUTORIDAD, "Solicitud de cambio de turno recibida - {nombre_eleccion}", "Recibimos su solicitud el {fecha_presentacion} para el turno {turno_solicitado}. Estado: {estado_solicitud}. Consulte {url_accion}."),
    ("cambio-turno-aprobacion", "Cambio de turno: aprobación", "transaccional", ROL_AUTORIDAD, "Solicitud de cambio de turno aprobada - {nombre_eleccion}", "Su nuevo turno es {turno_solicitado}. Resolución: {observacion_resolucion}. Consulte {url_accion}."),
    ("cambio-turno-rechazo", "Cambio de turno: rechazo", "transaccional", ROL_AUTORIDAD, "Solicitud de cambio de turno rechazada - {nombre_eleccion}", "Se mantiene su turno actual. Motivo: {observacion_resolucion}. Consulte {url_accion}."),
    ("justificacion-recepcion", "Justificación: recepción", "transaccional", ROL_ELECTOR + ROL_AUTORIDAD, "Justificación recibida - {nombre_eleccion}", "Recibimos su justificación el {fecha_presentacion}. Estado: {estado_solicitud}. Consulte {url_accion}."),
    ("justificacion-aprobacion", "Justificación: aprobación", "transaccional", ROL_ELECTOR + ROL_AUTORIDAD, "Justificación aprobada - {nombre_eleccion}", "Su justificación fue aprobada. Resolución: {observacion_resolucion}. Consulte {url_accion}."),
    ("justificacion-rechazo", "Justificación: rechazo", "transaccional", ROL_ELECTOR + ROL_AUTORIDAD, "Justificación rechazada - {nombre_eleccion}", "Su justificación fue rechazada. Motivo: {observacion_resolucion}. Consulte {url_accion}."),
)

COMUNICACIONES = (
    ("exhibicion-padron-provisorio", "apertura", "Apertura", "inicio", 0, (("padron-provisorio-apertura-cambio-sede", "habilitado_cambio_sede", 1), ("padron-provisorio-apertura-general", "", 2))),
    ("exhibicion-padron-provisorio", "recordatorio", "Recordatorio intermedio", "inicio", 14, (("padron-provisorio-recordatorio-cambio-sede", "habilitado_cambio_sede", 1),)),
    ("exhibicion-padron-provisorio", "proximo-cierre", "Próximo cierre", "fin", -2, (("padron-provisorio-proximo-cierre", "habilitado_cambio_sede", 1),)),
    ("exhibicion-padron-provisorio", "ultimo-dia", "Último día", "fin", 0, (("padron-provisorio-ultimo-dia-cambio", "habilitado_cambio_sede", 1), ("padron-provisorio-ultimo-dia-general", "", 2))),
    ("publicacion-padron-definitivo", "publicacion", "Publicación", "inicio", 0, (("padron-definitivo-publicado", "", 1),)),
    ("justificacion-ausencia-electoral", "apertura", "Apertura", "inicio", 0, (("ausencia-electoral-apertura", "", 1),)),
    ("justificacion-ausencia-electoral", "recordatorio", "Recordatorio intermedio", "inicio", 14, (("ausencia-electoral-recordatorio", "sin_solicitud_presentada", 1),)),
    ("justificacion-ausencia-electoral", "ultimo-dia", "Último día", "fin", 0, (("ausencia-electoral-ultimo-dia", "sin_solicitud_presentada", 1),)),
    ("justificacion-ausencia-autoridad", "apertura", "Apertura", "inicio", 0, (("ausencia-autoridad-apertura", "", 1),)),
    ("justificacion-ausencia-autoridad", "ultimo-dia", "Último día", "fin", 0, (("ausencia-autoridad-ultimo-dia", "sin_solicitud_presentada", 1),)),
    ("cambio-turno-autoridades", "designacion", "Designación", "inicio", 0, (("autoridad-designacion", "", 1),)),
    ("cambio-turno-autoridades", "ultimo-dia", "Último día", "fin", 0, (("autoridad-cambio-turno-ultimo-dia", "autoridad_vigente_sin_solicitud", 1),)),
    ("capacitacion-obligatoria-autoridades", "convocatoria", "Convocatoria", "inicio", 0, (("autoridad-capacitacion", "", 1),)),
)


class Command(BaseCommand):
    help = "Carga o actualiza los parámetros institucionales estándar sin eliminar registros personalizados."

    @transaction.atomic
    def handle(self, *args, **options):
        conteo = {"creados": 0, "actualizados": 0}

        for nombre in SEDES:
            self._upsert(conteo, Sede, {"activa": True}, nombre=nombre)
        for nombre in CLAUSTROS:
            self._upsert(conteo, Claustro, {"activo": True}, nombre=nombre)
        for nombre, inicio, fin in TURNOS:
            self._upsert(conteo, Turno, {"hora_inicio": inicio, "hora_fin": fin, "activo": True}, nombre=nombre)
        for codigo, nombre in DEPARTAMENTOS:
            self._upsert(conteo, Departamento, {"nombre": nombre, "activo": True}, codigo=codigo)

        organos = {}
        for nombre, descripcion in ORGANOS_ELECTIVOS:
            organos[nombre] = self._upsert(
                conteo,
                OrganoElectivo,
                {"descripcion": descripcion, "activo": True},
                nombre=nombre,
            )
        for organo_nombre, nombre, filtra_claustros, filtra_departamentos, descripcion in PUESTOS_ELECTIVOS:
            self._upsert(
                conteo,
                CargoElectivo,
                {
                    "permite_filtrar_claustros": filtra_claustros,
                    "permite_filtrar_departamentos": filtra_departamentos,
                    "descripcion": descripcion,
                    "activo": True,
                },
                organo=organos[organo_nombre],
                nombre=nombre,
            )

        fechas = {}
        for codigo, nombre, modalidad, duracion, roles, criterio, evento in FECHAS:
            fechas[codigo] = self._upsert(
                conteo,
                FechaAdministrativa,
                {
                    "nombre": nombre, "descripcion": "Definición institucional reutilizable.",
                    "modalidad_sugerida": modalidad, "duracion_sugerida_dias": duracion,
                    "roles_destinatarios": roles, "alcance_todos_claustros": True,
                    "criterio_destinatarios": criterio, "evento_disparador_sugerido": evento, "activa": True,
                },
                codigo=codigo,
            )
            fechas[codigo].claustros.clear()

        plantillas = {}
        for codigo, nombre, categoria, roles, asunto, contenido in PLANTILLAS:
            plantillas[codigo] = self._upsert(
                conteo,
                PlantillaNotificacion,
                {
                    "nombre": nombre, "categoria": categoria, "descripcion": "Plantilla institucional estándar.",
                    "asunto": asunto, "contenido": contenido, "roles_destinatarios": roles,
                    "permite_envio_manual": False, "activa": True,
                },
                codigo=codigo,
            )
            plantillas[codigo].claustros.clear()

        for orden, (fecha_codigo, codigo, nombre, referencia, desplazamiento, variantes) in enumerate(COMUNICACIONES, 1):
            comunicacion = self._upsert(
                conteo,
                ComunicacionFechaAdministrativa,
                {"nombre": nombre, "referencia": referencia, "desplazamiento_dias": desplazamiento, "hora_sugerida": time(9), "orden": orden, "activa": True},
                fecha_administrativa=fechas[fecha_codigo], codigo=codigo,
            )
            for plantilla_codigo, criterio, prioridad in variantes:
                self._upsert(
                    conteo,
                    VarianteComunicacionFechaAdministrativa,
                    {"plantilla": plantillas[plantilla_codigo], "criterio_adicional": criterio, "activa": True},
                    comunicacion=comunicacion, prioridad=prioridad,
                )

        self.stdout.write(self.style.SUCCESS(
            f"Parámetros estándar cargados. Creados: {conteo['creados']}. Actualizados: {conteo['actualizados']}."
        ))

    @staticmethod
    def _upsert(conteo, modelo, defaults, **lookup):
        objeto, creado = modelo.objects.update_or_create(defaults=defaults, **lookup)
        conteo["creados" if creado else "actualizados"] += 1
        return objeto
