# Registro de cambios por etapa

Este documento registra cambios aplicados al proyecto. Describe los archivos y el efecto de cada cambio; no reemplaza el historial de Git ni las migraciones de Django.

## Importación y cobertura de autoridades

- `apps/autoridades`: historial de archivos de nómina, estados y errores, CSV con coma o punto y coma y migración aditiva `0010`.
- `apps/autoridades` y su plantilla: cambio de sede sin reordenar cuando la mesa destino respeta capacidad y orden alfabético, con auditoría.
- `apps/justificativos` y `apps/autoridades`: la aprobación de una ausencia deja la vacante; la Junta puede confirmar una propuesta de traslado de otra mesa compatible sin cambiar la votación y se notifica a la persona trasladada.
- Las migraciones `autoridades.0012` y `elecciones.0031` eliminan las suplencias de mesa existentes y bloquean nuevos cupos o designaciones de suplentes, sin modificar candidaturas electorales.
- `apps/autoridades` y su plantilla: selección de la alternativa directamente desde la comparación, con detalle por opción y confirmación de la propuesta previamente calculada.

## Registro de participación limitado a la elección en curso

- `listar_elecciones` (`apps/elecciones/views.py`) filtra las elecciones del
  usuario por estado `en_curso`, tanto en la lista móvil como en el tablero de
  escritorio. Las elecciones finalizadas o publicadas ya no se listan ni se
  pueden seleccionar mediante `?eleccion=`.
- Prueba: `apps/asistencia/tests_dashboard.py`.

## Validación del comprobante en reclamos de participación

- Al presentar un reclamo «Voté, pero aparezco como ausente» con una imagen
  JPG/PNG, el sistema decodifica el QR del troquel (`zxing-cpp`) y verifica
  firma, elección e identificador del elector. Los PDF quedan para revisión
  manual y la pérdida declarada se marca como comprobante extraviado.
- Bandeja, gestión y resolución muestran el estado de la validación; la
  resolución permite volver a validar.
- La ausencia solo se anula cuando la Junta aprueba el reclamo: se elimina el
  `RegistroParticipacion`, se guarda una copia en el justificativo y se audita
  `participacion.anulada_por_reclamo`. Si la resolución pasa a rechazada se
  restaura (`participacion.restaurada_por_reclamo`).

Archivos creados:

- [services.py](../VotoUTN/apps/justificativos/services.py).
- [_validacion_comprobante.html](../VotoUTN/templates/justificativos/_validacion_comprobante.html).
- [0007_validacion_comprobante_reclamo.py](../VotoUTN/apps/justificativos/migrations/0007_validacion_comprobante_reclamo.py):
  agrega los campos de validación y respaldo, y marca los reclamos existentes
  como «Sin validar».

Archivos modificados: `requirements.txt` (`zxing-cpp==3.1.1`; requiere
reconstruir la imagen), `apps/justificativos/models.py`, `views.py`,
`tests.py`, y las plantillas `bandeja.html`, `gestion.html` y `resolver.html`.
Verificación: 374 pruebas correctas.

## Reclamo de participación como casilla

- El tipo reservado «Sí voté» se reemplaza por la casilla «Voté, pero aparezco
  como ausente» en Mis justificativos. Al marcarla se ocultan «Ausencia a
  justificar» y «Tipo» y se muestra «Perdí el comprobante de votación».
- El backend fija ausencia a votar y tipo vacío, exige comprobante o pérdida
  declarada y comentario, e ignora valores de ausencia o tipo enviados.
- La casilla solo se ofrece si hay una ausencia registrada por QR y la
  ausencia a votar no tiene justificativo; sin ausencia registrada el servidor
  ignora el reclamo y la pérdida de comprobante.
- Las descripciones de las casillas se muestran como tooltip al pasar el
  cursor y quedan asociadas con `aria-describedby` para lectores de pantalla.
- Bandeja, gestión, resolución y CSV muestran el motivo derivado.

Archivos creados:

- [mis-justificativos.js](../VotoUTN/static/js/mis-justificativos.js).
- [0004_reclamo_participacion_casilla.py](../VotoUTN/apps/justificativos/migrations/0004_reclamo_participacion_casilla.py):
  agrega la casilla, permite `tipo` vacío y convierte los reclamos existentes
  antes de quitar el tipo reservado; es reversible.
- [0005_justificativo_tipo_o_reclamo.py](../VotoUTN/apps/justificativos/migrations/0005_justificativo_tipo_o_reclamo.py):
  quita `TipoJustificativo.es_reclamo_participacion` y agrega la restricción
  de coherencia entre tipo y reclamo.
- [0006_etiqueta_reclamo_participacion.py](../VotoUTN/apps/justificativos/migrations/0006_etiqueta_reclamo_participacion.py):
  actualiza la etiqueta del campo; no cambia el esquema ni los datos.

Archivos modificados: justificativos [models.py](../VotoUTN/apps/justificativos/models.py),
[forms.py](../VotoUTN/apps/justificativos/forms.py) y
[tests.py](../VotoUTN/apps/justificativos/tests.py);
[reportes/services.py](../VotoUTN/apps/reportes/services.py);
[parametros/tests.py](../VotoUTN/apps/parametros/tests.py);
[gestion-electoral.css](../VotoUTN/static/css/gestion-electoral.css) (casillas
alineadas con su texto); plantillas
[base.html](../VotoUTN/templates/gestion/base.html),
[mis_justificativos.html](../VotoUTN/templates/justificativos/mis_justificativos.html),
[bandeja.html](../VotoUTN/templates/justificativos/bandeja.html),
[gestion.html](../VotoUTN/templates/justificativos/gestion.html) y
[resolver.html](../VotoUTN/templates/justificativos/resolver.html); documentación.

Verificación en Docker/PostgreSQL: migraciones aplicadas, revertidas y
reaplicadas; `check` y `makemigrations --check --dry-run` sin pendientes;
suite completa de 371 pruebas aprobada. En navegador se verificó la casilla
para un elector con ausencia registrada: al marcarla se ocultan ausencia y
tipo y aparece la pérdida de comprobante; al desmarcarla se revierte.

## Plazos de publicación y reclamo «Sí voté»

- Publicación con diálogo y dos fechas obligatorias. Las fechas no limitan el
  avance de estados; se conservan los controles de configuración y pendientes.
  El modelo persiste ambos plazos junto con el estado y se auditan sus valores.
- El plazo de autoridades es inclusivo y se valida en backend. No afecta las
  presentaciones como elector.
- Tipo reservado «Sí voté», con comprobante o declaración de pérdida y
  comentario. Se presenta para revisión manual, sin borrar ni corregir
  automáticamente la ausencia registrada.
- Filtro de cambios de sede: acción GET explícita y cantidad/estado visibles.
  El filtro se aplica al cambiar el desplegable (sin botones «Filtrar» ni
  «Limpiar filtro»; «Todos» quita el filtro). La URL reportada se verificó: la
  elección 12 tenía 70 aprobadas y ninguna rechazada; no se reprodujo un fallo
  del filtro backend. Se añadieron pruebas con estados mezclados y en modo
  lectura.

Archivos creados:

- [publicar-eleccion.js](../VotoUTN/static/js/publicar-eleccion.js).
- [0003_reclamo_participacion.py](../VotoUTN/apps/justificativos/migrations/0003_reclamo_participacion.py):
  migración aditiva que incorpora los campos y el tipo sin borrar datos.

Archivos modificados:

- Elecciones: [forms.py](../VotoUTN/apps/elecciones/forms.py),
  [models.py](../VotoUTN/apps/elecciones/models.py),
  [views.py](../VotoUTN/apps/elecciones/views.py) y
  [tests_ciclo_configuracion.py](../VotoUTN/apps/elecciones/tests_ciclo_configuracion.py).
- Justificativos: [forms.py](../VotoUTN/apps/justificativos/forms.py),
  [models.py](../VotoUTN/apps/justificativos/models.py) y
  [tests.py](../VotoUTN/apps/justificativos/tests.py).
- Filtro: [views.py](../VotoUTN/apps/padron/views.py).
- Pruebas existentes adaptadas al nuevo requisito:
  [asistencia/tests.py](../VotoUTN/apps/asistencia/tests.py),
  [auditoria/tests.py](../VotoUTN/apps/auditoria/tests.py) y
  [parametros/tests.py](../VotoUTN/apps/parametros/tests.py).
- Plantillas: [configurar_eleccion.html](../VotoUTN/templates/elecciones/configurar_eleccion.html),
  [mis_justificativos.html](../VotoUTN/templates/justificativos/mis_justificativos.html),
  [resolver.html](../VotoUTN/templates/justificativos/resolver.html) y
  [gestion_solicitudes_cambio_sede.html](../VotoUTN/templates/padron/gestion_solicitudes_cambio_sede.html).
- Documentación: [decisiones_funcionales.md](decisiones_funcionales.md),
  [modelo_dominio.md](modelo_dominio.md) y este registro.

Sin archivos eliminados. Se conserva sin cambios el comando demo preexistente.

Verificación en Docker/PostgreSQL: migración aplicada, estáticos publicados,
`check`, `makemigrations --check --dry-run` y `migrate --plan` sin pendientes.
Suite completa de 366 pruebas y regresión final de 85 pruebas aprobadas.
Diálogo, cancelación/foco, obligatoriedad de fechas y listado vacío filtrado
verificados en navegador con HTML renderizado, sin modificar la elección real.

## Nitidez del padrón imprimible

- Troqueles con fondo blanco, sin sombreado gris.
- QR de electores ampliados de 14 a 18 mm, con margen blanco de cuatro módulos.
- Los QR del PDF se dibujan como vectores negros sobre blanco, incluidos los de
  las carátulas: no dependen de la resolución de un PNG ni se pixelan al ampliar.
- Ajuste del espacio interno del troquel para conservar las firmas y los
  15 electores por hoja sin invadir las columnas contiguas.
- Línea de firma de autoridad de mesa acortada 2 mm a la izquierda y 2 mm
  a la derecha mediante márgenes simétricos explícitos, sin modificar la firma
  del votante ni el tamaño del QR.
- Se conservan el contenido firmado, la mesa, los identificadores y las marcas
  de emisión. No se modifican modelos ni migraciones.
- Pruebas de fondo blanco, tamaño, margen, correspondencia de la matriz QR,
  contenido firmado y ausencia de imágenes rasterizadas en el QR.

## Ciclo electoral, configuración y resolución seleccionada

- Estados de elección con códigos nuevos (`en_preparacion`, `publicada`,
  `en_curso`, `finalizada`). La migración `elecciones/0029` renombra los datos
  existentes (`borrador`, `preparada`, `abierta`, `cerrada`) y recrea la
  restricción de una única elección no finalizada, con reversión.
- La configuración queda en modo lectura también en Publicada: solo En
  preparación permite modificarla (incluye calcular mesas y vaciar padrones).
- Línea de tiempo: estados pasados en un verde, actual en un verde destacado y
  posteriores en gris. El popup de cambio de estado describe qué ocurre en el
  siguiente estado. Las etiquetas de las cards se muestran debajo del título.
- Padrón: historial de importaciones desplegable dentro de "Cargar padrón",
  botón azul "Configurar asignación de sedes" sobre "Vaciar padrón" y acceso a
  "Ver mesas" filtrado por claustro desde el encabezado. Se quitan las
  exportaciones CSV/PDF del padrón y "Ver mesas" de Padrones.
