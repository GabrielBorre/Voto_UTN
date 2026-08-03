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
