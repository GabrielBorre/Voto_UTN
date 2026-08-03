# Registro de cambios por etapa

Este documento registra cambios aplicados al proyecto. Describe los archivos y el efecto de cada cambio; no reemplaza el historial de Git ni las migraciones de Django.

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