- Asignación de sedes automática al agregar, eliminar o reordenar reglas y al
  confirmar importaciones (sin botón "Calcular asignaciones"). Se muestra un
  resumen por sede y regla; el detalle por elector es desplegable, de a 10.
- "Ver mesas" filtra por claustro, departamento y sede.
- Reportes → Padrón y mesas: "Exportar padrón" y "Exportar asignación de sedes".
- Cambios de sede: filtro por estado, sede preseleccionada si hay una sola
  opción, botones masivos deshabilitados sin pendientes y popups que indican en
  qué sedes se agregan y se quitan mesas. Al aprobar un cambio, una mesa
  automática de origen que queda vacía (sin autoridades, participaciones ni
  roles) se elimina; las mesas manuales se conservan.
- Refinamiento visual: indicadores de configuración completa en verde y
  pendientes en amarillo. El ciclo se presenta mediante tarjetas con colores
  e iconos por etapa, conectadas de izquierda a derecha en escritorio y de
  arriba hacia abajo en móvil, con el estado actual destacado y ayudas
  accesibles por foco o cursor. No se modifican transiciones ni permisos.
- El botón de avance de estado se ubica en el encabezado del ciclo. Cuando una
  regla impide la transición, el motivo se informa con un popup propio de la
  aplicación (con aviso en página como alternativa sin JavaScript).
- La pestaña "Notificaciones" se reemplaza por una campanita a la izquierda del
  rol del usuario, en todos los roles, con indicador rojo de no leídas. Sigue
  visible en móvil aunque se oculte el bloque de usuario.
- La pestaña "Configurar elección" se muestra grisada y deshabilitada cuando no
  hay una elección actual (En preparación, Publicada o En curso).
- Configuración actual directa desde el menú, línea de tiempo con estado
  destacado y ayudas breves, e indicadores de configuración pendiente.
- Inicio de junta global con elección actual, justificativos pendientes,
  cambios de sede pendientes y participación confirmada. Sin elección actual
  ofrece crearla; la creación continúa por Sedes y departamentos.
- Alta/baja de claustros en preparación, con herencia de sedes y rechazo
  transaccional de bajas que afectarían datos vinculados.
- Permisos de configuración: consulta en curso y bloqueo de POST, con las
  excepciones acordadas de fechas administrativas, transición de estado y
  padrón imprimible. Se conserva el acceso histórico previo de finalizadas.
- Emisión imprimible solo en curso; emisión y resolución de cambios coordinan
  el bloqueo de la elección para preservar los QR. Reimpresiones conservan
  identificadores, marcas de emisión y número de mesa.
- Selección de solicitudes pendientes, estimación por sede sin duplicar las
  reglas en JavaScript y aprobación exclusiva de las seleccionadas. Después
  de imprimir quedan bloqueadas las resoluciones individuales y masivas.
- Código de mesa con departamento en avisos y tarjetas del elector y autoridad.
- Diálogos propios y throbber compartido para operaciones demoradas. Se retiró
  la leyenda de estados de la presentación de justificativos sin ampliar permisos.
- Nuevas pruebas de invariantes y regresiones en elecciones y reportes;
  expectativas de navegación y redirecciones ajustadas en suites relacionadas.
  No se modificaron modelos ni se requieren nuevas migraciones.
- Por indicación expresa, no se implementó pedir fechas en la transición de
  estado ni reasignarlas a estados.
- Verificación: 342 pruebas correctas en PostgreSQL de pruebas aislado; check,
  detección de migraciones y plan de migraciones sin pendientes. También se
  verificaron en Chromium selección, confirmaciones, controles en lectura,
  diálogo de límite y disposición móvil de la línea de tiempo.
- Observación ajena a esta entrega: al reutilizar repetidamente la base de
  pruebas con `--keepdb`, los IDs superaron 1295. El formato QR previo reserva
  dos caracteres base36 para elección y mesa y no admite correctamente IDs
  mayores al parsearlos. No se cambió ese contrato ni su comportamiento;
  la validación final se ejecutó en una base de pruebas nueva y aislada.

## Etapa 0 - Auditoria y estabilizacion

Fecha de cierre: 2026-08-02

### Dependencias y entorno

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/requirements.txt` | Se convirtio de UTF-16 a UTF-8 sin BOM. Se reemplazo Django 6.0.7 por Django 5.2.16 y Django REST Framework 3.15.2 por 3.17.1. |
| `VotoUTN/.env.example` | Se agrego `CLAVE_FIRMA_QR` como variable separada de `DJANGO_SECRET_KEY`. |
| `VotoUTN/config/settings.py` | Se incorporo `CLAVE_FIRMA_QR`; conserva como respaldo `SECRET_KEY` para mantener la validacion de QR existentes hasta configurar la nueva variable. |

### Seguridad QR y archivos sensibles

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/asistencia/services.py` | La validacion HMAC de QR usa `settings.CLAVE_FIRMA_QR` en vez de `settings.SECRET_KEY`. |
| `VotoUTN/apps/elecciones/management/commands/seed_voters.py` | La generacion HMAC de QR usa `settings.CLAVE_FIRMA_QR`, en concordancia con el validador. |
| `VotoUTN/.gitignore` | Se agregaron las reglas `*.pem` y `generated_qrs/`. |
| `VotoUTN/192.168.1.45+2.pem` | Se retiro del indice de Git. El archivo local no fue borrado. |
| `VotoUTN/192.168.1.45+2-key.pem` | Se retiro del indice de Git. El archivo local no fue borrado. |
| `VotoUTN/generated_qrs/` | Sus imagenes generadas se retiraron del indice de Git y se conservaron localmente. |

### Pruebas y base de datos

| Ruta o recurso | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/asistencia/tests.py` | Se creo la cobertura inicial de QR: firma valida, firma modificada, clave distinta y compatibilidad entre generador y validador. |
| Base PostgreSQL configurada | Se aplicaron las migraciones iniciales de `admin`, `auth`, `contenttypes`, `elecciones`, `asistencia` y `sessions`. |

## Etapa 1 - Unificacion de nomenclatura

Fecha de cierre: 2026-08-03

### Modelo y migraciones

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | `Votante` paso a llamarse `Elector`. En `Eleccion`, `name`, `starts_at`, `ends_at` e `is_active` pasaron a `nombre`, `fecha_inicio`, `fecha_fin` y `habilitada`. En `Elector`, `name` paso a `nombre` y la relacion de mesa paso a llamarse `electores`. |
| `VotoUTN/apps/asistencia/models.py` | `voter_code`, `scanned_by` y `scanned_at` pasaron a `codigo_elector`, `registrada_por` y `registrada_en`. La relacion de eleccion paso de `attendances` a `asistencias`; tambien se tradujeron el indice y la restriccion de unicidad. |
| `VotoUTN/apps/elecciones/migrations/0003_nomenclatura_en_espanol.py` | Migracion explicita y segura para los renombres de `Eleccion`, `Votante` a `Elector`, el campo `nombre` y la relacion de mesa. |
| `VotoUTN/apps/asistencia/migrations/0003_nomenclatura_en_espanol.py` | Migracion explicita y segura para los tres campos de asistencia, la relacion de eleccion, el indice y la restriccion de unicidad. |
| Base PostgreSQL configurada | Se aplicaron ambas migraciones `0003_nomenclatura_en_espanol`; no quedan migraciones pendientes. |

### Servicios, API y cliente QR

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/asistencia/services.py` | Se actualizaron consultas, variables, parametros y `ResultadoAsistencia` para usar `Elector`, `codigo_elector`, `usuario`, `creados`, `ya_registrados` e `invalidos`. |
| `VotoUTN/apps/asistencia/serializers.py` | La carga por lote recibe `codigos_qr` en lugar de `voter_codes`. |
| `VotoUTN/apps/asistencia/api.py` | La API recibe `codigos_qr` y responde `creados`, `ya_registrados`, `invalidos` y `recibidos`. Tambien consulta elecciones `habilitada=True`. |
| `VotoUTN/apps/asistencia/api_urls.py` | El nombre de ruta paso a `api-asistencia-lote`; la URL HTTP se mantuvo. |
| `VotoUTN/static/js/api.js` | La funcion exportada paso de `registerAttendance` a `registrarAsistencia` y envia `codigos_qr`. |
| `VotoUTN/static/js/asistencia.js` | Se actualizo para consumir `registrarAsistencia`. |
| `VotoUTN/static/js/scanner-app.js` | La carga manual interpreta las claves de respuesta en espanol: `invalidos`, `creados` y `ya_registrados`. |
| `VotoUTN/templates/asistencia/scanner.html` | Se actualizaron los nombres de campos de eleccion y las referencias a rutas canonicas. |

### Vistas, administracion y comandos

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/views.py` | El listado filtra con `habilitada=True`. |
| `VotoUTN/apps/asistencia/views.py` | El escaner busca elecciones con `habilitada=True`. |
| `VotoUTN/apps/elecciones/admin.py` | Se registran y muestran los nombres `Elector`, `nombre`, `fecha_inicio`, `fecha_fin` y `habilitada`. |
| `VotoUTN/apps/asistencia/admin.py` | Se muestran los campos `codigo_elector`, `registrada_por` y `registrada_en`. |
| `VotoUTN/apps/elecciones/urls.py` | El nombre de ruta principal paso a `lista-elecciones`. |
| `VotoUTN/templates/base.html` | La navegacion principal usa `lista-elecciones`. |
| `VotoUTN/config/settings.py` | `LOGIN_REDIRECT_URL` usa `lista-elecciones`. |
| `VotoUTN/apps/elecciones/management/commands/seed_voters.py` | Se actualizo para crear `Elector` y asignar `nombre`. Se conserva como comando de compatibilidad. |
| `VotoUTN/apps/elecciones/management/commands/cargar_electores_demo.py` | Se creo el comando canonico en espanol como alias funcional del comando de datos demo existente. |

### Pruebas y documentacion

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas de los nombres de modelo en espanol y del campo `codigos_qr` del serializador. |
| `docs/plan_implementacion.md` | Se marcaron las etapas 0 y 1 como completadas y la etapa actual como 2. |

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 6 pruebas correctas.
- No se pudo ejecutar una comprobacion estatica con Node.js porque Node no esta instalado en el entorno.

## Ajuste funcional - Estados de eleccion y cambio de sede

Fecha de cierre: 2026-10-19

### Estados y reglas de ciclo de vida

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | Se mantuvieron los valores tecnicos de estado para compatibilidad (`borrador`, `preparada`, `abierta`, `cerrada`) y se actualizaron sus etiquetas visibles a `En preparación`, `Publicada`, `En curso` y `Finalizada`. Se agregó `fecha_cierre_solicitudes_cambio_sede`. |
| `VotoUTN/apps/elecciones/views.py` | Se incorporaron validaciones para finalizar elección (sin justificativos pendientes y sin mesas pendientes de escaneo), y envío de notificaciones al publicar e iniciar elección. |
| `VotoUTN/apps/elecciones/migrations/0026_eleccion_fecha_cierre_solicitudes_cambio_sede.py` | Migración aditiva para la nueva fecha de cierre de solicitudes de cambio de sede. |
| `VotoUTN/apps/elecciones/migrations/0027_alter_eleccion_estado.py` | Migración de actualización de `choices` del campo `estado` para reflejar los nuevos nombres funcionales. |

### Flujo de solicitud de cambio de sede

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/padron/models.py` | Se agregó `SolicitudCambioSede` con estados `pendiente/aprobada/rechazada`, trazabilidad de resolución y restricción de única solicitud pendiente por registro de padrón. |
| `VotoUTN/apps/padron/services.py` | Se agregaron servicios para resolver solicitudes individuales y masivas (aprobar/rechazar, con o sin creación de mesas, y con límite de mesas por sede). |
| `VotoUTN/apps/padron/views.py` | Se incorporaron vistas para `mis-solicitudes-cambio-sede` (elector) y `gestionar-solicitudes-cambio-sede` (junta), incluyendo validaciones de período y notificación al resolver. |
| `VotoUTN/apps/padron/urls.py` | Se registraron rutas nuevas para solicitud y gestión de cambios de sede. |
| `VotoUTN/apps/padron/migrations/0011_solicitudcambiosede.py` | Migración de creación de `SolicitudCambioSede` y su constraint de unicidad parcial. |
| `VotoUTN/templates/padron/mis_solicitudes_cambio_sede.html` | Nueva pantalla para que el elector solicite cambio de sede y consulte historial de solicitudes. |
| `VotoUTN/templates/padron/gestion_solicitudes_cambio_sede.html` | Nueva pantalla para gestión masiva e individual de solicitudes desde administración de junta. |

