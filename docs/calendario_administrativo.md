# Calendario administrativo por estado

En Parámetros generales > Fechas administrativas se define el estado, los
destinatarios y las plantillas sugeridas. Mensaje principal y recordatorios se
habilitan por separado. Las plantillas provienen del catálogo de mensajes.

El editor agrupa datos, destinatarios, mensaje principal y recordatorios en
tarjetas. Cada selector muestra asunto, contenido y destinatarios de la plantilla
con datos de ejemplo. «Crear plantilla» abre un diálogo con vista previa en vivo
y botones para insertar variables. El alta guarda en el catálogo y selecciona
la plantilla sin recargar el formulario; hay que guardar la fecha para conservar
esa selección. Cancelar la fecha no elimina una plantilla ya creada.

El alta integrada exige los mismos permisos de parámetros, POST y CSRF; valida
los campos y registra auditoría. Los errores mantienen abierto el diálogo y
preservan los datos. La pantalla se adapta a escritorio y navegador móvil.

Fechas y plantillas se identifican por nombre en los formularios y listados;
no se solicita código ni descripción. Los códigos internos se generan al crear
y se conservan al editar para no romper referencias; las descripciones históricas
también se mantienen. No se requiere migración de esquema.

El catálogo de Plantillas de mensajes usa el mismo editor al crear y editar:
asunto, contenido, destinatarios, vista previa e inserción de variables. Mantiene
las opciones de categoría, envío manual y activación. Comparte
`templates/parametros/_editor_plantilla.html` y `static/js/editor-plantilla.js`
con el diálogo; su página es `templates/parametros/plantilla_formulario.html`.
También se actualizan los formularios de notificaciones, los de parámetros,
sus vistas y las pruebas `tests_plantilla_calendario.py`.

En el catálogo, «Opciones de envío» explica dónde se puede usar el mensaje.
Las plantillas nuevas proponen mensajes de fechas y recordatorios, con envío
manual desmarcado. Editar una existente conserva su categoría y permisos.
Los formularios de parámetros se sirven sin caché para evitar versiones viejas
al volver a abrirlos. Se actualizaron las etiquetas y ayudas del formulario de
notificaciones, la página de plantilla, la vista de parámetros y sus pruebas.

Archivos del editor: se modifican `apps/parametros/forms.py`, `urls.py` y
`views.py`; se crean `tests_plantilla_calendario.py`, las plantillas
`parametros/fecha_formulario.html`, `_campo.html`, `_mensaje_fecha.html`,
`static/css/fechas-administrativas.css` y `static/js/fecha-administrativa.js`
(rutas relativas a `VotoUTN`). No requiere cambios de esquema ni elimina archivos.

Al avanzar la elección, el modal explica qué cambia y presenta las definiciones
del estado de destino. Marcar «Enviar mensaje», elegir fecha/hora y plantilla.
Se pueden agregar varios recordatorios, cada uno con su propia plantilla.
Las fechas no seleccionadas no generan mensajes. El estado y las programaciones
se guardan juntos; una validación fallida no modifica ninguno.

Desde Fechas administrativas se puede reprogramar o desactivar lo pendiente
del estado actual y consultar el historial. «Eliminar» desactiva conservando
el registro. Los cambios habilitados deben programarse desde mañana en
America/Argentina/Buenos_Aires. Los mensajes futuros pendientes bloquean el
avance; los vencidos no. No hay cierres automáticos de trámites.

## Operación

Aplicar `python manage.py migrate` antes de iniciar el worker. Docker Compose
incluye el servicio `calendario`, que espera las migraciones y ejecuta
`python manage.py procesar_calendario --continuo` cada minuto. Para una ejecución
manual usar `python manage.py procesar_calendario`. El comando genera notificaciones
y procesa la cola de correo pendiente. En desarrollo el correo llega a Mailpit.

Configurar `VOTO_PUBLIC_URL` con la dirección pública de la aplicación para los
enlaces de mensajes; el valor local por defecto es `https://localhost:8443`.
Para acceso desde otro equipo debe usarse el nombre/IP accesible desde ese equipo.

El procesamiento bloquea la elección y cada programación para evitar generación
duplicada. La cola de correo también bloquea cada envío. SMTP no ofrece entrega
exactamente una vez ante un corte después de aceptar el correo y antes de guardar
su resultado. Los errores de generación quedan en el calendario; los errores
de correo permanecen en la cola de notificaciones existente.

