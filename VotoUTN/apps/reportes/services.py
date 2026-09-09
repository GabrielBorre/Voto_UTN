import csv

from django.http import Http404, HttpResponse

from apps.asistencia.models import RegistroParticipacion
from apps.autoridades.models import AsignacionAutoridad
from apps.justificativos.models import JustificativoAusencia


def valor_csv(valor):
    texto = "" if valor is None else str(valor)
    return f"'{texto}" if texto.startswith(("=", "+", "-", "@")) else texto


def crear_respuesta_csv(nombre_archivo):
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    respuesta.write("\ufeff")
    return respuesta


def exportar_reporte_eleccion(eleccion, tipo):
    respuesta = crear_respuesta_csv(f"{tipo}_{eleccion.id}.csv")
    escritor = csv.writer(respuesta)

    if tipo == "padron":
        escritor.writerow(("dni", "legajo", "nombre", "correo", "claustro", "departamento", "sede", "mesa"))
        for registro in eleccion.registros_padron.select_related(
            "elector",
            "sede",
            "eleccion_claustro_departamento__departamento",
            "eleccion_claustro_departamento__eleccion_claustro__claustro",
            "asignacion_mesa__mesa",
        ):
            escritor.writerow(
                [
                    valor_csv(valor)
                    for valor in (
                        registro.elector.dni,
                        registro.elector.legajo,
                        registro.elector.nombre,
                        registro.elector.correo_electronico,
                        registro.eleccion_claustro_departamento.eleccion_claustro.claustro,
                        registro.eleccion_claustro_departamento.departamento,
                        registro.sede,
                        getattr(getattr(registro, "asignacion_mesa", None), "mesa", None),
                    )
                ]
            )
    elif tipo == "mesas":
        escritor.writerow(("numero", "claustro", "departamento", "sede", "turno", "origen"))
        for mesa in eleccion.mesas.select_related(
            "sede",
            "turno",
            "eleccion_claustro_departamento__departamento",
            "eleccion_claustro_departamento__eleccion_claustro__claustro",
        ):
            escritor.writerow(
                (
                    mesa.numero,
                    mesa.eleccion_claustro_departamento.eleccion_claustro.claustro,
                    mesa.eleccion_claustro_departamento.departamento,
                    mesa.sede,
                    mesa.turno,
                    "padron" if mesa.generada_automaticamente else "manual",
                )
            )
    elif tipo == "autoridades":
        escritor.writerow(("nombre", "legajo", "mesa", "estado", "asignada_en"))
        for item in AsignacionAutoridad.objects.filter(mesa__eleccion=eleccion).select_related("registro_padron__elector", "mesa"):
            escritor.writerow(
                (
                    valor_csv(item.registro_padron.elector.nombre),
                    valor_csv(item.registro_padron.elector.legajo),
                    item.mesa.numero,
                    item.estado,
                    item.asignada_en.isoformat(),
                )
            )
    elif tipo == "participacion":
        escritor.writerow(("elector", "legajo", "mesa", "registrada_en", "metodo"))
        for item in RegistroParticipacion.objects.filter(registro_padron__eleccion=eleccion).select_related("registro_padron__elector", "mesa"):
            escritor.writerow(
                (
                    valor_csv(item.registro_padron.elector.nombre),
                    valor_csv(item.registro_padron.elector.legajo),
                    item.mesa.numero,
                    item.registrada_en.isoformat(),
                    item.metodo,
                )
            )
    elif tipo == "justificativos":
        escritor.writerow(("elector", "motivo", "estado", "presentada_en", "resuelta_en"))
        for item in JustificativoAusencia.objects.filter(registro_padron__eleccion=eleccion).select_related("registro_padron__elector", "tipo"):
            escritor.writerow(
                [
                    valor_csv(valor)
                    for valor in (
                        item.registro_padron.elector.nombre,
                        item.tipo,
                        item.estado,
                        item.presentada_en.isoformat(),
                        item.resuelta_en.isoformat() if item.resuelta_en else "",
                    )
                ]
            )
    elif tipo == "errores-importacion":
        escritor.writerow(("archivo", "fila", "campo", "mensaje"))
        for error in eleccion.importaciones_padron.prefetch_related("errores").all():
            for detalle in error.errores.all():
                escritor.writerow([valor_csv(valor) for valor in (error.nombre_archivo, detalle.fila, detalle.campo, detalle.mensaje)])
    else:
        raise Http404()

    return respuesta
