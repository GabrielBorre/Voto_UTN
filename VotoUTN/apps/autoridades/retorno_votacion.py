"""Intenta restituir la mesa electoral sin desplazar a otras personas."""
from django.db.models import Q
from django.db import transaction
from django.core.exceptions import ValidationError
from types import SimpleNamespace

from apps.mesas.models import AsignacionMesa
from apps.padron.models import AsignacionSedePadron, RegistroPadron, SolicitudCambioSede


@transaction.atomic
def intentar_restituir_mesa(asignacion, usuario):
    destino = asignacion.mesa_votacion_original
    registro = asignacion.registro_padron
    if not destino or RegistroPadron.objects.filter(eleccion_id=registro.eleccion_id, qr_generado_en__isnull=False).exists() or not destino.sede_id or not destino.sede.activa:
        return False
    actual = AsignacionMesa.objects.select_for_update().select_related("mesa").filter(registro_padron=registro).first()
    if not actual or actual.mesa_id == destino.pk:
        return False
    if destino.eleccion_id != registro.eleccion_id or destino.eleccion_claustro_departamento_id != registro.eleccion_claustro_departamento_id:
        return False
    if destino.es_especial != (not registro.es_principal):
        return False
    try:
        destino.clean()
    except ValidationError:
        return False
    aprobada = SolicitudCambioSede.objects.filter(
        registro_padron__eleccion_id=registro.eleccion_id,
        registro_padron__elector_id=registro.elector_id, estado="aprobada",
    ).order_by("-resuelta_en", "-pk").first()
    if aprobada and aprobada.sede_destino_id != destino.sede_id:
        return False
    if actual.mesa.sede_id != destino.sede_id:
        from apps.autoridades.reordenamiento_padron import _planificar_traslado_sin_reordenar
        propuesta = _planificar_traslado_sin_reordenar(registro, destino, verificar_cursada=False)
        if propuesta is None:
            return False
        movimientos = []
        for item, mesa in propuesta:
            fila = AsignacionMesa.objects.select_for_update().select_related("mesa").get(registro_padron=item)
            sede = AsignacionSedePadron.objects.select_for_update(of=("self",)).filter(registro_padron=item).order_by("pk").first()
            if sede is None:
                return False
            movimientos.append((item, mesa, fila, sede))
        for item, mesa, fila, sede in movimientos:
            sede.sede = mesa.sede
            sede.regla_aplicada = None
            sede.estado = AsignacionSedePadron.Estado.ASIGNADA
            sede.full_clean()
            sede.save()
            fila.mesa = mesa
            fila.autoridad_al_final = False
            fila.full_clean()
            fila.save(update_fields=("mesa", "autoridad_al_final"))
        from apps.auditoria.services import registrar_evento
        registrar_evento(accion="autoridades.restitucion_mesa_votacion", entidad="RegistroPadron", entidad_id=registro.pk,
                         eleccion=registro.eleccion, usuario=usuario,
                         datos_nuevos={"movimientos": [{"registro": item.pk, "mesa": mesa.pk} for item, mesa, _, _ in movimientos]})
        return True
    maximo = destino.eleccion_claustro_departamento.eleccion_claustro.maximo_votantes_por_mesa
    if not maximo or AsignacionMesa.objects.filter(mesa=destino).count() >= maximo:
        return False
    filas = list(AsignacionMesa.objects.filter(
        Q(mesa__eleccion_claustro_departamento=destino.eleccion_claustro_departamento, mesa__sede=destino.sede, mesa__es_especial=destino.es_especial)
        | Q(registro_padron=registro)
    ).select_related("mesa").order_by("registro_padron__elector__apellido", "registro_padron__elector__nombre", "registro_padron__elector__legajo", "registro_padron_id"))
    antes = True
    for fila in filas:
        if fila.registro_padron_id == registro.pk:
            antes = False
        elif (antes and fila.mesa.numero > destino.numero) or (not antes and fila.mesa.numero < destino.numero):
            return False
    AsignacionSedePadron.objects.update_or_create(
        registro_padron=registro,
        defaults={"sede": destino.sede, "estado": AsignacionSedePadron.Estado.ASIGNADA, "regla_aplicada": None},
    )
    mesa_anterior_id = actual.mesa_id
    actual.mesa = destino
    actual.autoridad_al_final = False
    actual.save(update_fields=("mesa", "autoridad_al_final"))
    from apps.auditoria.services import registrar_evento
    registrar_evento(accion="autoridades.restitucion_mesa_votacion", entidad="RegistroPadron", entidad_id=registro.pk,
                     eleccion=registro.eleccion, usuario=usuario,
                     datos_anteriores={"mesa": mesa_anterior_id}, datos_nuevos={"mesa": destino.pk})
    return True