## Compatibilidad y destinatarios

Las migraciones son aditivas. Conservan fechas, comunicaciones y plantillas
anteriores; no convierten fechas históricas en mensajes pendientes. Agregan
plantillas estándar por estado que no anuncian plazos de trámites.

Los destinatarios se calculan al procesar, cruzando roles y claustros de fecha
y plantilla. Para ausentes electorales se exige la confirmación existente del
escaneo; para autoridades se usan justificativos de autoridad aprobados. Una
designación rechazada no demuestra ausencia como autoridad.

Variables generales: `nombre_destinatario`, `nombre_eleccion`,
`nombre_fecha_administrativa`, `url_accion`. Para electores se dispone de
`sede`, `mesa` cuando está asignada, `claustros`, `fecha_votacion`; para autoridades,
también `turno` y `horario_turno`. Una plantilla que requiera información
inexistente deja un error visible y se reintenta tras corregirla. La fecha del
mensaje nunca se usa como fecha de capacitación o cierre de trámite.

## Archivos de esta implementación

### Modificados

- `VotoUTN/.env.example`
- `VotoUTN/apps/auditoria/tests.py`
- `VotoUTN/apps/elecciones/models.py`
- `VotoUTN/apps/elecciones/tests_ciclo_configuracion.py`
- `VotoUTN/apps/elecciones/tests_permisos.py`
- `VotoUTN/apps/elecciones/views.py`
- `VotoUTN/apps/notificaciones/models.py`
- `VotoUTN/apps/notificaciones/services.py`
- `VotoUTN/apps/parametros/forms.py`
- `VotoUTN/apps/parametros/management/commands/cargar_parametros_estandar.py`
- `VotoUTN/apps/parametros/models.py`
- `VotoUTN/apps/parametros/tests.py`
- `VotoUTN/config/settings.py`
- `VotoUTN/templates/elecciones/configurar_eleccion.html`
- `VotoUTN/templates/parametros/lista.html`
- `docker-compose.yml`
- `docs/decisiones_funcionales.md`
- `docs/modelo_dominio.md`
- `docs/plan_implementacion.md`
- `docs/prompt_maestro.md`

### Creados

- `VotoUTN/.dockerignore`
- `VotoUTN/apps/elecciones/calendario_forms.py`
- `VotoUTN/apps/notificaciones/calendario.py`
- `VotoUTN/apps/notificaciones/calendario_models.py`
- `VotoUTN/apps/notificaciones/management/commands/procesar_calendario.py`
- `VotoUTN/apps/notificaciones/migrations/0006_mensajeprogramado.py`
- `VotoUTN/apps/notificaciones/tests_calendario.py`
- `VotoUTN/apps/parametros/calendario_estandar.py`
- `VotoUTN/apps/parametros/migrations/0005_fechaadministrativa_envia_mensaje_and_more.py`
- `VotoUTN/apps/parametros/migrations/0006_estados_fechas.py`
- `VotoUTN/apps/parametros/migrations/0007_plantillas_calendario.py`
- `VotoUTN/static/js/calendario.js`
- `VotoUTN/templates/elecciones/_calendario.html`
- `VotoUTN/templates/elecciones/calendario.html`
- `docs/calendario_administrativo.md`

No se eliminaron archivos existentes ni migraciones.

Verificación: 378 pruebas aprobadas en una base PostgreSQL nueva; `check`, `makemigrations --check`,
`migrate --plan`, `git diff --check`, sintaxis JavaScript y Docker Compose correctos.
Editor verificado en navegador de escritorio y a 390 px: vista previa, diálogo,
selección de nueva plantilla y conservación del borrador (alta simulada en navegador;
persistencia real validada en la base de pruebas).

Incidencia preexistente encontrada al reutilizar la base de pruebas: los QR
reservan dos caracteres base 36 para la elección y dejan de validar desde el
ID 1296. Se reprodujo con el servicio de QR sin cambiar su código (1295 valida;
1296 no). La verificación del editor se realiza también sobre una base nueva.
La ampliación del formato QR queda fuera de esta mejora de interfaz y requiere
mantener compatibilidad con los padrones ya impresos.
