# Registro de cambios por etapa

## Marca de agua en cada octante de las boletas imprimibles - 18 de noviembre de 2026

- Se replica «Demo Proyecto Final» y «VOTO UTN» en los ocho octantes de cada
  página de boletas, centrando cada marca dentro de su octante y dibujándola
  detrás de los marcos y las boletas.
- Se alinea el dibujo del padrón con sus dos renglones documentados y cubiertos
  por su prueba de regresión.

## Casos de candidatos para los cuatro claustros - 18 de noviembre de 2026

Se publican las cuatro carpetas `listas_*_sin_autoridades` en
`ESCENARIOS_PRUEBA_ELECTORAL/segmento_1_500/`, los padrones filtrados de origen
y los cinco generadores correspondientes en `scripts/`. Se mantienen los dos
CSV multipuesto de Estudiantes previamente publicados, sin modificar sus bytes.

Las listas comprenden Estudiantes 19 y 3; Graduados 19 y 3; Docentes 19 y 2 con
tres sublistas departamentales y una presentación de Directivo y DASUTeN por
familia; y No docentes 9 — Unión y Participación y 3 — Integración. Hay catorce
presentaciones. Los apoderados son ejemplos ficticios externos al padrón.
Superior comparte las mismas treinta personas en las tres sublistas de cada
familia docente. No hay otras repeticiones entre cargos o listas de un claustro.
El caso docente usa cupo 2 y 2 en Directivo, según confirmación del usuario.

`crear_listas_para_csv.py`, `test_crear_listas_para_csv.py` y `CREAR_LISTAS.md`
se agregan en la carpeta común. El script requiere ID explícito de elección
En preparación, previsualiza por defecto y aplica con `--aplicar`. Prepara
las catorce presentaciones con cincuenta asociaciones, conserva datos existentes
y no carga candidatos ni cambia parámetros, puestos o padrones. Si falta un
claustro o puesto o hay un conflicto, rechaza la operación sin carga parcial.
Se puede filtrar por claustro. Las instrucciones explican la carga posterior
mediante los CSV de uno o varios puestos.

Los cuatro generadores reproducen exactamente los archivos suministrados.
Las doce pruebas del script verifican creación sin candidatos, previsualización
sin escrituras, idempotencia, reutilización de listas manuales y apoderados,
asociaciones faltantes, configuración y cupos incompatibles y reversión ante
fallos de auditoría. No se modifican modelos ni migraciones ni se ejecuta la
creación de listas sobre una base habitual como parte de la publicación.

## Marca de agua en dos renglones y actualizacion del contenedor

- La marca de agua dibuja «Demo Proyecto Final» y «VOTO UTN» por separado:
  `drawCentredString` no interpreta saltos de linea. Se conserva la posicion
  ajustada y el fondo blanco de los QR. La regresion verifica ambos renglones
  a distinta altura en cada caratula y hoja.
- Se documenta como compilar y recrear solo el servicio web de la instancia 3
  con Docker Compose, sin ejecutar la restauracion de la foto fija. Compilar
  una imagen no actualiza los contenedores que ya estaban en ejecucion.
- Aplicado solo al contenedor web de la instancia 3, sin restaurar datos ni
  modificar ninguna de las dos fotos. Pasan las 22 pruebas del padron PDF;
  comprobaciones Django y de migraciones sin pendientes. Se verifica HTTPS
  200 y el PDF real con ambos renglones en sus 205 paginas.

## Foto v2 de instancia 3 y marca de agua del padron imprimible

- Se crea `.instancias/foto-instancia-3-v2` a partir de la foto original,
  sin incorporar los cambios posteriores de la base de trabajo. Corrige
  unicamente el apellido del elector de demostracion a «Gómez».
  La comparacion integral de 69 tablas y 68 secuencias y una restauracion
  independiente verifican que no se alteren otros datos. El archivo de
  adjuntos/QR es identico al anterior.
- `.instancias/foto-instancia-3` se conserva intacta; se verifican sus tres
  huellas originales. `scripts/instancias.ps1` selecciona la v2 en cada `up`
  que incluya la instancia 3, conservando el resto del flujo de arranque.
- `apps/reportes/services_pdf.py` dibuja «Demo VOTO UTN» detras del contenido
  de cada caratula y hoja del padron, en todas las instancias, sin modificar
  las firmas QR, la paginacion ni el fondo blanco de los codigos.
- Se agrega una regresion de PDF con dos mesas y varias hojas que comprueba
  el texto en las cinco paginas y su orden anterior a los fondos de QR.
  Se actualizan `README.md` y `docs/decisiones_funcionales.md`.
- Verificado el arranque real con la v2: apellido corregido, 352 ausencias y
  41 mesas procesadas. Las 22 pruebas del padron PDF y las pruebas PowerShell
  pasan; `check`, `makemigrations --check` y `migrate --plan` sin pendientes.
  El PDF real contiene la marca en sus 205 paginas; se rasterizan cinco
  paginas y se decodifican sus 47 QR, incluidos los de mesa y el de Carlos.
  Se comprueba visualmente la caratula y la hoja de Carlos. HTTPS responde 200.
- Se excluye la nueva foto local de Git mediante `.gitignore`, sin eliminar
  ni reemplazar la anterior.

## Foto fija de datos de instancia 3 y restauracion en cada up

- Se captura `.instancias/foto-instancia-3` el 17 de noviembre de 2026 con
  los escritores detenidos: PostgreSQL, adjuntos y QR generados, mas huellas
  SHA-256. No se incluyen Keycloak, Mailpit, secretos ni certificados en esa
  foto local excluida de Git. Los arranques nunca regeneran la captura.
- `scripts/instancias.ps1` valida la foto antes de modificar servicios y la
  restaura en cada `up` que incluya la instancia 3, con PostgreSQL atomico y
  reemplazo de los archivos de ambos volumenes. Una falla impide reanudar los
  escritores. `start` conserva datos de trabajo y las instancias 1 y 2
  mantienen sus flujos anteriores.
- `docker-compose.instancias.yml` omite `iniciar_instancia_demo` solamente
  para la instancia 3; conserva migraciones y recopilacion de estaticos.
- Se actualizan `README.md` y `scripts/tests_instancias.ps1` con cobertura
  de restauracion repetida, aislamiento de instancias, archivos en solo
  lectura, foto ausente/alterada y propagacion de errores.
- Verificado con una tabla y archivos temporales posteriores a la captura:
  `start -Instancia 3` conserva datos y `up -Instancia 3` recupera la foto.
  Las huellas de la captura no cambian y los 10 archivos restaurados
  coinciden exactamente, sin los temporales. El tablero conserva 352
  inasistencias, 41 mesas procesadas y las cuatro mesas K pendientes.
  Pruebas PowerShell y Compose correctas, HTTPS 200, `check` sin problemas,
  `makemigrations --check` sin cambios y `migrate --plan` sin pendientes.

## CSRF del escaneo y la carga manual en instancias independientes

- El cliente compartido usa el token enmascarado generado por Django en el
  formulario del escaner, sin depender del nombre de la cookie ni leer el
  token de otra instancia. El formulario existe tambien en la vista movil.
- Se versiona la cadena de modulos del escaner para renovar la cache.
  Se mantienen la autenticacion, la proteccion CSRF y los contratos QR/API.
- Se agregan regresiones JavaScript y pruebas con validacion CSRF real para
  cookies personalizadas, escaneo de mesa, carga manual y rechazo de tokens
  incorrectos. No hay cambios de modelos ni migraciones.
- Aplicado al servicio web de la instancia 3, sin restaurar datos ni reiniciar
  las instancias 1 y 2. Verificado HTTPS 200 y cliente actualizado desde el
  proxy; pasan 64 pruebas Django de QR/carga manual y 13 pruebas JavaScript.
  `check`, `makemigrations --check` y `migrate --plan` sin pendientes en esa
  instancia. La suite ampliada de asistencia detecta dos problemas fuera de
  este cambio en `tests_dashboard`: calendario administrativo y generacion
  demo de justificativos sin tipos activos.
- La suite general del entorno habitual ejecuta 816 pruebas con 5 fallos y
  4 errores fuera de este cambio (dashboard, notificaciones demo, permisos,
  configuracion, catalogos y candidaturas); no se considera validacion global
  satisfactoria. Ese entorno conserva pendiente `padron.0019`, que no se aplica
  como parte de esta correccion.

## Carga inicial en las tres instancias y foto solo bajo demanda

- `docker-compose.instancias.yml` ejecuta `iniciar_instancia_demo` en el
  servicio `web` de todas las instancias: en una base nueva aplica migraciones
  y la carga inicial de demostracion; en una base existente solo migra.