### Navegación y reportes

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/templates/gestion/_nav.html` | Se agregó acceso a gestión de solicitudes de cambio de sede para administración y acceso para electores a sus solicitudes. |
| `VotoUTN/apps/reportes/services.py` | Se agregó exportación CSV de infractores (ausentes sin justificativo aprobado). |
| `VotoUTN/apps/reportes/views.py` y `VotoUTN/templates/reportes/gestion.html` | Se habilitó la exportación de infractores solo para elecciones finalizadas y sin justificativos pendientes. |

### Verificaciones

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py test apps.elecciones apps.padron.tests apps.justificativos.tests`: correcto (114 pruebas).

## Límite total de mesas en la resolución de cambios de sede

La pantalla de administración muestra las mesas actuales por sede y una estimación de mesas adicionales. Se agregó una resolución masiva con un máximo total ingresado por el administrador; las solicitudes que superen el límite quedan pendientes. La asignación ahora busca una mesa con capacidad disponible antes de crear una nueva, respetando el máximo de electores por mesa del claustro.

La acción «Aceptar con límite de mesas nuevas» ahora abre un diálogo con la cantidad estimada de mesas que se crearían si se aceptaran todas las solicitudes y solicita el máximo total antes de continuar. El resumen por sede queda junto a las acciones en escritorio y se apila en pantallas angostas.
Además, cada elector ahora puede registrar una sola solicitud de cambio de sede por elección: si ya existe una solicitud para esa elección, se bloquea una nueva carga y se informa en pantalla.

Archivos modificados:

- `VotoUTN/apps/padron/services.py`
- `VotoUTN/apps/padron/views.py`
- `VotoUTN/apps/padron/tests.py`
- `VotoUTN/templates/padron/gestion_solicitudes_cambio_sede.html`
- `VotoUTN/static/js/solicitudes-cambio-sede.js`
- `VotoUTN/static/css/gestion-electoral.css`
- `VotoUTN/templates/gestion/base.html`
- `docs/decisiones_funcionales.md`
- `docs/registro_de_cambios.md`

## Etapa 2 - Modelo electoral base

Fecha de cierre: 2026-08-03

### Relevamiento previo de datos

| Recurso | Resultado |
| --- | --- |
| Base PostgreSQL configurada | `Eleccion`, `Mesa`, `Elector` y `Asistencia` tenian 0 registros. No se ejecuto una migracion de datos porque no habia datos que trasladar. |
| `Elector.mesa` | Se conserva como campo transitorio para no romper el servicio QR actual. La asignacion definitiva se incorpora con `AsignacionMesa`. |

### Modelo y administracion

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | Se crearon `Sede`, `Claustro`, `Turno` y `Departamento`, cada uno con nombre, codigo o rango horario y estado activo. `Turno` valida que su hora de fin sea posterior a la de inicio. |
| `VotoUTN/apps/elecciones/models.py` | Se crearon `EleccionSede`, `EleccionClaustro`, `EleccionClaustroSede`, `EleccionClaustroDepartamento` y `EleccionClaustroDepartamentoSede` para representar los alcances habilitados por eleccion. |
| `VotoUTN/apps/elecciones/models.py` | `Mesa` incorpora referencias opcionales a configuracion de claustro/departamento, sede y turno. Valida que la configuracion y la sede correspondan a la misma eleccion. El numero sigue siendo unico dentro de la eleccion. |
| `VotoUTN/apps/elecciones/models.py` | Se crearon `RegistroPadron` y `AsignacionMesa`. El primero vincula elector, eleccion y configuracion de claustro/departamento; el segundo asigna una unica mesa por registro de padron. Ambos validan que las relaciones pertenezcan a la misma eleccion. |
| `VotoUTN/apps/elecciones/admin.py` | Se registraron las nuevas entidades para su administracion desde Django Admin y se ampliaron las columnas de mesa. |

### Migracion y pruebas

| Ruta o recurso | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/migrations/0004_modelo_electoral_base.py` | Se creo y aplico la migracion aditiva del modelo base. Crea las tablas nuevas y agrega campos opcionales a `Mesa`; no elimina ni modifica datos existentes. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas para horario de turno invalido y para impedir que una mesa use una configuracion de otra eleccion. |
| Base PostgreSQL configurada | Se aplico `elecciones.0004_modelo_electoral_base`. |

### Verificaciones al cierre

- `python manage.py migrate`: aplico `elecciones.0004_modelo_electoral_base` correctamente.
- `python manage.py test`: 8 pruebas correctas, incluida una base temporal de pruebas PostgreSQL.

## Etapa 3 - Usuarios, roles y permisos

Fecha de cierre: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/usuarios/models.py` | Se crearon `PerfilUsuario`, que vincula una identidad Django con un elector opcional, y `AsignacionRol`, con roles de sistema, junta, administrativo, autoridad de mesa y elector, con alcance por eleccion, sede y mesa. |
| `VotoUTN/apps/usuarios/permisos.py` | Se implementaron `puede_registrar_participacion` y `elecciones_con_participacion`. Solo administrador de junta, administrativo de junta o administrador del sistema pueden registrar participacion; autoridad de mesa queda excluida. |
| `VotoUTN/apps/usuarios/admin.py` | Se registraron perfiles y asignaciones de rol para administracion local. |
| `VotoUTN/apps/usuarios/apps.py` | Se definio la configuracion de la nueva aplicacion `usuarios`. |
| `VotoUTN/config/settings.py` | Se agrego `apps.usuarios` a las aplicaciones instaladas. |
| `VotoUTN/apps/elecciones/views.py` | El listado solo muestra elecciones donde el usuario tiene una asignacion apta para participacion. |
| `VotoUTN/apps/asistencia/views.py` | El escaner responde 403 cuando el usuario no puede registrar participacion en la eleccion solicitada. |
| `VotoUTN/apps/asistencia/api.py` | La API rechaza con 403 los intentos sin permiso de participacion. |
| `VotoUTN/apps/asistencia/services.py` | El registro QR y manual verifica el alcance por mesa o sede antes de persistir la asistencia. |
| `VotoUTN/templates/403.html` | Se creo la pantalla para accesos denegados en vistas HTML. |
| `VotoUTN/apps/usuarios/migrations/0001_perfiles_y_roles.py` | Se creo y aplico la migracion que agrega las tablas de perfiles y roles. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas para permitir a un administrativo asignado y bloquear a una autoridad de mesa. |

### Verificaciones al cierre

- `python manage.py migrate`: aplico `usuarios.0001_perfiles_y_roles` correctamente.
- `python manage.py test`: 10 pruebas correctas, incluida una base temporal de pruebas PostgreSQL.

## Etapa 4 - Integracion definitiva del QR

Fecha de cierre: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | `RegistroPadron` incorpora `identificador_qr`, un UUID unico y opaco sin DNI ni legajo. |
| `VotoUTN/apps/asistencia/models.py` | Se creo `RegistroParticipacion`, vinculado a padrón, mesa, usuario, fecha y metodo QR o manual. |
| `VotoUTN/apps/asistencia/services.py` | Se reemplazo el formato QR por `v1`, con eleccion, mesa, UUID de padron y HMAC SHA-256 truncado a 128 bits. El servidor valida firma, eleccion, padrón, mesa y permiso antes de registrar. |
| `VotoUTN/apps/asistencia/serializers.py` y `api.py` | La carga manual ahora busca por DNI y utiliza el servicio definitivo de participacion. |
| `VotoUTN/static/js/scanner-app.js` y `asistencia.js` | El cliente reconoce QR `v1`, conserva la mesa detectada y solicita DNI para la contingencia manual. |
| `VotoUTN/apps/elecciones/management/commands/seed_voters.py` | El comando demo requiere una configuracion de departamento y genera padron, asignacion de mesa y QR opacos. |
| `VotoUTN/apps/elecciones/migrations/0005_identificador_qr_padron.py` | Migracion segura: agrega UUID nullable, asigna uno distinto a cada padrón existente y luego impone unicidad. |
| `VotoUTN/apps/asistencia/migrations/0004_registro_participacion.py` | Crea la tabla de participacion definitiva y su restriccion de unicidad. |

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 10 pruebas correctas.

## Etapa 5 - Gestion de elecciones

Fecha de cierre: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | `Eleccion` incorpora los estados `borrador`, `preparada`, `abierta` y `cerrada`. Se creo `EleccionTurno` para persistir la seleccion de turnos por eleccion. |
| `VotoUTN/apps/elecciones/models.py` | `Mesa` ahora valida que su turno este habilitado para la eleccion, ademas de las validaciones previas de configuracion y sede. |
| `VotoUTN/apps/elecciones/forms.py` | Se creo el formulario de alta: en una transaccion crea la eleccion y sus asociaciones de sedes, claustros, departamentos, sedes por configuracion y turnos seleccionados. Tambien se creo el formulario que genera mesas consecutivas solo con configuraciones, sedes y turnos validos. |
| `VotoUTN/apps/elecciones/views.py` | Se agregaron las vistas autenticadas para listar la gestion, crear una eleccion y generar o consultar sus mesas. |
| `VotoUTN/apps/elecciones/urls.py` | Se agregaron las rutas `/gestion/elecciones/`, `/gestion/elecciones/nueva/` y `/gestion/elecciones/<id>/mesas/`. |
| `VotoUTN/templates/elecciones/gestion_lista.html` | Se creo la pantalla de administracion para consultar elecciones y abrir el alta. |
| `VotoUTN/templates/elecciones/formulario_eleccion.html` | Se creo la pantalla de alta con seleccion multiple de sedes, claustros, departamentos y turnos. |
| `VotoUTN/templates/elecciones/gestion_mesas.html` | Se creo la pantalla para generar mesas y consultar las ya creadas. |
| `VotoUTN/apps/usuarios/permisos.py` | Se agrego `puede_administrar_elecciones`: habilita a superusuario o administrador del sistema para la gestion global y a administrador de junta dentro de su eleccion asignada. |
| `VotoUTN/apps/elecciones/admin.py` | El admin local muestra el estado de la eleccion y permite administrar asociaciones de turnos. |
| `VotoUTN/apps/elecciones/migrations/0006_gestion_elecciones.py` | Se creo y aplico una migracion aditiva que agrega el estado con valor por defecto `borrador` y crea la tabla de asociacion eleccion-turno. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas de configuracion inicial desde formulario, generacion consecutiva de mesas y rechazo de turnos ajenos a una eleccion. |