def _planificar_retorno_conjunto(asignacion, actual, destino):
    from apps.elecciones.models import EleccionClaustroDepartamentoSede
    from apps.mesas.models import Mesa

    registro = asignacion.registro_padron
    registros = list(RegistroPadron.objects.filter(
        eleccion_id=registro.eleccion_id, elector_id=registro.elector_id, activo=True,
    ).select_related("eleccion", "eleccion_claustro_departamento__eleccion_claustro").order_by("-es_principal", "pk"))
    principales = [item for item in registros if item.es_principal]
    if len(principales) != 1 or not EleccionClaustroDepartamentoSede.objects.filter(
        eleccion_claustro_departamento_id=principales[0].eleccion_claustro_departamento_id,
        sede_id=destino.sede_id, sede__activa=True,
    ).exists():
        raise ValidationError("La sede anterior no está habilitada para el departamento principal.")
    solicitudes = SolicitudCambioSede.objects.filter(
        registro_padron__eleccion_id=registro.eleccion_id,
        registro_padron__elector_id=registro.elector_id,
    )
    if solicitudes.filter(estado="pendiente").exists() or solicitudes.filter(estado="aprobada").exclude(sede_destino_id=destino.sede_id).exists():
        raise ValidationError("Una solicitud de cambio de sede impide el regreso conjunto.")
    movimientos = []
    for item in registros:
        fila = AsignacionMesa.objects.select_related("mesa").filter(registro_padron=item).first()
        if fila is None or fila.mesa.sede_id != actual.mesa.sede_id:
            raise ValidationError("Los registros de la persona no comparten una sede electoral válida.")
        candidatas = [destino] if item.pk == registro.pk else list(Mesa.objects.filter(
            eleccion_id=registro.eleccion_id,
            eleccion_claustro_departamento_id=item.eleccion_claustro_departamento_id,
            sede_id=destino.sede_id, es_especial=not item.es_principal,
        ).select_related("sede", "eleccion_claustro_departamento__eleccion_claustro").order_by("numero", "pk"))
        alternativas = []
        for mesa in candidatas:
            try:
                propuesta = planificar_retorno(SimpleNamespace(registro_padron=item, mesa_votacion_original=mesa), _individual=True)
            except ValidationError:
                continue
            alternativas.append((len(propuesta), mesa.numero, propuesta))
        if not alternativas:
            raise ValidationError("No se puede reubicar a todos los departamentos con las mesas existentes; revisá el caso.")
        movimientos.extend(min(alternativas, key=lambda item: (item[0], item[1]))[2])
    return movimientos