- `scripts/instancias.ps1` deja de restaurar la foto fija de PostgreSQL al
  levantar la instancia 2 (`up`). La foto `.instancias/foto-instancia-1.sql`
  se conserva y sigue aplicandose unicamente con la accion explicita
  `restaurar-foto -Instancia 2`.
- Se actualizan `scripts/tests_instancias.ps1` (prueban la restauracion
  explicita, su atomicidad y sus errores) y `README.md`. No se modifican
  modelos, migraciones ni la foto.

## Foto de instancia 2 sin turnos ni candidatos de autoridades de Estudiantes

- Se modifica unicamente `.instancias/foto-instancia-1.sql` (excluida de Git)
  para quitar, dentro de autoridades de mesa del claustro Estudiantes, los
  3 turnos configurados con sus maximos y minimos de titulares
  (`EleccionClaustroTurno`) y los 198 candidatos a autoridad cargados
  (`CandidaturaAutoridad`). Quedan 9 turnos y 232 candidatos de los demas
  claustros. No habia asignaciones de autoridad que dependieran de esas
  candidaturas porque las designaciones de Estudiantes ya se habian retirado.
- Se verifica en una base temporal que ninguna otra tabla ni secuencia cambie:
  los 500 registros del padron y las 19 mesas de Estudiantes se conservan. La
  exportacion se restaura en otra base temporal y se comprueba igualdad de las
  68 tablas y las 67 secuencias antes de reemplazar atomicamente la foto fija.
- Se actualiza `README.md`. No se cambian scripts ni modelos y no se crean
  migraciones. Las bases actuales de las instancias no se modifican; el ajuste
  se aplica al inicializar una base vacia de la instancia 2 o al ejecutar
  `restaurar-foto -Instancia 2`, que reemplaza todos los datos de esa
  instancia.

## Historial de padrones y motivos de la foto

- Se eliminan de la foto las siete entradas del historial de importaciones
  de padrón y sus 15 errores asociados, sin eliminar los 2100 registros
  importados. Las bases activas no se modifican.
- En la foto y en `seed_demo_inicial`, «Otro» reemplaza a «Problemas de
  transporte» en el catálogo inicial. En bases existentes, el comando conserva
  los tipos previos y no elimina datos históricos.
- Se validó la restauración de la foto comparando sus 68 tablas y 67
  secuencias; cinco pruebas enfocadas pasan y no hay migraciones pendientes.
  La suite completa de 784 pruebas conserva cuatro fallos y tres errores
  preexistentes, ajenos a este cambio.

## Catálogo de justificativos y limpieza de la foto para instancia 2

- `seed_demo_inicial` carga de forma idempotente cuatro motivos nuevos:
  «Enfermedad o accidente», «Obligaciones laborales»,
  «Problemas de transporte» y «Cuidado de familiar», además de
  «Certificado medico».
- La foto `.instancias/foto-instancia-1.sql` contiene los cinco tipos y no
  conserva filas del historial de archivos de nóminas (`ImportacionNominaAutoridades`).
  Solo se quitan las filas de ese historial; no se modifican candidaturas,
  electores ni designaciones de autoridad.
- La prueba de inicialización valida los cinco nombres luego de ejecutar el
  script dos veces. La foto se edita y valida en bases temporales antes del
  reemplazo; las instancias activas no se modifican.

## Emision de QR sin exigir plazo de cambios de sede cerrado

- `VotoUTN/apps/padron/services.py`: se elimina la validacion que exigia que
  el plazo de cambios de sede estuviera vencido antes de emitir QR y el padron
  imprimible. Se conserva el bloqueo por solicitudes de cambio de sede
  pendientes. La funcion pasa a llamarse
  `validar_emision_sin_solicitudes_cambio_sede_pendientes` y se actualizan sus
  consumidores (`apps/reportes/views.py` y el comando `seed_voters`).
- `VotoUTN/apps/padron/tests.py` y `VotoUTN/apps/reportes/tests.py`: las
  pruebas verifican que la emision procede con plazo abierto o sin plazo y que
  sigue bloqueada con solicitudes pendientes.
- `docs/decisiones_funcionales.md`: se actualiza la regla de emision de QR.
- No se requieren migraciones.

## Foto de instancia 2 sin autoridades de Estudiantes

- Se modifica unicamente `.instancias/foto-instancia-1.sql` (excluida de Git)
  para quitar las 171 designaciones de autoridades del claustro Estudiantes.
  Se conservan las 115 de Docentes, 81 de Graduados y 36 de No Docentes.
  No se modifican las bases actuales de ninguna instancia.
- Se verifica en una base temporal que ninguna otra fila ni secuencia cambie,
  incluidos electores, candidaturas y asignaciones de mesa. La exportacion
  se restaura en otra base temporal y se comprueba igualdad de las 68 tablas
  y las 67 secuencias antes de reemplazar atomicamente la foto fija.
- Se actualiza `README.md`. No se cambian scripts ni modelos y no se crean
  migraciones. El ajuste se aplica al inicializar una base vacia de la
  instancia 2 o al ejecutar explicitamente `restaurar-foto -Instancia 2`,
  que reemplaza todos los datos de esa instancia.

## Publicacion sin un plazo previamente guardado

- `VotoUTN/apps/elecciones/forms.py`: persiste el plazo ingresado antes de
  cambiar a Publicada y generar las solicitudes de demostracion. Ambas
  operaciones son atomicas: si falla la publicacion, tambien se revierte
  la fecha. No se omiten las validaciones del periodo de solicitudes.
- `VotoUTN/apps/elecciones/tests_solicitudes_publicacion.py`: reproduce la
  publicacion web con plazo previo vacio y comprueba estado, fecha, treinta
  solicitudes y lote de notificaciones, sin SMTP. Verifica ademas la
  sustitucion de un plazo anterior vencido y la reversion del plazo ante
  un error del generador.
- Verificacion: 47 pruebas de publicacion, generadores y notificaciones
  correctas. Correccion desplegada en las tres instancias; `check` correcto,
  sin cambios de modelos ni migraciones pendientes y HTTPS 200.
- No se crean ni eliminan archivos y no se requieren migraciones.

## Treinta estudiantes y notificaciones en segundo plano

- Publicar selecciona hasta treinta estudiantes sin ninguna designacion de
  autoridad en la eleccion, sin actividad ni QR y con destino alternativo
  compatible. Se excluye a Carlos y se conservan las solicitudes existentes.
  Si no hay treinta candidatos se crean los posibles sin informar faltantes.
- `notificaciones.0010` agrega lotes durables y datos de reintento, sin borrar
  notificaciones previas. Publicacion e inicio encolan un unico lote dentro
  de la transaccion del cambio de estado; su creacion masiva se ejecuta en el
  trabajador. Todas las operaciones dejan el correo en la cola de PostgreSQL.
- El trabajador prioriza al elector de la demo, bloquea filas para evitar
  procesamiento concurrente y reintenta fallos transitorios hasta tres veces.
  Ambos Compose incluyen el servicio `notificaciones`. Restaurar la foto
  detiene y reinicia tambien el trabajador.
- La interfaz distingue pendientes y errores de correos enviados. No se
  modifican retroactivamente solicitudes de elecciones publicadas ni se
  regeneran los avisos anteriores.
- Archivos: generador y comando de elecciones, selector de solicitudes del
  padron; modelos, servicios, vistas, comando y plantilla de notificaciones;
  productores de elecciones, autoridades, padron y justificativos; ajustes
  de correo, ambos Compose, script de instancias y pruebas relacionadas.
  Se crea `VotoUTN/apps/notificaciones/migrations/0010_cola_notificaciones.py`;
  no se eliminan archivos.
- Verificacion: 36 pruebas enfocadas correctas, incluida prioridad, reintentos
  y concurrencia. La corrida general de 780 pruebas detecto cuatro fallos y
  tres errores preexistentes, mas una expectativa de log de faltantes que se
  corrigio y verifico en la corrida enfocada. No se modifican los problemas
  previos de fechas, textos y tipos de justificativo.
- Migracion aplicada en las instancias 1, 2 y 3; verificaciones Django sin
  problemas, sin migraciones pendientes, trabajadores iniciados y HTTPS 200.
  Tambien se validaron ambos Compose y las pruebas del script de instancias.

## Solicitudes de publicacion con el padron de 500 registros principales

- Se reconoce explicitamente la variante actual del primer escenario, con DNI y
  legajos distintos del escenario generado y sin registros departamentales
  adicionales. El plan original se conserva y no se infieren identidades ni se
  eligen sustitutos aleatorios.
- `apps/padron/datos/solicitudes_demo_publicacion_sin_adicionales.json` contiene
  las diecinueve solicitudes de esa variante. Se reutilizan las validaciones
  existentes y se conservan las autoridades y las solicitudes ya resueltas.