### Verificaciones al cierre

- `python manage.py migrate`: aplico `elecciones.0006_gestion_elecciones` correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 12 pruebas correctas.

### Complemento de etapa 5 - ABM de parametros

Fecha de cierre: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/forms.py` | Se agregaron formularios de alta y edicion para `Sede`, `Claustro`, `Departamento` y `Turno`. El formulario de turno conserva la validacion de horario de inicio y fin. |
| `VotoUTN/apps/elecciones/views.py` | Se implementaron las vistas de panel, listado con busqueda, alta, edicion y cambio de estado de cada parametro. Las bajas se resuelven como desactivacion, sin eliminar datos referenciados. |
| `VotoUTN/apps/elecciones/urls.py` | Se agregaron las rutas bajo `/gestion/parametros/` para administrar los cuatro tipos de parametro. |
| `VotoUTN/apps/usuarios/permisos.py` | Se agrego `puede_administrar_parametros`; permite el acceso a superusuarios, administradores del sistema y administradores de junta. |
| `VotoUTN/templates/elecciones/parametros.html` | Se creo el panel de parametros, tomando como referencia la seccion de configuracion del maquetado administrativo. |
| `VotoUTN/templates/elecciones/parametro_lista.html` | Se creo la grilla responsive con busqueda, edicion y accion de activar o desactivar. |
| `VotoUTN/templates/elecciones/parametro_formulario.html` | Se creo el formulario reutilizable de alta y edicion con controles de estado y errores de validacion. |
| `VotoUTN/templates/elecciones/gestion_lista.html` | Se agrego el acceso directo a Parametros desde la gestion de elecciones. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas para alta y baja logica de sede por administrador de junta, y para el rechazo de usuarios sin rol de administracion. |

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 14 pruebas correctas.

### Complemento de etapa 5 - Integracion visual de maquetado administrativo

Fecha de cierre: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/templates/elecciones/base_gestion.html` | Se creo una base exclusiva para Junta Electoral, con cabecera institucional UTN, datos de sesion, navegacion horizontal y cierre de sesion. No se modifica la base usada por escaneo QR u otros roles. |
| `VotoUTN/static/css/gestion-electoral.css` | Se incorporaron los estilos de gestion basados en la maqueta `Maquetado/administrador-de-junta`: paleta azul UTN y rojo institucional, superficies blancas, bordes, tablas, formularios, paneles de trabajo y adaptacion movil. |
| `VotoUTN/templates/elecciones/gestion_lista.html` | Se transformo en el panel PRE-VOTACION, con accesos y listado de elecciones alineados a la maqueta principal de administrador de junta. |
| `VotoUTN/templates/elecciones/parametros.html`, `parametro_lista.html` y `parametro_formulario.html` | Se redisenaron el panel y ABM de parametros usando la estructura de configuracion, formularios y tablas del maquetado administrativo. |
| `VotoUTN/templates/elecciones/formulario_eleccion.html` y `gestion_mesas.html` | Se adaptaron los flujos de creacion de eleccion y generacion de mesas a la misma base visual y de navegacion. |

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 14 pruebas correctas.
- Renderizado autenticado comprobado para `/gestion/elecciones/` y `/gestion/parametros/`: respuesta HTTP 200.

### Complemento de etapa 5 - Ciclo de vida y alcances

Fecha de cierre: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | Se agregaron validaciones de configuracion y transiciones ordenadas de eleccion: borrador a preparada, preparada a abierta y abierta a cerrada. Abrir exige al menos una mesa; cerrar deshabilita la eleccion para el registro de participacion. |
| `VotoUTN/apps/elecciones/forms.py` | El alta de elecciones comienza siempre en borrador e inhabilitada. Sedes, claustros, departamentos y turnos se renderizan con casillas de seleccion multiple. Se agregaron formularios para editar datos generales y para ajustar sedes heredadas. |
| `VotoUTN/apps/elecciones/forms.py` | Los ajustes de sedes por claustro o departamento se ejecutan de forma transaccional. Se bloquea la quita de una sede si ya existen mesas que dependen de esa combinacion. |
| `VotoUTN/apps/elecciones/views.py` y `urls.py` | Se agregaron edicion de eleccion, acciones de preparar, abrir y cerrar, consulta de alcances y edicion de sedes por claustro o departamento. |
| `VotoUTN/templates/elecciones/gestion_lista.html` | Se incorporaron acciones visibles de ciclo de vida, edicion, alcances y mesas para cada eleccion. |
| `VotoUTN/templates/elecciones/alcances.html`, `editar_alcance.html` y `editar_eleccion.html` | Se crearon las pantallas administrativas para ajustar herencias de sedes y editar datos generales. |
| `VotoUTN/templates/elecciones/formulario_eleccion.html` y `static/css/gestion-electoral.css` | Las selecciones de parametros ahora se presentan como grupos de checkboxes visibles y estilizados, en lugar de listas desplegables. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas para estado inicial, apertura solo con mesas, cierre que deshabilita y bloqueo de quita de sedes con mesas. |

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 16 pruebas correctas.

### Complemento de etapa 5 - Historial y calendario administrativo

Fecha de cierre: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | `Eleccion` incorpora fechas para apertura y cierre de padron provisorio, cierre de candidaturas, publicacion de padron definitivo y limites de justificativos de autoridades y electores. Valida el orden del calendario de padrones. |
| `VotoUTN/apps/elecciones/migrations/0007_fechas_administrativas.py` | Se creo y aplico una migracion aditiva con campos anulables, segura para elecciones ya existentes. |
| `VotoUTN/apps/elecciones/forms.py` | La creacion y edicion incluyen el calendario administrativo. Se elimino la seleccion de departamentos del alta de eleccion: se asociaran durante la importacion de padrones por claustro en la etapa 6. |
| `VotoUTN/apps/elecciones/views.py` y `urls.py` | Se separaron elecciones en curso de las cerradas y se agrego la ruta `/gestion/elecciones/historial/`. Tras crear una eleccion se vuelve al panel, ya que la configuracion de departamentos depende del padron posterior. |
| `VotoUTN/templates/elecciones/historial_elecciones.html` | Se creo la consulta de elecciones pasadas con fechas y cantidad de mesas. |
| `VotoUTN/templates/elecciones/formulario_eleccion.html` y `editar_eleccion.html` | Se agruparon visualmente datos generales, fechas administrativas y parametros seleccionables. El alta ya no presenta departamentos. |
| `VotoUTN/templates/elecciones/base_gestion.html` | Se agrego el acceso de navegacion a Elecciones pasadas. |
| `VotoUTN/apps/asistencia/tests.py` | Se actualizaron las pruebas de configuracion inicial sin departamentos y se agrego validacion del orden del calendario administrativo. |

### Verificaciones al cierre

- `python manage.py migrate`: aplico `elecciones.0007_fechas_administrativas` correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 17 pruebas correctas.

### Complemento de etapa 5 - Fechas administrativas configurables

Fecha de implementacion: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | Se crearon `FechaAdministrativa`, con nombre, roles destinatarios, claustros, asunto, mensaje y estado, y `FechaAdministrativaEleccion`, que programa una definicion para una eleccion concreta. La fecha programada se valida dentro del periodo electoral. |
| `VotoUTN/apps/elecciones/migrations/0008_fechaadministrativa_fechaadministrativaeleccion.py` | Se genero y aplico la migracion aditiva para las nuevas tablas, sin alterar registros existentes. |
| `VotoUTN/apps/elecciones/forms.py` | Se creo el ABM de definiciones de fechas administrativas. El formulario de eleccion carga dinamicamente las definiciones activas al final, con una casilla para incluir cada hito y un campo de fecha obligatorio cuando se selecciona. |
| `VotoUTN/apps/elecciones/forms.py` | Las fechas administrativas fijas incorporadas previamente se conservan como compatibilidad de modelo, pero dejan de aparecer en la interfaz nueva. La seleccion de departamentos sigue fuera del alta y queda para la importacion de padron por claustro. |
| `VotoUTN/apps/elecciones/views.py` | El panel de parametros incorpora Fechas administrativas como un quinto ABM y el formulario de alta expone sus definiciones dinamicas. |
| `VotoUTN/apps/elecciones/admin.py` | Se registraron las definiciones y sus programaciones por eleccion en Django Admin. |
| `VotoUTN/templates/elecciones/parametro_lista.html` | El listado de fechas administrativas muestra los roles destinatarios configurados. |
| `VotoUTN/templates/elecciones/formulario_eleccion.html` | Las fechas administrativas son el ultimo bloque del alta: permite seleccionar los hitos aplicables y asignar una fecha individual a cada uno. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas para crear una programacion desde el alta y rechazar fechas fuera del periodo electoral. |

### Verificaciones realizadas

- `python manage.py migrate`: aplico `elecciones.0008_fechaadministrativa_fechaadministrativaeleccion` correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 18 pruebas correctas.

## Etapa 9 - Notificaciones

Fecha de implementacion: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | Se agregaron `PlantillaNotificacion` y `EnvioNotificacion`. Las plantillas conservan asunto, contenido, roles destinatarios y claustros aplicables; cada envio registra destinatario, estado, fecha de envio, lectura y error. |
| `VotoUTN/apps/elecciones/migrations/0016_plantillanotificacion_envionotificacion.py` | Crea las tablas de plantillas y envios de manera aditiva, sin modificar datos electorales existentes. |
| `VotoUTN/apps/elecciones/servicios/notificaciones.py` | Se centralizo la creacion de envios para usuarios con rol en la eleccion y perfiles electorales alcanzados por claustro. Tambien se implemento el procesamiento por correo y el registro de envios fallidos. |
| `VotoUTN/apps/elecciones/management/commands/procesar_notificaciones.py` | Se agrego el comando `python manage.py procesar_notificaciones` para procesar la cola de envios pendientes. |
| `VotoUTN/apps/elecciones/forms.py`, `views.py` y `urls.py` | Se agregaron formularios y rutas de administracion de plantillas, envios por eleccion, bandeja personal y detalle de notificacion. |
| `VotoUTN/apps/elecciones/context_processors.py` y `VotoUTN/config/settings.py` | Se incorporo al contexto global el contador de notificaciones sin leer para mostrarlo en la navegacion. |
| `VotoUTN/templates/elecciones/gestion_notificaciones.html`, `mis_notificaciones.html` y `detalle_notificacion.html` | Se implementaron las pantallas de Junta para crear plantillas y enviar avisos, y las vistas de recepcion y lectura para los usuarios. |

## Etapa 10 - Reportes operativos

