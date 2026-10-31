"""Plantillas para mensajes por estado, sin plazos implícitos de trámites."""

FECHAS_ESTANDAR = {
    "exhibicion-padron-provisorio": ("publicada", "elector", "Consultá el padrón provisorio y las opciones habilitadas para tu elección."),
    "publicacion-padron-definitivo": ("publicada", "elector", "Consultá tu asignación en el padrón definitivo."),
    "justificacion-ausencia-electoral": ("en_curso", "elector", "Figurás como ausente en el registro electoral confirmado. Consultá las opciones para presentar tu justificativo."),
    "justificacion-ausencia-autoridad": ("en_curso", "autoridad_mesa", "Consultá la información de tu justificación de ausencia como autoridad."),
    "cambio-turno-autoridades": ("publicada", "autoridad_mesa", "Consultá tu designación como autoridad y las opciones disponibles para tu turno."),
    "capacitacion-obligatoria-autoridades": ("publicada", "autoridad_mesa", "Consultá con la Junta Electoral los detalles de la capacitación obligatoria para autoridades."),
}


def cargar_calendario(Fecha, Plantilla, alias="default"):
    for codigo, (estado, rol, contenido) in FECHAS_ESTANDAR.items():
        fecha = Fecha.objects.using(alias).filter(codigo=codigo).first()
        if fecha is None:
            continue
        plantillas = []
        for sufijo, etiqueta in (("mensaje", "Aviso"), ("recordatorio", "Recordatorio")):
            plantilla, _ = Plantilla.objects.using(alias).get_or_create(
                codigo=f"estado-{codigo}-{sufijo}",
                defaults={
                    "nombre": f"{etiqueta} por estado: {fecha.nombre}",
                    "categoria": "calendario", "roles_destinatarios": [rol],
                    "asunto": f"{etiqueta}: {{nombre_fecha_administrativa}} - {{nombre_eleccion}}",
                    "contenido": "Hola {nombre_destinatario}. " + contenido + " Ingresá en {url_accion}.",
                    "permite_envio_manual": False, "activa": True,
                },
            )
            plantillas.append(plantilla)
        fecha.estado_eleccion = estado
        fecha.envia_mensaje = True
        fecha.permite_recordatorios = True
        fecha.plantilla_mensaje_id = plantillas[0].pk
        fecha.plantilla_recordatorio_id = plantillas[1].pk
        fecha.save(using=alias)