- La publicacion y el comando `generar_solicitudes_cambio_sede_demo` reconocen
  ambos planes. En una eleccion ya publicada, el comando completa las faltantes
  sin volver a publicar ni reenviar las notificaciones de publicacion.
- No se modifican los CSV, la foto de PostgreSQL, modelos, migraciones ni el
  comportamiento sincronico de las notificaciones.

## Publicación con el escenario reproducible de diecinueve solicitudes

- Se reemplaza la generación aleatoria de setenta solicitudes al publicar por el lote fijo del primer escenario: diez originales y nueve adicionales, con los tres solicitantes compartidos por las nóminas de doce y de 198.
- `apps/padron/solicitudes_escenario.py` es el servicio compartido por la publicación, el comando Django y el guion externo. Conserva solicitudes resueltas y autoridades, crea únicamente las faltantes y valida plazo, QR, actividad y traslado conjunto.
- El plan se incluye en `apps/padron/datos/solicitudes_demo_publicacion.json`, disponible también dentro de Docker. El generador lo exporta con `--exportar-plan-publicacion`. Otros padrones se publican sin inventar solicitantes.
- Se actualizan pruebas, README y guiones. No se cambian modelos ni migraciones ni se resuelven automáticamente solicitudes o designaciones de la elección activa.

## Aprobación individual y confirmaciones de cambios de sede

- `apps/padron/views.py`: la aprobación individual aplica el servicio de
  resolución y recálculo en una transacción, notifica y vuelve al listado
  conservando el filtro. Las acciones masivas mantienen su revisión.
- Las tres plantillas base cargan `js/interfaz.js` con la misma URL sin
  parámetros que usan los imports ES6. Así se evita ejecutar dos instancias
  del módulo y abrir otra confirmación al aceptar la primera.
- `apps/padron/tests.py`: regresiones de aprobación directa, notificación
  única, permisos, bloqueo por QR, reversión ante error y URL de carga.

## Autoridades y plazos para demostraciones

- La Junta puede confirmar autoridades antes del vencimiento del plazo de cambios de sede si no quedan solicitudes pendientes. La confirmación cierra nuevas solicitudes y la interfaz lo informa.
- Publicar no exige turnos de autoridad provisorios; siguen siendo necesarios para iniciar la elección.
- Las confirmaciones de autoridades utilizan el modal interno de la aplicación; cancelar no envía los formularios y se conserva la acción elegida al confirmar.

Este documento registra cambios aplicados al proyecto. Describe los archivos y el efecto de cada cambio; no reemplaza el historial de Git ni las migraciones de Django.

## Exportación de infractores alineada con el registro de ausencias

- `exportar_reporte_eleccion` (`apps/reportes/services.py`) filtraba electores
  de mesas procesadas **sin** `RegistroParticipacion`, criterio anterior a la
  regla vigente: un registro de participación representa una ausencia (QR del
  troquel escaneado o carga manual). El CSV listaba a quienes votaron.
- Ahora exporta a los electores con ausencia registrada que no tienen un
  justificativo aprobado de «Ausencia a votar», el mismo criterio del
  historial electoral. Un justificativo aprobado como autoridad de mesa no
  excluye la infracción como elector. Sin cambios de esquema ni de vistas.
- Pruebas: `ExportarInfractoresTests` en `apps/reportes/tests.py` (votante,
  ausente, justificado, rechazado, justificado solo como autoridad, y bloqueo
  si la elección no está finalizada).
- Documentación: [guion_demostracion.md](guion_demostracion.md), guion de la
  demostración de 20 minutos.
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

## Registro manual de mesas desde el tablero

Fecha de implementación: 2026-11-05

- La tabla de mesas del tablero de participación (escritorio) agrega la columna «Registro» con el botón «Registrar» para cada mesa no procesada.
- El botón abre un diálogo con la cantidad de electores y de inasistencias cargadas; al confirmar, el servidor valida permisos y estado y deja la mesa procesada (pasando por En proceso si estaba pendiente). Se audita con `origen: manual`.
- La carga manual de una inasistencia por DNI pasa la mesa de Pendiente a En proceso dentro de la misma transacción.
- La carátula de mesa muestra el claustro encima de «Información de mesa».
- En «Solicitudes de cambio de sede», aplicar el filtro de estado conserva la posición de desplazamiento.
- Se agregaron pruebas en `apps/asistencia/tests_procesamiento_manual.py`.
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

## 2026-11-08 — Padrón con departamentos adicionales y mesas especiales

- La importación admite varias filas de una persona, una por departamento, exige la fila principal y valida los datos comunes. Los datos académicos pueden variar; una fila única sin principal explícito conserva compatibilidad.
- El modelo conserva una identidad de elector, un registro por elección y alcance y como máximo un registro principal. Los registros históricos permanecen principales. Cada registro conserva un QR independiente.
- El cálculo y recálculo separan mesas ordinarias y especiales por claustro, departamento y sede. Los adicionales heredan la sede del principal y pueden usarla aunque no esté habilitada para mesas ordinarias de su departamento.
- Las solicitudes, los traslados de autoridades con y sin reacomodo y los retornos preparan movimientos conjuntos, con protección de solicitudes, QR, capacidad y autoridades existentes. Las propuestas incluyen los nuevos campos en su huella de revalidación.
- La nómina identifica personas con varios registros sin duplicar designaciones. Los conteos de importación, nómina y preparación de elecciones distinguen personas de registros. El inicio del elector muestra ambas clases de mesa y su situación por registro.
- La emisión de QR y del padrón imprimible exige plazo de cambio de sede vencido y solicitudes resueltas. La carga manual identifica el registro por DNI y mesa.

Archivos creados:

- `VotoUTN/apps/mesas/migrations/0005_mesa_es_especial.py`.
- `VotoUTN/apps/padron/migrations/0014_registropadron_es_principal.py` y `0015_registros_por_departamento.py`.
- `VotoUTN/apps/padron/tests_departamentos_multiples.py` y `tests_sedes_compartidas.py`.
- `VotoUTN/apps/autoridades/tests_unicidad_personas.py`.

Archivos modificados por componente:

- `asistencia`: servicio de carga manual y descripción de mesas; pruebas de procesamiento manual.
- `padron`: modelos, servicios, recálculo provisorio, vistas, comando `seed_voters`, pruebas y plantillas de importación.
- `mesas`: modelo, pruebas y plantilla de gestión.
- `autoridades`: modelos, servicios, distribución, nómina, reordenamiento, retorno, vistas y pruebas correspondientes.
- `partidos`: búsqueda y validación del elector por alcance, con pruebas.
- `elecciones`: vistas, historial por registro, pruebas de ciclo y comandos de datos demo; plantilla de inicio del elector.
- `usuarios`: comando `seed_keycloak_demo` para seleccionar el registro principal.
- `justificativos`: selección del registro de designación al presentar ausencia de autoridad; la política de inasistencias electorales se completa en la sección siguiente.
- `reportes`: emisión web y PDF, con sus pruebas.
- `docs/decisiones_funcionales.md` y `docs/modelo_dominio.md`.

No se eliminan archivos. Las migraciones se prueban en PostgreSQL aislado; la base habitual conserva migraciones anteriores pendientes. La eventual exclusión de cargos generales en registros adicionales requiere confirmación funcional.

Se aplicaron también a la base habitual, de forma dirigida, `mesas.0005`,
`padron.0014` y `padron.0015`; las tres finalizaron correctamente y el chequeo
posterior no informó incidencias. Las migraciones anteriores de otras apps
permanecen pendientes y no formaron parte de esta aplicación dirigida.

Verificación final de esta entrega: `manage.py check` sin incidencias,
`makemigrations --check` sin cambios detectados, `migrate --plan` revisado y
635 pruebas aprobadas en una base PostgreSQL nueva y aislada. La integración
incluye registros reales K/I, reimportación idempotente, QR y participación
independiente, conteos por persona, inicio del elector, nómina, solicitud de
cambio de sede, traslados por autoridad y retornos con y sin reordenamiento.

## 2026-11-08 — Un justificativo para todas las ausencias de la persona

La regla confirmada permite presentar una sola justificación de ausencia a votar
por elección. Su resolución se refleja en todos los registros activos de la
persona marcados como ausentes, incluidos los de mesas especiales y las ausencias
registradas posteriormente. No se duplican documentos ni resoluciones. Quienes
votaron en otra de sus mesas conservan ese estado.

Archivos creados:

- `VotoUTN/apps/justificativos/tests_departamentos_multiples.py`.
- `VotoUTN/templates/justificativos/_alcance.html`.

Archivos modificados:

- `VotoUTN/apps/justificativos/{models,services,forms,views}.py`: cobertura por persona/elección, presentación desde una mesa especial y revalidación transaccional contra solicitudes duplicadas.
- `VotoUTN/apps/elecciones/historial_electores.py`, `VotoUTN/apps/asistencia/dashboard.py` y `VotoUTN/apps/reportes/services.py`: estados e indicadores compartidos y exclusión de todas las ausencias justificadas en el reporte de infractores.
- `VotoUTN/templates/justificativos/{mis_justificativos,resolver,detalle_elector}.html`: explicación y consulta de las mesas cubiertas.
- `VotoUTN/templates/elecciones/_dashboard_participacion.html`: los indicadores explican cuántas ausencias cubren las solicitudes, sin presentarlas como documentos duplicados.
- `docs/{decisiones_funcionales,modelo_dominio,plan_implementacion,registro_de_cambios}.md`.

Sin archivos eliminados ni cambios de esquema. Las ausencias de autoridades y
los reclamos «Voté, pero aparezco como ausente» conservan su alcance específico;
un comprobante no anula ausencias de otras mesas.

Verificación: 646 pruebas aprobadas en PostgreSQL aislado, incluidas 11 nuevas
pruebas de cobertura departamental. `manage.py check` sin incidencias,
`makemigrations --check` sin cambios detectados y `git diff --check` sin errores.
`migrate --plan` conserva pendientes las migraciones previas `elecciones.0030`,
`elecciones.0034` y `justificativos.0003` a `0008`; no se aplicaron en esta tarea.
La habilitación en la base habitual requiere resolver esas migraciones anteriores.

## 2026-11-08 — Cierre de pendientes del padrón departamental

- El cálculo separado de padrones de votación limita los cargos generales al registro principal. Los registros adicionales reciben los cargos de su departamento. El control de duplicados se realiza por persona y una configuración inválida conserva las asignaciones anteriores.
- Publicación, inicio y aviso de ausencia crean un solo envío por persona. El aviso de inicio enumera todas sus mesas y sedes electorales; el de ausencia enumera únicamente las mesas donde figura ausente. Las pruebas de correo usan el backend de pruebas o un envío simulado.
- El reclamo de participación permite elegir la mesa cuando hay varias ausencias, rechaza registros ajenos, usados o sin ausencia y revalida al guardar. Un QR del principal no acredita el voto en una mesa especial. La aprobación conserva las ausencias de las otras mesas y la revisión identifica el registro reclamado.
- Se instaló `zxing-cpp==3.1.1` en el entorno normal del contenedor `votoutn62-web-1`. Ya figuraba en `requirements.txt` y el Dockerfile lo incorpora al reconstruir la imagen; la ejecución habitual dejó de depender de `PYTHONPATH` temporal.
- Se creó un respaldo PostgreSQL previo en `votoutn62-db-1:/tmp/votoutn-antes-cierre-padron-20261108.dump` y se aplicaron las ocho migraciones anteriores de elecciones y justificativos. La conversión del tipo reservado «Sí voté» conserva sus solicitudes mediante la casilla de reclamo; en esta base no había ese tipo reservado. Se comprobaron antes y después los 545 registros de padrón y los 4 justificativos.

Archivos modificados en este cierre:

- `VotoUTN/apps/padron/services.py` y `tests_departamentos_multiples.py`.
- `VotoUTN/apps/notificaciones/services.py`.
- `VotoUTN/apps/justificativos/forms.py`, `views.py` y `tests_departamentos_multiples.py`.
- `VotoUTN/static/js/mis-justificativos.js`.
- `VotoUTN/templates/justificativos/_alcance.html` y `mis_justificativos.html`.
- `docs/decisiones_funcionales.md`, `modelo_dominio.md`, `plan_implementacion.md` y este registro.

No se crean migraciones nuevas ni se eliminan archivos en este cierre.

Verificación:

- 122 pruebas dirigidas y 658 pruebas de la suite completa aprobadas en PostgreSQL aislado, ejecutadas con el entorno normal del contenedor.
- `manage.py check` sin incidencias; `makemigrations --check` sin cambios; `migrate --plan` sin operaciones pendientes en la base habitual.
- `node --check` y `git diff --check` sin errores.
- Chromium: cinco pantallas renderizadas por Django con datos ficticios, revisadas a 1440 y 390 píxeles de ancho. Selector condicional de mesa, campos obligatorios y diálogo de confirmación comprobados; sin errores JavaScript ni desbordes horizontales del documento. Los POST, permisos, validación del QR y resoluciones se verifican en las pruebas de Django.
- Las capturas y el informe de navegador quedan en la carpeta temporal `votoutn-padron-browser`; la transacción utilizada para renderizar las pantallas fue revertida y no agregó datos de demostración a la base habitual.
- Se reinició únicamente el contenedor web para renovar el proceso que había fallado al importar la dependencia antes de su instalación. Se verificó HTTP 200 en el JavaScript servido por la aplicación habitual y la presencia del selector actualizado.


## 2026-11-09 — Indicador durante todo el procesamiento

Los envíos de formularios ya no ocultan el indicador ni liberan el reenvío al
cumplir 90 segundos. La carga se mantiene hasta que la página de respuesta
reemplaza la actual; al navegar o volver desde el historial se restablece el
estado. Los cierres explícitos de fetch y HTMX, las descargas y los destinos
en otra ventana conservan su comportamiento.

Archivos modificados:

- `VotoUTN/static/js/interfaz.js`: elimina el vencimiento y conserva el bloqueo del mismo formulario mientras su envío está pendiente.
- `VotoUTN/templates/base.html`, `templates/gestion/base.html` y `templates/elecciones/base_publica.html`: actualizan la versión del JavaScript.
- `docs/contexto_continuidad_padrones.md`: actualiza P3 y registra la aclaración sobre autoridades por tipo de registro. La corrección de elegibilidad de P1 continúa pendiente.
- Este registro de cambios.

No se crean ni eliminan archivos de la aplicación, no se requieren migraciones
y no se modifican los datos ni las asignaciones de la elección habitual.

Verificación:

- Chromium aislado: el código anterior falla al simular una espera de diez minutos; el actualizado conserva el indicador y el bloqueo de reenvío. También se comprueban navegación, historial, solicitudes simultáneas, eventos de respuesta/error/timeout de HTMX, exclusiones y cancelación de confirmaciones. Se simulan eventos y respuestas; no se importa una nómina real.
- Suite completa: 658 pruebas aprobadas en PostgreSQL separado (`test_indicador_20261109_c6e29`), con almacenamiento temporal para archivos de prueba.
- `manage.py check` sin incidencias; `makemigrations --check` sin cambios y `migrate --plan` sin operaciones pendientes.
- `node --check` y `git diff --check` sin errores. La aplicación activa devuelve HTTP 200 y sirve el JavaScript actualizado sin reiniciarla.


## 2026-11-09 — Eliminar candidaturas junto con las asignaciones

La acción «Eliminar todas las asignaciones» también retira todas las candidaturas
de autoridad del claustro, incluidas las excluidas y sus selecciones y destinos
fijados. Funciona cuando ya no hay designaciones, para que esas candidaturas
residuales no sigan bloqueando el vaciado del padrón. La confirmación explica el
alcance y el resultado informa que la nómina de posibles autoridades quedó vacía.

La operación mantiene sus permisos, CSRF, confirmación explícita, bloqueos por
estado, QR y avisos de ausencia, atomicidad y alcance por claustro. Conserva
personas, padrón, mesas, configuración de modo, turnos, cupos e historial de
importaciones. La auditoría conserva cantidad y datos de las candidaturas
retiradas además de las asignaciones. Se descartan las propuestas y comparaciones
pendientes de la sesión.

Archivos modificados:

- `VotoUTN/apps/autoridades/distribucion.py`: elimina candidaturas después de sus asignaciones y amplía la auditoría.
- `VotoUTN/apps/autoridades/views.py`: descarta las comparaciones de sesión y actualiza los mensajes de confirmación y resultado.
- `VotoUTN/apps/autoridades/tests_eliminar_asignaciones.py`: actualiza la regla y agrega regresiones para candidaturas sin designaciones y limpieza de propuestas.
- `VotoUTN/templates/autoridades/gestion_claustro.html`: informa en el diálogo que también se eliminan candidaturas, incluidas las excluidas.
- `docs/decisiones_funcionales.md`, `docs/autoridades_modalidades.md`, `docs/contexto_continuidad_padrones.md` y este registro.

No se crean ni eliminan archivos de la aplicación y no se requieren migraciones.
El cambio de código no ejecuta el botón ni elimina las 675 candidaturas de la
elección habitual; su ejecución queda a cargo del usuario desde la pantalla.

Verificación:

- La regresión reprodujo seis fallos con el comportamiento anterior; después de la corrección pasaron las diez pruebas dirigidas.
- La integración verifica que, tras quitar candidaturas sin designaciones, se conservan padrón y mesas y luego se puede vaciar el padrón por el servicio existente.
- Se comprueban conservación de otros claustros, permisos, CSRF, confirmación, bloqueos, auditoría, reversión completa ante fallos y sorteo posterior.
- Suite completa: 660 pruebas aprobadas en 187,218 segundos, PostgreSQL aislado (`test_eliminar_candidaturas_20261109`) y archivos de prueba temporales.
- `manage.py check` sin incidencias; `makemigrations --check` sin cambios; `migrate --plan` sin operaciones pendientes; `git diff --check` sin errores.


## 2026-11-09 — Vaciar padrón conservando identidades con notificaciones

Se corrigió el `ProtectedError` del vaciado: la selección de identidades
huérfanas no contemplaba `EnvioNotificacion.elector`, una relación `PROTECT`.
Se conservan las identidades con notificaciones y todos sus avisos, aunque el
envío haya fallado o no tenga una elección asociada. El padrón puede vaciarse
sin borrar ese historial, y las identidades realmente huérfanas siguen
eliminándose. El resumen previo cuenta las mismas referencias que la limpieza.

Archivos modificados:

- `VotoUTN/apps/padron/services.py`: incluye las notificaciones al contar identidades conservadas y excluye sus destinatarios de la eliminación de huérfanos.
- `VotoUTN/apps/padron/tests.py`: agrega regresiones del resumen, el servicio y la confirmación/POST web con notificaciones, y verifica que solo se liberen identidades huérfanas.
- `VotoUTN/templates/padron/confirmar_eliminar_padron.html`: explica que las identidades con notificaciones y sus avisos se conservan.
- `docs/decisiones_funcionales.md`, `docs/contexto_continuidad_padrones.md` y este registro.

No se crean ni eliminan archivos de la aplicación y no se requieren migraciones.
Se verificaron los 20.000 registros, sus 20.000 asignaciones y las 75 mesas
después del intento fallido: la transacción se había revertido completa. Había
3.578 identidades con avisos, conservadas por el resumen corregido; las otras
14.922 podían liberarse. La tarea no ejecutó el vaciado en la base habitual.

Verificación:

- Antes de corregir, las regresiones reprodujeron dos fallos de conteos y el mismo `ProtectedError` de `EnvioNotificacion.elector` informado por el usuario.
- Después de corregir, nueve pruebas dirigidas aprobadas, incluidos los tres casos nuevos y la confirmación seguida del POST de vaciado.
- Las notificaciones conservan todos sus campos y el vínculo con la identidad; la auditoría cuenta correctamente las identidades conservadas y eliminadas.
- Suite completa: 663 pruebas aprobadas en PostgreSQL aislado (`test_vaciado_notificaciones_20261109`) y archivos temporales.
- `manage.py check` sin incidencias; `makemigrations --check` sin cambios; `migrate --plan` sin operaciones pendientes; `git diff --check` sin errores.
- Aplicación activa con HTTP 200 y resumen corregido, sin vaciar el padrón ni borrar avisos de la base habitual.


## 2026-11-09 — Autoridades compatibles con el tipo de mesa y sede compartida

Se corrigió la elegibilidad de autoridades para impedir que un registro de mesa
ordinaria se proponga para una especial o al revés. El control se aplica antes
de aceptar destinos fijados, también sin reordenar el padrón, y al conservar
asignaciones previas. Una designación incompatible que ya exista se informa
para revisión; no se elimina automáticamente. Se conserva la validación del
reordenador.

La persona aporta el registro compatible con su destino, con una sola
designación por identidad. Se verificó que un cambio de sede electoral de la
autoridad traslada juntos su principal y todos sus adicionales a esa sede,
conservando tipo, departamento, identidad, datos de cursada e identificadores
QR. Se probó designar desde el principal y desde un adicional, con y sin
reordenamiento, usando tres registros de la misma persona.

Archivos creados en esta subetapa:

- `VotoUTN/apps/autoridades/tests_elegibilidad_tipos_mesa.py`.

Archivos modificados:

- `VotoUTN/apps/autoridades/distribucion.py`: comparte el control de tipo entre elegibilidad general, de nómina y conservación de asignaciones.
- `docs/decisiones_funcionales.md`, `docs/contexto_continuidad_padrones.md` y este registro.
- `PRUEBA_20000_ALUMNOS/LEEME_nomina_300_padron_2000.md`: reemplaza el aviso del error pendiente por los resultados de las cinco alternativas ya verificadas.

En la preparación de la nómina se crearon
`PRUEBA_20000_ALUMNOS/nomina_autoridades_300_padron_2000.csv` y
`control_nomina_300_padron_2000.csv`: 300 personas distintas del padrón de 2.000,
incluidas 90 con principal y adicional. No se eliminan archivos ni se requieren
migraciones. No se cargó ni confirmó la nómina en la elección habitual.

Verificación:

- Las regresiones reprodujeron ambos reordenamientos inválidos y los filtros que omitían el tipo; después de corregir pasaron las ocho pruebas nuevas.
- Suite completa: 671 pruebas aprobadas en 259,874 segundos en PostgreSQL aislado (`test_tipos_mesa_20261109`).
- `check` sin incidencias; `makemigrations --check` sin cambios; `migrate --plan` sin operaciones pendientes; `git diff --check` sin errores.
- En otra base aislada (`test_nomina_300_tipos_20261109`), una réplica ficticia de 2.000 registros y 75 mesas recorrió las cinco alternativas sin errores y confirmó cambio de sede con reordenamiento. Quedaron 300 autoridades distintas, tipos compatibles, una sede por persona y ninguna mesa con más de 30 registros. Los datos de la prueba se revirtieron.
- La confirmación conservó los 2.000 registros. Los resultados comparativos están en el LEEME de la nómina.
- Persisten las demoras de otra sede sin reordenar: 331,416 segundos en ese ensayo. Las otras alternativas demoraron 8,268; 10,855; 39,990 y 30,329 segundos. Son referencias de un ensayo parcialmente concurrente con la suite en otra base, no garantías ni una optimización aplicada.
- El ensayo integral de 20.000 filas y las mejoras de rendimiento siguen pendientes como subetapas separadas.


## 2026-11-15 — Plantilla de padrón con ejemplos y definiciones

Se reemplazan los ejemplos desalineados de la plantilla CSV por cuatro registros
de tres personas, incluido un departamento adicional para mesa especial. La
plantilla usa Sede donde asiste, omite discapacidad e incluye Turno y la
definición acordada de Nivel para estudiantes y docentes. Agrega una fila vacía
y una guía por columna con la marca ESTA FILA DEBE ELIMINARSE.

La lectura de CSV y Excel admite la columna auxiliar Instrucciones únicamente
vacía. Si persiste la guía, exige eliminarla con un error de archivo explícito;
las filas separadoras vacías no se incorporan como electores. Se conservan los
formatos históricos y el rechazo de otras columnas desconocidas.

Archivos modificados: `VotoUTN/apps/padron/services.py`,
`VotoUTN/apps/padron/views.py`, `VotoUTN/apps/padron/tests.py`,
`VotoUTN/templates/padron/cargar.html`, `docs/decisiones_funcionales.md` y este
registro. Se crea `VotoUTN/apps/padron/tests_plantilla.py`. No se eliminan
archivos ni se modifica el esquema de la base de datos.

Verificación:

- 42 pruebas dirigidas aprobadas en PostgreSQL, incluidas cinco regresiones nuevas de CSV/Excel, guía sin eliminar, columna auxiliar, compatibilidad e importación con mesa especial.
- La suite completa ejecutó 780 pruebas en 233,390 segundos: 772 aprobadas y los mismos cinco fallos y tres errores anteriores de develop en fechas, interfaz de elecciones y generación de justificativos demo. No se modifican esos flujos en esta subetapa.
- `python manage.py check` sin incidencias; `python manage.py makemigrations --check` sin cambios; `git diff --check` sin errores.
- `python manage.py migrate --plan` identifica las doce migraciones de develop que ya estaban pendientes en la base habitual. No se aplican a esa base; esta subetapa no genera migraciones.
- El CSV `ESCENARIOS_PRUEBA_ELECTORAL/segmento_1_500/padron_estudiantes.csv` conserva sus encabezados y sus 600 registros de 500 personas. Su reducción a 500 registros sigue pendiente como otra subetapa.
- Los cambios de plantilla están aplicados; la validación general del proyecto no se considera cerrada por los fallos previos y las migraciones pendientes.


## 2026-11-15 — Retiro de la columna Instrucciones