Fecha de implementacion: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/views.py` y `urls.py` | Se incorporaron la pantalla de reportes de cada eleccion y exportaciones CSV de padron, mesas, participacion, autoridades, justificativos y errores de importacion. El acceso queda restringido a los roles de Junta autorizados. |
| `VotoUTN/templates/elecciones/reportes.html` | Se creo el panel de descargas con conteos por reporte y acceso a cada exportacion disponible. |
| `VotoUTN/templates/elecciones/configurar_eleccion.html` | Se agrego Reportes como acceso central dentro de la configuracion de la eleccion. |
| `VotoUTN/apps/elecciones/views.py` | Las exportaciones usan CSV UTF-8 con BOM y protegen contra inyeccion de formulas ante valores que comienzan con `=`, `+`, `-` o `@`. |

### Verificaciones realizadas para las etapas 8, 9 y 10

- `python manage.py migrate`: aplico correctamente las migraciones `0015` y `0016`.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 24 pruebas correctas.

## Etapa 8 - Justificativos

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` y migración `0015_tipojustificativo_justificativoausencia.py` | Se agregaron tipos configurables y justificativos con archivo, estado, presentación, revisor, fecha y observación de resolución. |
| `VotoUTN/apps/usuarios/permisos.py` | Administrador de Junta y Administrativo de Junta pueden revisar y resolver, además de superusuarios y administrador del sistema. |
| `VotoUTN/apps/elecciones/forms.py` | Se agregaron formularios de presentación y resolución; los adjuntos aceptan PDF/JPG/PNG de hasta 5 MB. |
| `VotoUTN/apps/elecciones/views.py` y `urls.py` | Se incorporaron presentación propia, bandeja general de Junta, revisión por elección y resolución trazable. |
| `VotoUTN/templates/elecciones/` | Se crearon las pantallas de presentación, bandeja, gestión y resolución; Justificativos se agregó a la navegación principal. |

### Verificaciones

- Migración `0015` aplicada correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py test`: 24 pruebas correctas.

## Etapa 7 - Autoridades de mesa

Fecha de implementacion: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | Se agregaron `AsignacionAutoridad`, con elector del padrón, mesa, estado, responsable y fechas de respuesta, y `PreferenciaAutoridad`, con disponibilidad y preferencias de sede y turno. Se valida que la mesa sea de la misma elección y claustro. |
| `VotoUTN/apps/elecciones/migrations/0013_asignacionautoridad_preferenciaautoridad.py` | Crea las tablas de autoridades y preferencias sin alterar registros existentes. |
| `VotoUTN/apps/elecciones/servicios/autoridades.py` | Se creó el servicio único de asignación para carga manual y CSV. Valida padrón, elección, mesa y claustro; cuando existe un perfil de usuario para el elector, habilita su rol operativo de autoridad de mesa. Incluye validación de CSV y respuesta de confirmación. |
| `VotoUTN/apps/elecciones/forms.py` | Se agregaron formularios para asignación manual, archivo CSV y preferencias personales de autoridad. |
| `VotoUTN/apps/elecciones/views.py` y `urls.py` | Se incorporó la gestión de autoridades dentro de configuración de elección, la carga manual/CSV y las rutas `/autoridad/` para consulta, respuesta y preferencia de la autoridad asignada. |
| `VotoUTN/templates/elecciones/gestion_autoridades.html` | Se creó el panel de Junta Electoral con carga manual, CSV y trazabilidad de asignaciones. |
| `VotoUTN/templates/elecciones/mis_asignaciones_autoridad.html` y `preferencia_autoridad.html` | Se crearon las pantallas operativas para confirmar o rechazar una mesa y registrar disponibilidad/preferencias. |
| `VotoUTN/templates/elecciones/configurar_eleccion.html` | Se agregó el acceso central a Autoridades de mesa y el contador de asignaciones. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas de asignación válida, sincronización del rol de autoridad y rechazo de mesa perteneciente a otro claustro. |

### Verificaciones realizadas

- `python manage.py migrate`: aplicó `elecciones.0013_asignacionautoridad_preferenciaautoridad` correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py test`: 24 pruebas correctas.

### Complemento de etapa 6 - Configuracion central y mesas automaticas

Fecha de implementacion: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | `RegistroPadron` ahora conserva la sede de asistencia de cada elector. `Mesa` incorpora `generada_automaticamente` para distinguir mesas derivadas del padrón de mesas históricas o manuales. |
| `VotoUTN/apps/elecciones/migrations/0012_mesa_generada_automaticamente_registropadron_sede.py` | Agrega ambos campos de forma anulable o con valor por defecto, sin borrar ni modificar padrones o mesas existentes. |
| `VotoUTN/apps/elecciones/servicios/importacion_padron.py` | Al confirmar un CSV se reconstruyen las mesas automáticas del claustro: agrupa el padrón por departamento y sede, ordena por nombre completo y legajo, toma el turno más temprano de la elección y divide cada grupo por el máximo de electores por mesa. Luego crea las asignaciones de mesa correspondientes. |
| `VotoUTN/apps/elecciones/views.py` y `urls.py` | Se agregó `configurar-eleccion`. La lista de elecciones y el historial ahora incluyen todos los estados. La vista de mesas pasó a ser una consulta del resultado automático, sin formulario para elegir cantidades. |
| `VotoUTN/templates/elecciones/configurar_eleccion.html` | Se creó el punto central de configuración con accesos a datos generales, sedes y departamentos, padrones y mesas. |
| `VotoUTN/templates/elecciones/gestion_lista.html` y `historial_elecciones.html` | Se reemplazaron las acciones separadas de alcances y mesas por un único botón `Configuracion`; el historial muestra borradores, elecciones preparadas, abiertas y cerradas. |
| `VotoUTN/templates/elecciones/base_gestion.html` y `gestion_mesas.html` | La navegación pasa a llamar `Historial de elecciones`; la pantalla de mesas explica y muestra la asignación automática, sin permitir definir una cantidad manual. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregó una prueba con tres electores y máximo dos por mesa. Comprueba la creación de dos mesas y la asignación alfabética `Ana Perez`, `Bruno Gomez`, `Zoe Alvarez`. |

### Verificaciones realizadas

- `python manage.py migrate`: aplicó `elecciones.0012_mesa_generada_automaticamente_registropadron_sede` correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 22 pruebas correctas.

## Etapa 6 - Padrones e importaciones CSV

Fecha de implementacion: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | `EleccionClaustro` incorpora fecha de votacion y maximo de votantes por mesa. Se agregaron `ImportacionPadron` y `ErrorImportacionPadron` para conservar archivo, huella SHA-256, claustro, usuario, fecha, estado, resumen y errores por fila. `Elector` ahora conserva correo electronico. |
| `VotoUTN/apps/elecciones/migrations/0010_preparacion_por_claustro.py` | Agrega de forma anulable la fecha de votacion y el maximo por mesa a configuraciones de claustro existentes. |
| `VotoUTN/apps/elecciones/migrations/0011_elector_correo_electronico_importacionpadron_and_more.py` | Agrega correo a electores y crea las tablas de trazabilidad de importaciones y errores sin modificar ni borrar padrones existentes. |
| `VotoUTN/apps/elecciones/forms.py` | Se agrego la preparacion por claustro con fecha, capacidad, departamentos y sedes mediante casillas. No permite quitar sedes ya utilizadas por un padron importado. Se agrego el formulario CSV, limitado a 5 MB y extension `.csv`. |
| `VotoUTN/apps/elecciones/servicios/importacion_padron.py` | Se creo el servicio de validacion y confirmacion. Exige las cabeceras `dni,legajo,nombres,apellidos,mail,departamento,sede`, UTF-8, DNI, correo, duplicados internos, departamento y sede habilitados para el claustro. Rechaza celdas que comiencen con `=`, `+`, `-` o `@`. La confirmacion verifica la huella y persiste en una transaccion; una reimportacion confirmada no duplica registros. |
| `VotoUTN/apps/usuarios/permisos.py` | Se agrego `puede_importar_padron`; habilita a superusuario, administrador del sistema y roles de junta asignados a la eleccion. |
| `VotoUTN/apps/elecciones/views.py` y `urls.py` | Se incorporaron descarga de plantilla, carga y previsualizacion, confirmacion, descarga de errores y listado historico de importaciones. Todas las rutas verifican permisos y bloquean importacion en elecciones abiertas o cerradas. |
| `VotoUTN/templates/elecciones/preparar_eleccion.html`, `preparar_claustro.html`, `cargar_padron.html`, `detalle_importacion_padron.html` y `historial_importaciones_padron.html` | Se implemento el flujo visual de Junta Electoral: configuracion previa, plantilla, carga, resumen de filas, detalle de errores, confirmacion e historial. |
| `VotoUTN/static/css/gestion-electoral.css` | Se agrego el resumen visual de importacion y su comportamiento responsive dentro de la identidad del maquetado administrativo. |
| `VotoUTN/config/settings.py` y `config/urls.py` | Se agrego configuracion de `MEDIA_ROOT` y `MEDIA_URL`; los archivos se sirven solo en desarrollo cuando `DEBUG` esta activo. |
| `VotoUTN/.gitignore` | Se excluyo `media/` para impedir que archivos de padron queden versionados. |
| `VotoUTN/apps/asistencia/tests.py` | Se agregaron pruebas de CSV valido, confirmacion idempotente, persistencia de correo, rechazo de formulas y sedes fuera del alcance, y previsualizacion desde la interfaz. |

### Verificaciones al cierre

- `python manage.py migrate`: aplico `elecciones.0011_elector_correo_electronico_importacionpadron_and_more` correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes luego de aplicar la migracion.
- `python manage.py test`: 21 pruebas correctas.

### Complemento de etapa 5 - Identificacion de parametros

Fecha de cierre: 2026-08-03

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/models.py` | Se eliminaron los campos `codigo` de `Sede` y `Claustro`. Ambos parametros pasan a identificarse exclusivamente por nombre; `Departamento` conserva su codigo. |
| `VotoUTN/apps/elecciones/migrations/0009_quitar_codigos_sede_y_claustro.py` | Se creo y aplico la migracion que elimina las dos columnas. Al momento de aplicarla existia una sede y ningun claustro; los valores de codigo no tenian consumidores funcionales. |
| `VotoUTN/apps/elecciones/forms.py` y `views.py` | Se quitaron los codigos de los formularios y listados de sedes y claustros. |
| `VotoUTN/apps/asistencia/tests.py` | Se actualizaron los datos de prueba para crear sedes y claustros solo por nombre. |

### Verificaciones al cierre

- `python manage.py migrate`: aplico `elecciones.0009_quitar_codigos_sede_y_claustro` correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py test`: 18 pruebas correctas.

## Modularizacion completa de modelos

Fecha de implementacion: 2026-09-07

| Area | Cambio aplicado |
| --- | --- |
| `parametros`, `padron`, `mesas`, `autoridades`, `justificativos` y `notificaciones` | Cada aplicacion pasa a declarar y administrar sus propios modelos de dominio. |
| `elecciones` | Conserva exclusivamente `Eleccion` y las entidades que configuran su alcance electoral. |
| Migraciones | Se usan operaciones de estado separadas de las operaciones de base de datos. Todas las tablas conservan sus nombres fisicos `elecciones_*` y no se ejecuta DDL destructivo. |
| `django_content_type` | Los registros de los modelos trasladados cambian al nuevo `app_label`, preservando sus permisos existentes. |
| Consumidores | Formularios, vistas, servicios, comandos, administracion y pruebas importan cada modelo desde su aplicacion propietaria. |

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: solo operaciones de estado y actualizacion de `ContentType`.
- `python manage.py sqlmigrate`: cero operaciones `CREATE TABLE`, `ALTER TABLE` o `DROP TABLE` en las once migraciones nuevas.
- `python manage.py test`: 45 pruebas correctas.