def planificar_retorno(asignacion, *, _individual=False):
    """Propone particiones alfabéticas con la mesa anterior y los cupos existentes."""
    from apps.autoridades.models import AsignacionAutoridad
    from apps.mesas.models import Mesa

    registro = asignacion.registro_padron
    destino = asignacion.mesa_votacion_original
    actual = AsignacionMesa.objects.select_related("mesa").filter(registro_padron=registro).first()
    if not destino or not actual or actual.mesa_id == destino.pk:
        raise ValidationError("No hay un regreso a mesa anterior pendiente.")
    if not _individual and actual.mesa.sede_id != destino.sede_id and RegistroPadron.objects.filter(
        eleccion_id=registro.eleccion_id, elector_id=registro.elector_id, activo=True,
    ).exclude(pk=registro.pk).exists():
        return _planificar_retorno_conjunto(asignacion, actual, destino)
    if RegistroPadron.objects.filter(eleccion_id=registro.eleccion_id, qr_generado_en__isnull=False).exists() or destino.eleccion_id != registro.eleccion_id or destino.eleccion_claustro_departamento_id != registro.eleccion_claustro_departamento_id:
        raise ValidationError("La mesa anterior ya no está disponible para este padrón.")
    if not destino.sede_id or not destino.sede.activa or destino.es_especial != (not registro.es_principal):
        raise ValidationError("La sede anterior ya no está habilitada.")
    try:
        destino.clean()
    except ValidationError as error:
        raise ValidationError("La sede anterior ya no está habilitada.") from error
    aprobada = SolicitudCambioSede.objects.filter(
        registro_padron__eleccion_id=registro.eleccion_id,
        registro_padron__elector_id=registro.elector_id, estado="aprobada",
    ).order_by("-resuelta_en", "-pk").first()
    if aprobada and aprobada.sede_destino_id != destino.sede_id:
        raise ValidationError("El regreso contradice una solicitud de sede aprobada; requiere revisión de la Junta.")
    maximo = destino.eleccion_claustro_departamento.eleccion_claustro.maximo_votantes_por_mesa
    if not maximo:
        raise ValidationError("Configurá la capacidad de las mesas antes de revisar el regreso.")
    sede_ids = {actual.mesa.sede_id, destino.sede_id}
    mesas = list(Mesa.objects.filter(eleccion=registro.eleccion, eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
                                     sede_id__in=sede_ids, es_especial=destino.es_especial).select_related("sede").order_by("numero", "pk"))
    filas = list(AsignacionMesa.objects.filter(mesa__in=mesas, registro_padron__activo=True).select_related(
        "mesa", "registro_padron__elector", "registro_padron__asignacion_autoridad",
    ).order_by("registro_padron__elector__apellido", "registro_padron__elector__nombre", "registro_padron__elector__legajo", "registro_padron_id"))
    if any(f.registro_padron.qr_generado_en for f in filas):
        raise ValidationError("No se puede modificar un padrón con QR emitidos.")
    por_id = {f.registro_padron_id: f for f in filas}
    if registro.pk not in por_id:
        raise ValidationError("El elector ya no tiene una asignación electoral válida.")
    movimientos = []
    for sede_id in sede_ids:
        mesas_sede = [m for m in mesas if m.sede_id == sede_id]
        electores = [f for f in filas if (f.registro_padron_id == registro.pk and sede_id == destino.sede_id)
                     or (f.registro_padron_id != registro.pk and f.mesa.sede_id == sede_id)]
        n, m = len(electores), len(mesas_sede)
        if not m or n < m or n > m * maximo:
            raise ValidationError("No se puede respetar el orden y la capacidad con las mesas existentes; revisá el caso.")
        estados = {0: (0, [])}
        for indice, mesa in enumerate(mesas_sede):
            siguientes = {}
            for inicio, (costo, cortes) in estados.items():
                for fin in range(inicio + 1, min(n, inicio + maximo) + 1):
                    if not (m - indice - 1 <= n - fin <= (m - indice - 1) * maximo):
                        continue
                    bloque = electores[inicio:fin]
                    if any(f.registro_padron_id == registro.pk and mesa.pk != destino.pk for f in bloque):
                        continue
                    if any(f.registro_padron_id != registro.pk and f.mesa_id != mesa.pk and
                           getattr(f.registro_padron, "asignacion_autoridad", None) and
                           f.registro_padron.asignacion_autoridad.estado == AsignacionAutoridad.Estado.ASIGNADA for f in bloque):
                        continue
                    nuevo_costo = costo + sum(f.mesa_id != mesa.pk for f in bloque)
                    if fin not in siguientes or nuevo_costo < siguientes[fin][0]:
                        siguientes[fin] = (nuevo_costo, cortes + [(mesa, bloque)])
            estados = siguientes
        if n not in estados:
            raise ValidationError("No se puede regresar a la mesa anterior sin afectar autoridades confirmadas; revisá el caso.")
        for mesa, bloque in estados[n][1]:
            for fila in bloque:
                if fila.mesa_id != mesa.pk:
                    movimientos.append({"registro": fila.registro_padron_id, "elector": fila.registro_padron.elector.nombre_completo,
                                        "origen": fila.mesa.codigo, "destino": mesa.codigo, "mesa_id": mesa.pk})
    return movimientos