Se retira únicamente la columna auxiliar de la plantilla descargable y su
aviso, conservando las once columnas de datos, los cuatro registros de ejemplo,
la separación y las descripciones. La ayuda de carga explica que el archivo se
prepara reemplazando esos contenidos por los datos del padrón. Los archivos
anteriores con Instrucciones vacía conservan compatibilidad.

Se modifican `VotoUTN/apps/padron/services.py`, `views.py`, `tests.py`,
`tests_plantilla.py`, `VotoUTN/templates/padron/cargar.html`,
`docs/decisiones_funcionales.md` y este registro. No se crean ni eliminan
archivos del proyecto ni se generan migraciones.

Verificación del retiro:

- 42 pruebas dirigidas aprobadas en 15,525 segundos, incluida la descarga con once columnas y la importación CSV/Excel de los ejemplos y de archivos anteriores.
- `check` sin incidencias, `makemigrations --check` sin cambios y `git diff --check` sin errores.
- `migrate --plan` conserva las doce migraciones anteriores pendientes en la base habitual; no se aplican en esta tarea.
- La suite con `--keepdb --noinput --failfast` detectó 780 casos y se detuvo tras 31 pruebas por el error previo de tipos de justificativo demo al notificar ausentes. La validación general sigue pendiente; los resultados completos anteriores se conservan arriba.
- No se modifican los CSV ni las capacidades de los escenarios de ejemplo. La consulta de su configuración confirma Estudiantes 60 y Docentes, Graduados y No docentes 200 por mesa. La elección habitual segmento1 solo tiene Estudiantes configurado, con máximo 60.


## 2026-11-16 — Padrón de estudiantes de ejemplo con 500 registros principales

Se retiran las cien filas de departamentos adicionales de
`ESCENARIOS_PRUEBA_ELECTORAL/segmento_1_500/padron_estudiantes.csv`.
Se conservan las mismas quinientas personas, el orden, los encabezados, la
codificación y cada valor de sus registros principales, incluido Carlos.
El archivo queda con quinientas filas de datos y sin registros de mesa especial.

Solo se modifican ese CSV y este registro. No se crean ni eliminan archivos del
proyecto, no se importan datos en la base habitual y no se modifican nóminas,
otros claustros, segmentos ni código de la aplicación.

Antes de editar ya se comprobó que las diez huellas de CSV del control del
primer segmento no coinciden con los archivos actuales de develop. El control
y el generador conservan la versión anterior de las identidades y cantidades;
su reconciliación queda fuera de este ajuste del archivo. Regenerar los
escenarios con esa configuración volvería a producir cien adicionales para
estudiantes. Tampoco se valida en esta tarea el guion anterior de diecinueve
solicitudes, que incluía movimientos de registros de mesas especiales.

Verificación del archivo de 500:

- Comparación exacta: cien filas eliminadas, ninguna agregada; los quinientos registros conservados son idénticos a los principales originales, incluyendo orden, encabezados, DNI, legajos y restantes campos. Los nueve CSV restantes del segmento conservan sus huellas.
- Importación del archivo real en una transacción de la base de pruebas PostgreSQL: quinientas personas, quinientos registros principales y quinientas asignaciones de mesa; ninguna mesa especial ni mesa con más de sesenta electores. Prueba aprobada en 14,396 segundos, con archivos temporales y reversión de los datos de prueba.
- Después de guardar, el archivo vuelve a contar quinientos registros, quinientos DNI únicos y cero departamentos adicionales.
- `python manage.py check` sin incidencias; `python manage.py makemigrations --check` sin cambios; `git diff --check` sin errores.
- `python manage.py migrate --plan` conserva las doce migraciones previas pendientes. La suite con `--keepdb --noinput --failfast` se detuvo tras 31 pruebas por el error previo de tipos de justificativo demo; la validación general del proyecto sigue pendiente.


## 2026-11-16 — Retiro de mensajes debajo de Guardar configuración

Se elimina el área de estado del autoguardado dentro del recuadro de
configuración del padrón y todas las escrituras de mensajes sobre ella. El
script deja de depender de ese elemento y de mostrar allí la respuesta de
recalcular mesas. Se actualiza su versión en la plantilla para evitar que un
script anterior busque el elemento retirado.

Se conserva el botón Guardar configuración, el envío automático y manual, los
controles de cambios concurrentes, la validación, el indicador general de carga
y el aviso de salida cuando no se pudieron guardar los cambios. No se modifica
el endpoint, los permisos, los modelos ni la base habitual.

Archivos modificados: `VotoUTN/static/js/configuracion-padron-autoguardado.js`,
`VotoUTN/templates/padron/cargar.html`, `VotoUTN/apps/padron/tests.py`,
`docs/decisiones_funcionales.md` y este registro. No se crean ni eliminan
archivos del proyecto y no se requieren migraciones nuevas.

Verificación de mensajes del autoguardado:

- Las 33 pruebas de `apps.padron.tests.PadronViewsTests` aprobaron en 14,070 segundos: la pantalla conserva fecha, máximo, botón y atributos de autoguardado, sin área de mensajes de estado; el endpoint sigue persistiendo los cambios automáticos y manuales.
- `node --check` sin errores. Ejercicio de ejecución del JavaScript sin elemento de estado: guardado exitoso y fallo de conexión, POST con los indicadores esperados, limpieza del temporizador al usar el botón manual y confirmación de salida si no se pudo guardar. Los casos aprobaron sin intentar escribir mensajes en el DOM.
- `python manage.py check` sin incidencias; `python manage.py makemigrations --check` sin cambios; `git diff --check` sin errores.
- `python manage.py migrate --plan` conserva las doce migraciones anteriores pendientes de develop en la base habitual; esta tarea no las aplica ni agrega migraciones.
- La verificación general del proyecto sigue pendiente por las incidencias previas documentadas; esta entrega ejecuta las pruebas del flujo afectado, sin modificar esos otros flujos.


## 2026-11-16 — Conservar posición en acciones de la misma pantalla

La interfaz compartida conserva la posición al volver a la misma ruta después
de formularios, filtros, paginación o navegación por JavaScript. La captura se
realiza en pagehide y deja de depender de atributos en formularios concretos,
por lo que alcanza a agregar, eliminar y reordenar reglas de sede. Los cambios
de pantalla y las anclas explícitas conservan su comportamiento habitual.

Se protege la lectura y escritura del almacenamiento de sesión para que un
bloqueo o dato corrupto no interrumpa los diálogos. Se preserva la URL única del
módulo compartido y sus importaciones para evitar duplicar la interfaz.

Se modifica `VotoUTN/static/js/interfaz.js`, `docs/decisiones_funcionales.md`
y este registro. Se crea `VotoUTN/pruebas_js/conservar-posicion.test.cjs` con
pruebas de navegación del módulo real. No se eliminan archivos ni se modifican
modelos, endpoints, migraciones o datos de la base habitual.

Verificación de posición conservada:

- Las pruebas reprodujeron seis fallos con el módulo anterior, incluidos los POST no marcados, filtros, posición horizontal y almacenamiento bloqueado. Con el módulo corregido aprobaron los diez casos de navegación, cambio de ruta, anclas, cancelación sin navegación, datos corruptos y compatibilidad.
- `node --test VotoUTN/pruebas_js/conservar-posicion.test.cjs`: diez pruebas aprobadas. `node --check VotoUTN/static/js/interfaz.js`: sin errores de sintaxis. Son pruebas del módulo real en contextos de página simulados, no una ejecución de navegador gráfico.
- `python manage.py test apps.padron.tests.AsignacionSedesClaustroTests apps.padron.tests.SolicitudCambioSedeTests --keepdb --noinput`: 33 pruebas aprobadas en 6,539 segundos. Incluyen reglas, operaciones y conservación de filtros, y que las plantillas base y los imports comparten la misma URL del módulo de diálogos.
- `python manage.py check` sin incidencias; `python manage.py makemigrations --check` sin cambios; `git diff --check` sin errores.
- `python manage.py migrate --plan` conserva las doce migraciones anteriores pendientes de develop; no se aplican ni se agregan migraciones en esta tarea. La validación general mantiene pendientes las incidencias previas documentadas.


## 2026-11-16 — Actualización segura de la base recuperada para probar configuración

El inicio de junta fallaba porque faltaba
`elecciones_eleccion.solicitudes_cambio_sede_habilitadas_en`. La base habitual
conservaba doce migraciones pendientes de develop. Sobre una copia restaurada
se reprodujo además el fallo de `padron.0012_identidad_electoral_por_eleccion`:
intentaba crear unicidad global por elección antes de llegar a la restricción
parcial para los registros principales, incompatible con los cien adicionales.