## Correccion del inicio autenticado por rol

Fecha de implementacion: 2026-09-08

| Ruta | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/elecciones/views.py` y `urls.py` | Se agrego una entrada autenticada que envia a los administradores al panel de gestion y a los usuarios operativos a la seleccion de eleccion. |
| `VotoUTN/config/settings.py` | El destino posterior al login ahora utiliza la entrada que resuelve el panel segun los permisos del usuario. |
| `VotoUTN/apps/elecciones/tests_inicio.py` | Se cubren el login sin destino explicito y las rutas iniciales de superusuarios y usuarios operativos. |

## Partidos participantes y candidatos

Fecha de implementacion: 2026-09-08

| Area | Cambio aplicado |
| --- | --- |
| `VotoUTN/apps/partidos/` | Se creo la app propietaria de partidos, participaciones electorales, listas por alcance y candidatos. |
| Modelo de candidatos | El vinculo con `Elector` es opcional. Los candidatos externos conservan nombre, DNI y correo propios; los electores vinculados respetan el alcance de su padron cuando existe. |
| Gestion web | Se agregaron alta de partidos, incorporacion a elecciones, listas, candidatos, edicion y desactivacion segura. |
| Integracion | La configuracion de cada eleccion muestra la cantidad de partidos y ofrece acceso al modulo. |
| Migracion | `partidos.0001_initial` crea cuatro tablas nuevas y sus restricciones sin modificar tablas existentes. |
| Pruebas | Se cubren permisos, flujo web, candidatos externos, vinculo opcional al elector, alcance electoral y duplicados entre listas. |

### Verificaciones al cierre

- `python manage.py migrate`: aplico `partidos.0001_initial` correctamente.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 57 pruebas correctas.

## Cierre de modularizacion estructural

Fecha de implementacion: 2026-09-08

| Area | Cambio aplicado |
| --- | --- |
| Plantillas | Las pantallas de `padron`, `mesas`, `autoridades`, `justificativos`, `notificaciones`, `parametros` y `reportes` se trasladaron a namespaces propios. La base de gestion paso a `templates/gestion/base.html`. |
| Comandos | `cargar_electores_demo`, `seed_voters` y `seed_random_electores` pertenecen ahora a `padron`; `procesar_notificaciones` pertenece a `notificaciones`. Sus nombres publicos se conservan. |
| `elecciones` | Conserva plantillas y comandos transversales del nucleo electoral; `seed_demo_data` permanece como orquestador integral. |
| `pagina_web` | Se elimino el directorio residual de bytecode. Las maquetas y recursos estaticos se conservaron segun la decision funcional. |
| Documentacion | `plan_implementacion.md` refleja las etapas entregadas y separa el backlog externo de Keycloak, correo, usuarios y produccion. Se verifico que los supuestos caracteres corruptos eran solo una representacion de PowerShell y no mojibake almacenado. |

### Verificaciones al cierre

- Los comandos trasladados responden a `python manage.py help` con sus nombres originales.
- No quedan referencias a los namespaces de plantillas anteriores.
- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 57 pruebas correctas.

## Catálogos reutilizables, mensajes estándar y protección de QR

Fecha de implementación: 2026-09-13

| Área | Cambio aplicado |
| --- | --- |
| Parámetros | Se completó el ABM sin eliminación física de sedes, claustros, departamentos, turnos, fechas administrativas, tipos de justificativo y plantillas de mensajes. Las altas, ediciones y transiciones de estado quedan auditadas. |
| Fechas y mensajes | `FechaAdministrativa` incorpora código, modalidad, duración, alcance, criterio y evento sugerido. Las comunicaciones y variantes enlazan las plantillas sin ampliar la audiencia de la fecha. |
| Carga estándar | Se agregó `python manage.py cargar_parametros_estandar`, transaccional e idempotente. Carga 2 sedes, 4 claustros, 3 turnos, 10 departamentos, 6 fechas, 26 plantillas y sus reglas; reactiva los registros canónicos y conserva extras e identificadores. |
| Compatibilidad | La migración convierte mensajes embebidos existentes en plantillas y comunicaciones antes de retirar los campos anteriores. Los seis campos históricos de `Eleccion` y `FechaAdministrativaEleccion` continúan operativos. |
| Notificaciones | La pantalla manual solo ofrece plantillas activas habilitadas para ese uso. Las plantillas automáticas y transaccionales quedan fuera de la selección manual y disponen de vista previa. |
| QR | `RegistroPadron` conserva fecha de emisión y mesa impresa. La generación marca solo después de crear los archivos; bloquea cambios de mesa, reimportaciones y regeneraciones automáticas incompatibles. El payload y su validación permanecen sin cambios. |
| Mesas | Se mantiene la generación automática y la consulta; no se agregó un ABM manual. |

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 68 pruebas correctas.

## Puestos, listas y candidaturas por elección

Fecha de implementación: 2026-09-19

- Parámetros presenta una única entrada «Puestos a elegir», con órganos o cuerpos y puestos reutilizables. Las agrupaciones dejaron de ser un parámetro. Cada puesto indica si permite limitar por claustros y por departamentos mediante opciones independientes.
- En cada elección, no activar un filtro equivale a incluir todos sus valores. Puede limitarse solo por claustros, solo por departamentos, por ambos o por ninguno; el sistema genera los alcances resultantes sin exigir que un filtro active al otro.
- Número y nombre de lista, código de presentación y apoderado pertenecen a la elección. Se permite repetir un número de lista en presentaciones distintas.
- Se incorporó una plantilla CSV única, previsualización con errores y advertencias, confirmación transaccional y trazabilidad de la importación.
- Una persona puede integrar más de una candidatura; si el mismo identificador figura en presentaciones diferentes se emite una advertencia sin bloquear la carga.
- Las migraciones preservan los registros históricos y mantienen opcional el vínculo legado con `Partido`.

## Datos demostrativos electorales

Fecha de implementación: 2026-09-20

- `cargar_parametros_estandar` incorpora tres órganos y sus puestos reutilizables: Consejo Directivo, Consejo Departamental y Consejo DASUTeN.
- `seed_demo_data` es el inicializador integral para el equipo: primero carga los parámetros estándar y luego crea una elección demo idempotente.
- La elección de ejemplo incluye los cuatro claustros, el alcance departamental de Sistemas, nueve configuraciones de puestos y casos representativos de las listas 2026 entregadas por la Junta.
- Los ejemplos conservan números repetidos cuando representan presentaciones diferentes y cubren cargos generales, departamentales y de DASUTeN.

## Fechas del proceso y calendario administrativo

Fecha de implementación: 2026-09-22

- La creación de una elección solicita solamente el nombre, el rango general del proceso y sus parámetros iniciales.
- Las fechas administrativas se cargan y modifican desde la configuración de la elección, dentro de su calendario administrativo.
- El inicio y el fin del proceso se almacenan como días, sin componente horario. Se admite que ambos coincidan para procesos de un solo día.
- La migración conserva el día calendario de los datos existentes según la zona `America/Argentina/Buenos_Aires` y descarta solamente la hora.
- Los campos de inicio y fin incorporan ayuda contextual accesible para distinguir el proceso electoral del día de votación.

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: se validó la operación segura de `elecciones.0021_fechas_de_eleccion_sin_hora`.
- `python manage.py test`: 111 pruebas correctas.

## Turnos de trabajo de autoridades

Fecha de implementación: 2026-09-23

- Los turnos representan exclusivamente rondas de trabajo de autoridades de mesa; no restringen el horario de votación de los electores.
- La mesa dejó de tener turno y permanece operativa durante toda la jornada electoral.
- La creación de elecciones solicita únicamente claustros y sedes como configuración inicial.
- Los turnos habilitados se administran desde Autoridades de mesa y cada asignación vincula autoridad, mesa y turno de trabajo.
- El máximo de autoridades se aplica por mesa y por turno, permitiendo varias autoridades simultáneas y el recambio entre rondas.
- La migración copió los turnos históricos de las mesas a las autoridades antes de retirar el campo anterior.

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate`: aplicó `autoridades.0003_turno_de_trabajo_en_autoridad` y `mesas.0002_remove_mesa_turno`.
- `python manage.py test`: 114 pruebas correctas.

## Ajustes visuales de creación y fechas administrativas

Fecha de implementación: 2026-09-26

- La selección de sedes y claustros en la creación de elecciones se presenta en una sola columna, sin recuadros individuales y con espacios uniformes.
- La acción «Seleccionar todas» conserva su comportamiento, pero queda separada del estilo visual de las opciones.
- Fechas administrativas se incorporó como una tarjeta del panel de configuración de la elección.
- La edición del calendario administrativo se trasladó a una pantalla propia, con los mismos permisos, validaciones y datos existentes.
- Se agregaron pruebas de regresión para la nueva estructura del selector y la navegación al panel independiente.

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 115 pruebas correctas.

## Navegación interna de la configuración electoral

Fecha de implementación: 2026-09-26

- Las secciones principales de una elección regresan de forma consistente a su panel de configuración, sin redirigir al listado general.
- La acción «Volver a configuración» aparece una sola vez, fuera de las tarjetas, al final de la pantalla y alineada con el borde derecho del contenido.
- Los formularios de Datos generales y Fechas administrativas ubican su acción de guardado a la izquierda del regreso y mantienen ambas acciones alineadas con el ancho de la tarjeta.
- Se incorporó un componente reutilizable para el regreso y pruebas de regresión en elecciones, mesas, autoridades, candidaturas, justificativos y reportes.

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 117 pruebas correctas.

## Tarjetas uniformes del panel de configuración

Fecha de implementación: 2026-09-26

- Las ocho tarjetas principales del panel de configuración utilizan una grilla visual específica, sin alterar otros paneles del sistema.
- En escritorio comparten altura y distribución interna entre ambas filas.
- Las acciones tienen ancho uniforme y se alinean al borde inferior de cada tarjeta.
- En pantallas móviles las tarjetas recuperan su altura natural para evitar espacios vacíos.

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 117 pruebas correctas.

## Unificación visual de puestos, listas y candidaturas

Fecha de implementación: 2026-09-26

- La gestión de candidaturas se reorganizó en cuatro tarjetas de ancho uniforme: puestos habilitados, importación CSV, presentación manual y presentaciones registradas.
- Los encabezados, etiquetas, formularios, tablas y acciones siguen una jerarquía visual común y responsive.
- Los selectores múltiples de claustros y departamentos utilizan el componente visual de listas de selección en lugar del estilo de campos de texto.
- Se preservaron los formularios, rutas y reglas funcionales existentes.

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 117 pruebas correctas.

## Gestión de autoridades por claustro

Fecha de implementación: 2026-09-27