Se recupera del trabajo previo la migración de reemplazo
`VotoUTN/apps/padron/migrations/0018_identidad_electoral_multidepartamental_segura.py`.
No se modifican ni eliminan migraciones históricas ni se simula su aplicación.
La nueva ruta parte de registros por departamento, copia DNI y legajo del mismo
elector y crea directamente las restricciones parciales sobre principales.
Django conserva las rutas históricas en instalaciones con aplicación parcial.

Se crea `VotoUTN/apps/padron/tests_migracion_identidad.py` con regresiones de
actualización desde una base con principales y adicionales: preservación de
identidad y QR, y rechazo de otra persona principal con el mismo DNI o legajo.
Solo se modifica este registro, además de esos dos archivos nuevos.

Antes de la actualización se creó un pg_dump completo, restaurado en
`ensayo_reparacion_voto_20261116`, y una copia local fuera del repositorio:
`C:/Users/domin/AppData/Local/Temp/voto_utn_reparacion_20261116/respaldo_antes_migraciones.dump`.
La copia coincidió por cantidad y SHA-256 del contenido con diez tablas de
dominio. La elección 4, segmento1, ya estaba en En preparación por solicitud
expresa, auditada en el evento 378. Se preservan los datos de la base habitual;
el CSV de quinientas filas no se importa en esta tarea.

Verificación de reparación de migraciones:

- Respaldo completo restaurado y coincidente con diez tablas de dominio. Se reprodujo en el ensayo la violación de unicidad de la ruta antigua y luego se migró sin errores con la ruta de reemplazo.
- Tres regresiones de migración aprobadas en 69,919 segundos. Verifican datos y QR sin cambios, DNI compartido con adicionales y rechazo de otro principal por DNI o legajo.
- La base habitual se actualizó después del ensayo. Comparación de diez tablas: contenido previo idéntico, excluyendo solamente las columnas nuevas. Se conservan 505 electores, 600 registros, 22 mesas, 600 asignaciones, 198 autoridades, 208 candidaturas de autoridad y 19 solicitudes.
- Inicio de junta, configuración de elección, padrón y reglas de sede responden HTTP 200 con autenticación local verificada en una transacción revertida. La elección 4 sigue En preparación. Reparación auditada en el evento 379.
- `check` sin incidencias; `makemigrations --check` sin cambios; `migrate --plan` sin operaciones pendientes.
- Suite completa: 783 pruebas en 346,928 segundos; 776 aprobadas, cuatro fallos y tres errores de los flujos anteriores de fechas y notificadores demo. Las tres pruebas nuevas de migración aprobaron. La validación general sigue pendiente por esas incidencias, no por migraciones pendientes.



## 2026-11-16 — Reglas de sede atómicas ante un registro adicional protegido

Al eliminar la regla de nivel hasta tercero, el recálculo rechazó una sede
protegida incompatible con su principal. La vista borraba antes la regla y
dejaba sus referencias a NULL, y luego mostraba error 500. Se reproduce con
principales y adicionales compartiendo sede y autoridad en el adicional.

Los POST de agregar, eliminar y reordenar se ejecutan ahora en una sola
transacción, bloqueando primero la elección. Un ValueError del cálculo revierte
la operación completa y vuelve al listado con su motivo. Se conservan las
protecciones funcionales y los recálculos válidos.

Se modifica `VotoUTN/apps/padron/views.py`, `docs/decisiones_funcionales.md` y
este registro. Se crea `VotoUTN/apps/padron/tests_reglas_sede_atomicidad.py` con
tres regresiones reales de eliminación, reordenamiento y alta incompatibles.
No se modifica el modelo ni se requieren migraciones nuevas para esta corrección.

Recuperación y verificación de reglas atómicas:

- Las tres regresiones reprodujeron HTTP 500 al agregar, eliminar y reordenar con un adicional protegido. Después de corregir, los tres casos vuelven con aviso y conservan todos los datos, y las 36 pruebas de reglas y solicitudes aprobaron en 7,981 segundos.
- Se comprobó contra el respaldo que el intento fallido había eliminado la regla 8 y dejado 250 referencias a NULL, sin otros cambios en esas asignaciones. Antes de cualquier restauración, el usuario quitó las autoridades y reemplazó las reglas por interfaz; se respetan sus cambios posteriores y no se restaura la configuración del respaldo.
- El error de cálculo sigue rechazando una sede protegida incompatible, pero ya no deja un borrado parcial ni responde con error 500.



## 2026-11-16 — Carga versionada de la conservación de posición

El usuario seguía viendo saltos al agregar, ordenar y eliminar reglas. En
Chrome con el HTML real de la pantalla de ensayo y sus estáticos se reprodujeron
los tres saltos a cero al cargar el módulo antiguo, mientras que el módulo
actual conservaba la posición. Esto identifica la caché del módulo antiguo
como una causa compatible con lo observado, sin inspeccionar la sesión del usuario.

Se separa la conservación de posición en
`VotoUTN/static/js/conservar-posicion.js`, cargado con versión propia en
`VotoUTN/templates/base.html`, `gestion/base.html` y
`elecciones/base_publica.html`. `interfaz.js` conserva su URL compartida con
los imports de diálogos y deja de gestionar la posición. El nuevo módulo
restaura después de pageshow y del siguiente cuadro de renderizado, conserva
las exclusiones de rutas y anclas y acepta el formato anterior almacenado.

Se modifican también `VotoUTN/pruebas_js/conservar-posicion.test.cjs`,
`VotoUTN/apps/padron/tests.py`, `docs/decisiones_funcionales.md` y este
registro. No se modifican datos habituales ni se generan migraciones.

Verificación de posición versionada:

- Chrome real con el HTML autenticado de la copia de ensayo y los estáticos actuales del servidor: agregar conservó 3192 píxeles, ordenar 1563 y eliminar 1601. Se simularon los POST y sus redirecciones en un servidor aislado, sin enviar cambios a la base habitual. Se repitió con el módulo de diálogos antiguo y el nuevo módulo de posición para comprobar compatibilidad con caché previa. Se cerró el navegador de ensayo al terminar.
- Once pruebas de navegación aprobadas con `node --test VotoUTN/pruebas_js/conservar-posicion.test.cjs`. Sintaxis válida en ambos módulos JavaScript. Se verifica la URL compartida de diálogos y la carga versionada de posición en las tres plantillas base.
- Las 36 pruebas de reglas, solicitudes y atomicidad aprobaron en 7,921 segundos. Los rechazos por adicionales protegidos conservan reglas, asignaciones, mesas y autoridades.
- `python manage.py check`: sin incidencias. `makemigrations --check`: sin cambios. `migrate --plan`: sin operaciones pendientes. `git diff --check`: sin errores.
- Las verificaciones de esta corrección aprobaron. La última suite completa, anterior a estos ajustes, mantiene los cuatro fallos y tres errores previos documentados en la reparación de migraciones; no se declara completada la validación general.
- Se respetan las eliminaciones de autoridades y las reglas nuevas realizadas por el usuario. Para incorporar el nuevo script en una página que ya estaba abierta, recargar esa página una vez.

## 2026-11-16 — Nombre de sede de asistencia y departamentos desplegables

Se actualiza la etiqueta de condición a «Sede donde asiste» desde la definición
compartida, para cubrir formularios, reglas existentes y descripciones calculadas.
Se mantiene la clave interna `sede_donde_cursa`, las reglas guardadas y la
compatibilidad de importación de planillas nuevas y anteriores.

La selección de departamentos se agrupa en un `<details>` nativo con el texto
«Ver departamentos afectados», cerrado al entrar y abierto si vuelve un
formulario inválido. Los checkboxes y sus nombres se conservan dentro del
formulario; el script existente sigue sincronizando la opción de todos con
las individuales. No se agregan manejadores JavaScript ni estilos nuevos.

Archivos modificados: `VotoUTN/apps/padron/models.py`,
`VotoUTN/apps/padron/tests.py`,
`VotoUTN/templates/padron/configurar_sedes_claustro.html`,
`docs/decisiones_funcionales.md` y este registro. Se crea
`VotoUTN/apps/padron/migrations/0019_etiquetas_sede_donde_asiste.py` para las
tres condiciones concretas que heredan el campo compartido; no cambia los
valores ni columnas existentes. No se eliminan archivos.

Verificación de sede de asistencia y desplegable:

- Las 37 pruebas de reglas de sede, solicitudes y atomicidad aprobaron en 7,792 segundos. Incluyen la etiqueta nueva con la clave histórica, el cálculo con reglas existentes y el formulario inválido que conserva departamentos, abre el desplegable y muestra errores sin crear reglas.
- Chrome real con HTML autenticado de la base de ensayo y estáticos actuales: a 1200 y 390 píxeles de ancho, el desplegable inicia cerrado, abre y cierra, conserva selecciones individuales y sincroniza la opción de todos sin navegar. La prueba usa un servidor aislado y simula las redirecciones, sin enviar cambios a la elección habitual. El navegador de ensayo se cerró al terminar.
- La misma prueba de navegador conserva el desplazamiento al agregar (2774 píxeles), ordenar (1563) y eliminar (1601). Las once pruebas JavaScript de conservación de posición también aprobaron.
- La pantalla de reglas de la elección habitual respondió HTTP 200, con el nuevo texto y el desplegable cerrado, mediante una lectura autenticada dentro de una transacción revertida.
- `sqlmigrate padron 0019` mostró tres operaciones sin SQL de modificación de estructura o datos. La migración se aplicó correctamente en la base habitual. `check`: sin incidencias; `makemigrations --check`: sin cambios; `migrate --plan`: sin operaciones pendientes; `git diff --check`: sin errores.
- Suite completa: 787 pruebas en 332,731 segundos, 780 aprobadas, cuatro fallos y tres errores. Los siete casos coinciden exactamente con los registrados antes de esta tarea: avisos de ausencia con tipos demo y expectativas anteriores de fechas/interfaz de elecciones. No aparecen incidencias nuevas; la validación general sigue pendiente por esos casos.

## 2026-11-16 — Selección manual sin selector de función

Se retira el selector visible que solo ofrecía Titular. El formulario usa un
campo oculto con ese valor y lo completa si no se envía, manteniendo el rechazo
de tipos inválidos. La pantalla pide elegir turno y persona. Los reemplazos
siguen fijando la función y turno originales; se mantienen los controles del
servicio y las confirmaciones existentes.

Se modifican `VotoUTN/apps/autoridades/forms.py`,
`VotoUTN/templates/autoridades/seleccionar_mesa.html`,
`VotoUTN/apps/autoridades/tests_nomina.py`, `docs/decisiones_funcionales.md`
y este registro. No se crean ni eliminan archivos, no se modifican modelos ni
se requieren migraciones. Las pruebas no modifican la elección del usuario.

Verificación de función manual oculta:

- Las 184 pruebas de `apps.autoridades` aprobaron en 75,153 segundos. La edición en nómina, sorteo y modo histórico manual no muestra selector ni etiqueta de función. Las altas sin enviar tipo guardan Titular, el reemplazo sin tipo ni turno conserva el cupo original y un tipo inválido sigue rechazándose sin crear autoridades.
- Lectura autenticada de una mesa de la elección habitual: HTTP 200, campo Titular oculto y ningún selector ni etiqueta de función en el formulario. La transacción de verificación se revirtió, sin asignar ni reemplazar personas.
- `python manage.py check`: sin incidencias; `makemigrations --check`: sin cambios; `migrate --plan`: sin operaciones pendientes; `git diff --check`: sin errores.
- La comprobación general con `--keepdb --noinput --failfast` detectó 789 pruebas y se detuvo tras 31 en 8,102 segundos por el error anterior de tipos de justificativo demo en el aviso de ausencias. No se repite toda la suite de la tarea anterior, que registró cuatro fallos y tres errores; la validación general sigue pendiente. La suite completa de autoridades sí aprobó.

## 2026-11-16 — Botón Validar archivo en nómina de autoridades

Se cambia «Previsualizar nómina» por «Validar archivo» en la plantilla y en
el JavaScript que actualiza el botón al cambiar de modalidad. Se versiona el
recurso para que una copia anterior en caché no reponga el texto antiguo.
Se conserva el envío, la validación y la revisión de propuestas antes de
confirmar asignaciones.

Archivos modificados: `VotoUTN/templates/autoridades/gestion_claustro.html`,
`VotoUTN/static/js/explicacion-modo-autoridades.js`,
`docs/decisiones_funcionales.md` y este registro. No se crean ni eliminan
archivos ni se modifican modelos, migraciones o datos de la elección.

Verificación del texto Validar archivo:

- Las 37 pruebas existentes de nómina aprobaron en 37,663 segundos. Cubren validación, revisión sin asignar, alternativas, confirmación, errores de archivo y conservación de designaciones manuales.
- La plantilla renderizada para el modo nómina muestra Validar archivo y carga el recurso con versión 20261116.1. El JavaScript usa el mismo texto al cambiar de modalidad. La página habitual de autoridades respondió HTTP 200 en una lectura autenticada dentro de una transacción revertida.
- `node --check` sin errores; `check` sin incidencias; `makemigrations --check` sin cambios; `migrate --plan` sin operaciones pendientes; `git diff --check` sin errores.
- La comprobación general con `--keepdb --noinput --failfast` detectó 789 pruebas y se detuvo tras 31 en 7,702 segundos por el error previo de tipos de justificativo demo en los avisos de ausencia. La validación general sigue pendiente por las incidencias ya registradas.

## 2026-11-16 — Tarjetas pendientes ante claustros sin preparar

Se reproduce el falso verde de Autoridades, Mesas y Candidaturas con una
elección de cuatro claustros donde solo uno tiene padrón, mesa, autoridad y
candidatura. Los controles anteriores recorrían únicamente las mesas
existentes o comprobaban una presentación global.

El resumen toma ahora todos los claustros participantes, conserva como
pendientes los vacíos y comprueba sus prerrequisitos antes de la cobertura.
Autoridades valida el mínimo de cada mesa y turno con designaciones activas;
Mesas exige distribución completa y compatible del padrón activo;
Candidaturas exige puestos, presentaciones, listas y candidatos válidos de
cada claustro sin requerir llenar todos los cupos. Las tres tarjetas muestran
el avance y un detalle desplegable por claustro. Las consultas son de lectura
y no alteran los permisos ni las transiciones electorales.

Se crean `VotoUTN/apps/elecciones/resumen_preparacion.py`,
`VotoUTN/apps/elecciones/tests_resumen_preparacion.py` y
`VotoUTN/templates/elecciones/_resumen_preparacion_claustros.html`.
Se modifican `VotoUTN/apps/elecciones/views.py`,
`VotoUTN/templates/elecciones/configurar_eleccion.html`,
`docs/decisiones_funcionales.md` y este registro. No se eliminan archivos
ni se modifican modelos o migraciones.

También se actualiza una expectativa en
`VotoUTN/apps/autoridades/tests_distribucion.py` que aún buscaba el texto
Previsualizar nómina, reemplazado por Validar archivo en el punto anterior.

Verificación de tarjetas por claustro:

- Antes de corregir, la regresión de cuatro claustros con uno completo reprodujo el falso estado listo en las tres tarjetas. Después aprobaron 15 regresiones en 3,859 segundos: claustros vacíos o agregados posteriormente, padrón inactivo, falta de mesas o asignaciones, sede pendiente, mínimos por turno, autoridad rechazada, candidaturas inactivas, presentaciones sin claustro, capacidad y tipos de mesa. Se conserva el caso válido de adicionales en mesa especial.
- Verificación final conjunta: las 55 pruebas de resumen y distribución de autoridades aprobaron en 13,123 segundos, incluida la expectativa actualizada del botón de nómina.
- Lectura autenticada de configuración habitual: HTTP 200 y tres detalles por claustro. El resumen hizo diez consultas y tardó 0,073 segundos en esa medición local. Se revirtió la transacción de verificación. La elección tenía un solo claustro participante; los parámetros del catálogo que aún no participan no se agregan automáticamente.
- `check`: sin incidencias; `makemigrations --check`: sin cambios; `migrate --plan`: sin operaciones pendientes; `git diff --check`: sin errores.
- Suite completa: 804 pruebas en 348,548 segundos, 796 aprobadas, cinco fallos y tres errores. Uno de los fallos era exclusivamente la expectativa anterior del botón de nómina: se actualizó y la distribución completa aprobó en la verificación final. Los otros siete casos coinciden exactamente con los cuatro fallos y tres errores previos de fechas, pantallas de elecciones y justificativos demo. No se declara cerrada la validación general.

Reapertura solicitada para probar otro claustro:

Durante la verificación, el usuario pidió retroceder segmento1 (elección 4),
que había publicado por interfaz, para agregar un claustro. Se comprobó que
no tenía participación ni QR emitidos ni autoridades definitivas confirmadas.
En una transacción se llevó a En preparación, con habilitada=False y sin
habilitación de solicitudes de cambio de sede. Se conservaron fechas, 600
registros, 15 mesas, 600 asignaciones, una autoridad y 19 solicitudes. La
excepción quedó auditada en el evento 384, sin cambiar las transiciones
normales del sistema. Una lectura autenticada confirmó HTTP 200 y el alta de
claustro habilitada en `/gestion/elecciones/4/alcances/`.