- Autoridades de mesa incorpora una pantalla previa con una tarjeta uniforme por claustro y un resumen de turnos, mesas, candidatos y asignaciones.
- Cada claustro dispone de una pantalla independiente para configurar turnos, realizar asignaciones manuales, cargar candidatos por archivo y consultar asignaciones registradas.
- Los bloques se presentan como opciones independientes, sin numeración ni una secuencia obligatoria.
- Los formularios, listados e importaciones quedan limitados al claustro seleccionado y rechazan candidatos, mesas o turnos pertenecientes a otro claustro.
- Los turnos de autoridades dejaron de configurarse globalmente y ahora pertenecen a cada claustro. La migración replica los turnos existentes en todos los claustros de su elección antes de retirar la relación anterior.
- Los datos demo, el administrador y los comandos auxiliares fueron actualizados al nuevo alcance por claustro.
- La futura asignación automática de candidatos a mesas no forma parte de este cambio; el archivo continúa cargando candidatos sin indicar mesas.

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate`: aplicó `elecciones.0022_turnos_autoridades_por_claustro` y conservó los turnos existentes.
- `python manage.py test`: 122 pruebas correctas.

## Gestión integrada de padrones por claustro

Fecha de implementación: 2026-09-27

- La pantalla de Padrones presenta una tarjeta uniforme por claustro y una única acción «Gestionar padrón».
- La gestión de cada claustro reúne la fecha de votación, el máximo de electores por mesa, la carga del archivo y su historial de importaciones.
- Departamentos y sedes dejaron de editarse desde Padrones y permanecen centralizados en «Sedes y departamentos».
- El historial integrado muestra exclusivamente las importaciones del claustro seleccionado.
- La ruta anterior de configuración del claustro redirige a la nueva pantalla para conservar compatibilidad con enlaces existentes.
- La validación, previsualización y confirmación de archivos mantienen su comportamiento funcional.

### Verificaciones al cierre

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check`: sin cambios pendientes.
- `python manage.py migrate --plan`: sin operaciones pendientes.
- `python manage.py test`: 125 pruebas correctas.

## Confirmación de notificaciones a ausentes

Fecha de implementación: 2026-10-19

- El tablero ofrece al administrador de junta una acción confirmable cuando todas las mesas están procesadas.
- El servidor vuelve a validar permisos, estado de elección y procesamiento de todas las mesas; rechaza confirmaciones repetidas.
- Se generan notificaciones web para electores activos registrados como ausentes mediante escaneo de QR. Se intenta el envío por correo y se informa el resultado sin ocultar los avisos web cuando falla el correo.
- La confirmación, el usuario y los totales de notificación/correo quedan registrados en la elección y en auditoría.
- `elecciones.0028_eleccion_notificaciones_ausentes_confirmadas_en` agrega el marcador de confirmación sin alterar datos existentes.
- Se agregaron pruebas para confirmar que no se notifica antes de procesar todas las mesas, para la autorización exclusiva de junta y para la idempotencia del envío.

## Autoridades: tres modos y decisiones C/C

Fecha: 2026-10-23.

Se integró la base local de modos aleatorio por mesa, manual por mesa y nómina
común con las decisiones confirmadas: reacomodo mínimo optativo de titulares
y reemplazo confirmado por la Junta independiente del justificativo.
Los traslados confirmados modifican el destino laboral, no el padrón electoral.
Los suplentes conservan su mesa al promoverse. La confirmación registra usuario,
fecha y reemplazante y es idempotente; sin suplente queda vacante visible.

El alcance completo, archivos, dependencias, comandos y pasos de revisión están
en [plan_autoridades_tres_modos.md](plan_autoridades_tres_modos.md), que es el punto
de entrada para retomar este trabajo sin historial de conversación.

Verificaciones en PostgreSQL del contenedor: 335 pruebas de la suite completa
correctas, seguidas por 63 pruebas de autoridades correctas después de los ajustes
finales. `check`, `makemigrations --check` y `migrate --plan` correctos; aplicada
`autoridades.0007_traslados_y_reemplazos_independientes`. No hubo eliminaciones,
commit ni push. Revisión visual del usuario pendiente antes del commit.

## Autoridades: sorteo completo y conservación de asignaciones

Fecha: 2026-10-23.

Se corrigió el conteo duplicado de un mismo titular en varios cupos de una mesa
y turno. «Sortear todas las mesas» conserva cada asignación válida una sola vez,
incluidas las selecciones manuales. «Recalcular» solicita confirmación y reemplaza
todo el plantel desde cero; la limpieza de destinos manuales y traslados laborales
se realiza en el servicio, en la misma transacción que el cálculo y el guardado.
La operación conserva las reglas de elegibilidad y puede volver a elegir a las
mismas personas por azar.

El emparejamiento usa caminos aumentantes iterativos, con prioridad de un titular
por mesa/turno, titulares restantes y suplentes. Se sortean personas y cupos de
igual prioridad. Se verifican unicidad de personas y coincidencia exacta entre
la solución y las filas persistidas. La auditoría identifica completar/recalcular,
las asignaciones anteriores/resultantes y las vacantes. Los mensajes distinguen
la falta de combinaciones compatibles de la limitación de conservar asignaciones.
La baja explícita de un titular vuelve a promover al primer suplente compatible;
esa acción es independiente de completar cupos con el botón Sortear.

Archivos modificados en esta corrección:

- `VotoUTN/apps/autoridades/distribucion.py`: cálculo, recálculo, validaciones,
  consulta conjunta de candidatos electorales, auditoría y promoción por baja.
- `VotoUTN/apps/autoridades/views.py`: conexión de ambas acciones con el servicio
  y mensajes de cobertura.
- `VotoUTN/templates/autoridades/gestion_claustro.html`: explicación de las acciones
  y actualización de versión del JavaScript. Se publicaron los estáticos y se
  comprobó por HTTP que el servidor entrega la versión actual sin confirmación doble.
- `VotoUTN/apps/autoridades/tests_distribucion.py`: regresiones, recálculo desde
  cero, conservación, reversión ante errores, restricciones, desempate entre turnos
  y comparación exhaustiva de cobertura en grafos pequeños; cadena de 1100 plazas
  para verificar que no depende del límite de recursión.
- `VotoUTN/apps/autoridades/tests.py`: expectativas actualizadas al flujo de aplicar
  distribución después de configurar turnos y a los controles vigentes.
- `docs/decisiones_funcionales.md`, `docs/autoridades_modalidades.md` y este registro:
  comportamiento confirmado y documentación de continuidad.

Esta corrección no crea ni elimina archivos ni cambia modelos o migraciones.

Verificaciones finales en PostgreSQL del contenedor:

- `python manage.py check`: sin problemas.
- `python manage.py makemigrations --check`: sin cambios.
- `python manage.py migrate --plan`: sin migraciones pendientes.
- `python manage.py test --keepdb --noinput`: **348 pruebas correctas**.
- `git diff --check`: sin errores; únicamente avisos de finales de línea CRLF.
- Estático servido por HTTP: respuesta 200 y contenido idéntico al archivo fuente.

## Autoridades: eliminar todas las asignaciones del claustro

Fecha: 2026-10-24.

Se agregó al final del detalle un botón de eliminación con confirmación. Deja
vacías las asignaciones del claustro actual sin ejecutar otro sorteo. El servicio
elimina sus roles de autoridad y limpia las selecciones manuales/de planilla,
destinos laborales y marcas de autoridad al final del padrón; conserva electores,
mesas de votación, nómina, exclusiones y configuración. Respeta los bloqueos por
estado electoral, QR y avisos de ausencia, y registra las asignaciones anteriores
en `autoridades.asignaciones_eliminadas` dentro de la misma transacción.

Archivos modificados:

- `VotoUTN/apps/autoridades/distribucion.py`: servicio atómico con permisos,
  alcance por claustro, limpieza de dependencias y auditoría.
- `VotoUTN/apps/autoridades/views.py`: acción POST que exige confirmación explícita.
- `VotoUTN/templates/autoridades/gestion_claustro.html`: botón al pie, CSRF y aviso
  integrado en el formulario, independiente del JavaScript estático.
- `docs/decisiones_funcionales.md`, `docs/autoridades_modalidades.md` y este registro:
  alcance y comportamiento para futuras sesiones.

Archivo creado: `VotoUTN/apps/autoridades/tests_eliminar_asignaciones.py`, con
ocho pruebas de confirmación, alcance, conservación del padrón/configuración,
permisos/CSRF, bloqueos, reversión ante fallos e idempotencia.
No se eliminan archivos ni se modifican modelos o migraciones.

Verificación de la eliminación: ocho pruebas específicas y **356 pruebas de la
suite completa correctas**. `check`, `makemigrations --check` y `migrate --plan`
sin problemas ni operaciones pendientes.

## Autoridades: tabla compacta y filtros del listado

Fecha: 2026-10-24.

Se mantiene el formato de tabla pedido por el usuario. Se separan Mesa,
Departamento, Sede, Turno, Titulares, Suplentes y Autoridades; se agrupan las filas
de turno bajo cada mesa y los cupos se muestran como «1 de 2». El detalle de
personas se abre/cierra debajo de cada grupo, con indicadores accesibles y sin
recargar la página. Se conservan el orden titular/suplente y las acciones de
confirmar reemplazo.

Se agregan filtros GET combinables por departamento, sede y cobertura. Validan
opciones dentro del claustro, muestran un estado vacío cuando no hay coincidencias
y conservan filtros al paginar hasta 25 mesas. El ancla de filtros/paginación
lleva al listado. No modifican asignaciones ni el alcance de las acciones globales.

Archivos modificados: `VotoUTN/apps/autoridades/forms.py`,
`VotoUTN/apps/autoridades/views.py`,
`VotoUTN/templates/autoridades/gestion_claustro.html`,
`VotoUTN/templates/gestion/base.html`,
`VotoUTN/static/css/gestion-electoral.css`,
`VotoUTN/static/js/explicacion-modo-autoridades.js`,
`docs/decisiones_funcionales.md`, `docs/autoridades_modalidades.md` y este registro.
Se crea `VotoUTN/apps/autoridades/tests_vista_mesas.py` con seis pruebas de
agrupación, columnas, filtros, paginación, límites del claustro y reemplazos.
No se eliminan archivos ni se requieren migraciones.

Verificación: **362 pruebas correctas** en la suite completa, más las seis pruebas
del listado repetidas tras el ajuste final de columnas. Comprobaciones de Django
y migraciones correctas. Se comprobó la apertura/cierre del detalle con Node, y
CSS/JavaScript publicados con versión nueva y verificados por HTTP (200 y contenido
idéntico al fuente).

## Autoridades: restaurar nómina común y títulos sin numeración

Fecha: 2026-10-25.

Se vuelve a ofrecer «Nómina común» en el selector, con carga de personas manual
o por archivo y controles para permitir propuestas de cambio de sede y reacomodar
titulares. Al aplicar el modo se guardan las opciones, se auditan y se distribuye
la nómina. Desactivar los cambios de sede limpia los destinos laborales confirmados
y vuelve a distribuir dentro de la sede electoral, sin modificar el padrón.
La planilla conserva la validación de pertenencia a la mesa indicada: una fila
seleccionada inválida impide aplicar todo el archivo.

Se retiran los prefijos numéricos de «Turnos y cupos» y «Modo de elección».

Archivos modificados en esta tarea:

- `VotoUTN/apps/autoridades/forms.py`, `views.py` y `distribucion.py`.
- `VotoUTN/templates/autoridades/gestion_claustro.html`.
- `VotoUTN/static/js/explicacion-modo-autoridades.js`.
- `VotoUTN/apps/autoridades/tests.py`, `tests_distribucion.py` y `tests_traslados.py`.
- `docs/decisiones_funcionales.md`, `docs/autoridades_modalidades.md` y este registro.

No se crean ni eliminan archivos en esta tarea ni se requieren migraciones.

Verificación final: **369 pruebas correctas** en PostgreSQL. `check`,
`makemigrations --check` y `migrate --plan` sin problemas ni operaciones pendientes.
JavaScript validado con Node, publicado y comprobado por HTTP (200 y contenido
idéntico al fuente). `git diff --check` sin errores de espacios.

## Autoridades: pantalla común y nómina por archivo (en curso)

Fecha: 2026-10-25.

Se compacta la pantalla de nómina con la misma estructura de turnos, modo y
tabla de mesas utilizada por los otros modos. Se retira la carga manual de la
nómina y se integra su archivo CSV/XLSX en el formulario del modo. «Cargar nómina»
guarda opciones, importa y distribuye atómicamente, sin un paso de cálculo
separado. Las cargas agregan personas a la nómina vigente sin duplicarlas ni
levantar exclusiones existentes. Cambiar opciones de una nómina ya cargada o
guardar sus turnos/cupos dispara la distribución automáticamente.

El resumen separa titulares, suplentes y personas de la nómina sin asignar de
los cupos vacantes. La comparación entre opciones está pendiente de definir el
alcance de cambio de sede automático y cambio de mesa con el usuario; todavía
no se muestra una estimación. Las reglas existentes de esos movimientos siguen
vigentes mientras se resuelven esas preguntas.

Se crean `VotoUTN/apps/autoridades/nomina.py` y `tests_nomina.py`. Se modifican
`forms.py`, `views.py`, `services.py`, `distribucion.py`, `tests.py` y
`tests_distribucion.py` de autoridades, su plantilla `gestion_claustro.html` y
`static/js/explicacion-modo-autoridades.js`, además de este registro. No se
eliminan archivos ni se cambian modelos o migraciones.

Verificación parcial: `check`, `makemigrations --check` y `migrate --plan`
correctos. La suite de 375 pruebas detectó únicamente una expectativa antigua
que exigía calcular después de cambiar turnos; se actualizó al flujo automático.
Luego pasaron las 57 pruebas de turnos, distribución y nueva carga de nómina.
JavaScript validado con Node y publicado con contenido verificado por HTTP 200.
La tarea completa sigue pendiente de las definiciones necesarias para los escenarios.

## Integración de develop del 27 de octubre de 2026

Se integra `origin/develop` hasta `d96e638e` en `feat/62-autoridades-de-mesa`
mediante el commit de merge `b1385d66`. Incluye diez commits nuevos de estados
electorales, solicitudes de cambio de sede, notificaciones y exportación de padrón.
El trabajo local previo se recupera sin publicarlo ni incorporarlo al commit
de integración. Se conserva el respaldo completo en el stash
`7bc2a782291e6a20e6fa5f07e0411f85d619c6e3`.

Se crean las migraciones de unión `elecciones/0029_merge_20261027_1450.py` y
`padron/0013_merge_20261027_1450.py`, sin alterar migraciones anteriores. Se
aplican las migraciones pendientes en la base de desarrollo PostgreSQL.

La resolución combina las pruebas de tipo de documento con turno de cursada;
conserva el recálculo de sedes y mesas, los servicios de autoridades y la creación
atómica de notificaciones al resolver justificativos. Archivos con resolución
manual: `apps/padron/{services,tests,views}.py`, `apps/justificativos/views.py`,
`templates/gestion/base.html`, `templates/padron/configurar_sedes_claustro.html`,
`docs/decisiones_funcionales.md` y este registro.

Se ajustan `apps/autoridades/reemplazos.py` y `views.py` para permitir el reemplazo
operativo durante la elección abierta sin habilitar cambios de configuración.
Se verifica su endpoint en `tests_reemplazos.py`; se actualizan las expectativas
de `tests_eliminar_asignaciones.py` y `apps/elecciones/tests_permisos.py` al nuevo
bloqueo de edición y acceso a crear elecciones desde Inicio. No se eliminan
archivos locales ni se hace push. Los cambios previos de nómina siguen sujetos
a las definiciones funcionales pendientes documentadas arriba.

Verificación final: **425 pruebas correctas**. `check` sin problemas,
`makemigrations --check` sin cambios y `migrate --plan` sin operaciones pendientes.
Sin archivos en conflicto ni errores en `git diff --check`; los 24 archivos
nuevos del respaldo se recuperaron. Estáticos actualizados y web con HTTP 200.

## Autoridades: cálculo previo de reordenamiento de padrón (en curso)

Se desarrolla el cálculo sin escritura del reordenamiento: reserva los titulares
al final de su mesa de trabajo y distribuye el resto en orden alfabético, hasta
el máximo por mesa. Informa mesas existentes, propuestas y sobrantes por claustro,
departamento y sede; conserva la identidad de los electores y no modifica datos.
Los traslados no pueden cambiar de claustro o departamento. Se confirmó que se
conserva la restricción para quien cursa en su sede electoral de origen.

Se crean `apps/autoridades/reordenamiento_padron.py` y
`apps/autoridades/tests_reordenamiento_padron.py`; no se cambian modelos ni se
requieren migraciones. El cálculo todavía no está conectado a la interfaz ni a la
confirmación. Está pendiente la decisión sobre crear una mesa nueva cuando la
nómina no alcance para cubrir sus autoridades, además de completar el flujo de
confirmación, las comprobaciones de concurrencia y las pruebas integradas.

Verificación parcial: 7 pruebas específicas y **432 pruebas correctas** en la
suite completa. `check`, `makemigrations --check` y `migrate --plan` correctos;
sin migraciones pendientes. El cálculo aún no está disponible en pantalla.

## Autoridades: propuesta confirmable y conservación de asignaciones

Fecha: 2026-10-27.

Se conectó el cálculo previo de nómina con la pantalla. La propuesta conserva
autoridades y roles existentes, compara mesa propia, misma sede y cambio de sede,
e informa titulares, suplentes, personas sin asignar y mesas agregadas o quitadas
por claustro, departamento y sede. Se puede cancelar; confirmar revalida el estado
de la elección y aplica la propuesta atómicamente. Se registran los movimientos.

El reordenamiento ubica titulares al final de su mesa de trabajo, distribuye al
resto por apellido y nombre y conserva los suplentes ya asignados y mesas con
datos protegidos. Una mesa nueva puede quedar con cupos vacantes; cargas posteriores
los completan sin reemplazar las designaciones existentes. El cambio de sede se
restringe al mismo claustro y departamento y no se traslada a quien cursa en su
sede electoral de origen. Una solicitud de cambio de sede pendiente bloquea su
traslado hasta resolverla. Los QR emitidos y las ausencias siguen protegiendo el
padrón frente a cambios. La regeneración automática de mesas se bloquea cuando
existen autoridades asignadas para no borrar su designación.

La selección manual deja de aparecer como modo y está disponible desde cada mesa
en todos los modos. Los caminos anteriores de carga y cambio de sede no pueden
eludir la previsualización. «Recalcular» y «Eliminar todas las asignaciones» son
acciones explícitas con confirmación y conservan sus efectos documentados.

Archivos creados: `apps/autoridades/reordenamiento_padron.py` y
`apps/autoridades/tests_reordenamiento_padron.py`. Archivos modificados:
`apps/autoridades/{distribucion,forms,nomina,seleccion_manual,services,views}.py`,
`apps/autoridades/{tests,tests_distribucion,tests_nomina,tests_reemplazos,tests_traslados}.py`,
`apps/padron/services.py`, `templates/autoridades/{gestion_claustro,seleccionar_mesa}.html`,
`static/js/explicacion-modo-autoridades.js`, `docs/autoridades_modalidades.md`,
`docs/decisiones_funcionales.md`, `docs/modelo_dominio.md`,
`docs/plan_implementacion.md` y este registro. Las rutas de aplicación y estáticos
son relativas a `VotoUTN/`. No se eliminan archivos ni se agregan migraciones.

Verificación final: **456 pruebas correctas** en la suite completa, más tres
pruebas repetidas sobre la pantalla y la conservación de sedes. `check` sin
problemas, `makemigrations --check` sin cambios y `migrate --plan` sin
operaciones pendientes. JavaScript validado y publicado; inicio y estático
respondieron HTTP 200. `git diff --check` sin errores.

## Nómina: autoridad en mesa de votación distinta

Fecha: 2026-10-28.

Se retira Planilla de asignaciones del selector; la edición manual sigue desde el
detalle de cada mesa. Nómina agrega «Votar en mesa distinta»: asigna a la persona
a otra mesa de la misma sede, en un turno configurado que no se superponga con su
cursada, y conserva intacta su mesa de votación. Es excluyente con el reacomodo
previo del padrón y el cambio de sede. El reacomodo anterior y sus previsualizaciones
se mantienen disponibles con su opción original.

La migración nueva conserva asignaciones, normaliza los modos históricos Planilla
y selección manual a Sorteo, y agrega la opción nueva apagada. Cambios en modelos,
formularios, distribución, previsualización, plantilla, JavaScript, documentación
y pruebas. Archivos principales: `VotoUTN/apps/autoridades/migrations/0009_nomina_mesa_distinta_sin_planilla.py`,
`VotoUTN/apps/autoridades/{models,forms,distribucion,nomina,views}.py` y
`VotoUTN/templates/autoridades/gestion_claustro.html`.
# Autoridades: mínimo por turno y justificativos pendientes

- Se añade revisión firmada de los recálculos manuales y de las aprobaciones de cambios de sede, con movimientos, mesas creadas o quitadas y autoridades provisorias afectadas. Las propuestas vencen o se rechazan si cambia el padrón. Tras importar un padrón, el recálculo automático informa las designaciones que quedan vacantes.
- El inicio comprueba el mínimo de titulares por mesa y turno. Se agrega restitución de mesa anterior sin desplazar electores y una propuesta confirmable cuando es necesario reordenar; los casos sin una partición segura requieren revisión.

- Se habilita la gestión provisoria de autoridades en Publicada. La confirmación definitiva exige cierre y resolución de cambios de sede, registra el plazo de justificación y las convocatorias, y bloquea la edición general. Los traslados por ausencias aprobadas requieren confirmación previa.
- Las solicitudes de cambio de sede utilizan la sede electoral asignada y preservan la sede de cursada. El comando `generar_solicitudes_prueba` permite simular y crear un lote concentrado para probar cambios de mesas.

- La nómina y el sorteo priorizan la cobertura mínima configurada por turno antes de distribuir cupos adicionales. La previsualización se invalida si cambia ese mínimo.

- Se agrega el mínimo de titulares por mesa y turno, con valor inicial 1 para configuraciones existentes. El formulario exige que no supere el máximo y las propuestas de traslado conservan ese mínimo en la mesa de origen.
- La elección no pasa a En curso con justificativos de autoridad pendientes. La presentación de nuevos justificativos de autoridad queda limitada al estado Publicada; los justificativos de ausencia a votar conservan su flujo.
- La migración `elecciones.0032` incorpora el mínimo sin modificar asignaciones ni mesas existentes.
