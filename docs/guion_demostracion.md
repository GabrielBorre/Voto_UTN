# Guion de demostración — Voto UTN (20 minutos)

## Introducción

**Voto UTN** es una aplicación web responsive con la que la Junta Electoral de la UTN FRBA gestiona una elección universitaria completa. Permite configurarla, distribuir el padrón en sedes y mesas, registrar la participación escaneando los QR del padrón impreso y gestionar los justificativos. Al finalizar, identifica a los infractores. No hay que instalar nada: funciona en el navegador de la computadora y en el del celular.

### Roles que aparecen en la demostración

| Rol | Usuario demo (Keycloak) | Qué hace en la demo |
|---|---|---|
| Administrador de junta | `juanb` | Configura la elección, cambia sus estados, emite el padrón imprimible, confirma el escaneo y finaliza. |
| Administrativo de junta | `administrativojunta` | Registra la participación con el celular y gestiona justificativos. |
| Autoridad de mesa | `autmesa` | Consulta y confirma su asignación. **No registra participación.** |
| Elector | `alumnocg` (Carlos Gómez) | Consulta su mesa, recibe notificaciones y presenta un justificativo. |

### Hilo conductor

Se presenta una única elección de Estudiantes, desde su preparación hasta el cierre. El caso que recorre toda la demo es el de **Carlos Gómez**. Votó y se llevó su troquel como comprobante. Durante el escaneo, el operador comete un error de carga manual y Carlos queda registrado como ausente. Carlos presenta un reclamo con la foto de su troquel, el sistema valida el QR y la Junta corrige la situación antes del cierre.

> En el guion, `MESA_DEMO` es la mesa de Carlos que se escanea en vivo (por ejemplo, `K-005`) y `MESA_MANUAL` es la única otra mesa que queda pendiente para mostrar el registro manual. Reemplazar ambos por los códigos reales durante la preparación.

---

## Agenda

| # | Etapa | Duración | Minuto |
|---|---|---|---|
| 0 | Apertura y propósito | 1:00 | 00:00 – 01:00 |
| 1 | Inicio de la Junta y ciclo de vida de la elección | 1:30 | 01:00 – 02:30 |
| 2 | Configuración: sedes, padrón, asignación de sedes y mesas | 2:30 | 02:30 – 05:00 |
| 3 | Autoridades de mesa | 1:30 | 05:00 – 06:30 |
| 4 | Publicación y cambios de sede | 1:30 | 06:30 – 08:00 |
| 4.1 | Generacion de boletas
| 5 | Inicio de la elección y padrón imprimible con QR | 1:30 | 08:00 – 09:30 |
| 6 | Jornada electoral: escaneo QR con el celular | 3:30 | 09:30 – 13:00 |
| 7 | Tablero de participación y notificación a ausentes | 2:00 | 13:00 – 15:00 |
| 8 | Experiencia del elector: reclamo con su troquel | 2:00 | 15:00 – 17:00 |
| 9 | Intento de cierre y resolución del justificativo | 1:30 | 17:00 – 18:30 |
| 10 | Cierre: finalizar la elección y exportar infractores | 1:30 | 18:30 – 20:00 |
| | **Total** | **20:00** | |

---

## Etapa 0 — Apertura y propósito

1. **Tiempo estimado:** 1 minuto (00:00 – 01:00).
2. **Funcionalidad:** contexto del problema y del recorrido.
3. **Acciones:**
   - Tener en pantalla el **Inicio** del administrador de junta (`juanb`).
   - Mostrar físicamente el padrón impreso y el celular en el soporte.
4. **Speech sugerido:**
   > «Una elección universitaria implica configurar claustros, sedes y mesas; imprimir un padrón por mesa; y saber, terminada la jornada, quién no votó para gestionar justificativos e identificar infractores. Voto UTN digitaliza todo ese proceso sin cambiar la forma de votar: el elector sigue firmando un padrón en papel. La diferencia es que ese padrón tiene códigos QR que después leemos con un celular. Vamos a recorrer una elección completa con cuatro roles: administrador de junta, administrativo de junta, autoridad de mesa y elector. Todos ingresan con la cuenta institucional a través de Keycloak.»

**Transición:** «Empecemos por quien organiza la elección: la Junta.»

---

## Etapa 1 — Inicio de la Junta y ciclo de vida de la elección

1. **Tiempo estimado:** 1,5 minutos (01:00 – 02:30).
2. **Funcionalidad:** panel inicial de la Junta y ciclo de cuatro estados.
3. **Acciones:**
   1. En el **Inicio** de `juanb`, señalar las tarjetas **Elección actual**, **Justificativos pendientes**, **Solicitudes de cambio de sede pendientes** y **Participación**.
   2. Ir a **Configurar elección** en el menú.
   3. Mostrar la línea de tiempo **«Una elección, cuatro etapas»**: En preparación → Publicada → En curso → Finalizada. Señalar el **Estado actual** (En curso).
   4. Pasar el cursor sobre cada etapa para mostrar qué habilita.
   5. Señalar el aviso **«La configuración está en modo lectura»** y las tarjetas de configuración con sus indicadores (Configurado / Pendiente).
4. **Speech sugerido:**
   > «La elección avanza por cuatro estados en orden y cada uno habilita funcionalidades distintas. Tomamos tres decisiones de negocio importantes:
   > - Solo puede haber una elección activa a la vez. Hasta que no se finaliza, no se puede crear otra.
   > - Una vez publicada, la configuración queda en modo lectura. Así nadie puede cambiar sedes, padrones o mesas cuando los electores ya consultan su información.
   > - Cada cambio de estado pide una confirmación que explica qué va a pasar.
   >
   > Hoy la elección está En curso: es el día de la votación. Antes veamos cómo la preparamos.»

**Transición:** «La configuración sigue disponible para consulta. Veamos lo que se cargó en la etapa de preparación.»

---

## Etapa 2 — Configuración: sedes, padrón, asignación de sedes y mesas

1. **Tiempo estimado:** 2,5 minutos (02:30 – 05:00).
2. **Funcionalidad:** configuración en cascada de sedes, importación del padrón por CSV, asignación automática de sedes por reglas y generación automática de mesas.
3. **Acciones:**
   1. **Ver sedes y departamentos:** mostrar las sedes habilitadas para la elección, luego por claustro y luego por departamento.
   2. Volver y entrar en **Ver padrones** → padrón de **Estudiantes**. Desplegar **Historial de importaciones** y abrir una importación con **Ver**. Señalar las cantidades de electores nuevos, existentes y con errores.
   3. Abrir **Configurar asignación de sedes**. Mostrar las reglas ordenadas y el resumen del tipo «N electores se asignaron a la sede X por la regla Y».
   4. Volver y entrar en **Ver mesas**. Aplicar un filtro (por ejemplo, por sede) y señalar los códigos de mesa con el formato `K-001`.
4. **Speech sugerido:**
   > «La configuración funciona en cascada. Primero se eligen las sedes de la elección. Cada claustro las hereda y puede quitar algunas. Después, cada departamento hereda las de su claustro.
   >
   > El padrón se importa con un CSV y siempre hay una vista previa antes de confirmar. El sistema separa los electores nuevos de los que ya estaban y detecta los errores. **Si hay un solo error, no se importa nada** hasta corregirlo, para no quedar con un padrón a medias.
   >
   > La sede de votación se asigna con reglas ordenadas que define la Junta. Si un departamento tiene una sola sede, se asigna directamente. Si ninguna regla aplica, el elector queda pendiente de revisión: **el sistema nunca elige una sede al azar**.
   >
   > Con las sedes asignadas y un máximo de electores por mesa, las mesas se calculan solas. Cada una tiene un código con la letra del departamento y un número único en toda la elección: no pueden existir a la vez K-001 y E-001.»

**Transición:** «Las mesas necesitan quien las atienda: las autoridades de mesa.»

---

## Etapa 3 — Autoridades de mesa

1. **Tiempo estimado:** 1,5 minutos (05:00 – 06:30).
2. **Funcionalidad:** asignación de autoridades por mesa y turno, y la vista de la autoridad.
3. **Acciones:**
   1. En **Configurar elección**, entrar en **Ver autoridades** → claustro Estudiantes. Mostrar los turnos de trabajo y las autoridades asignadas por mesa. Mencionar la importación por CSV y la asignación manual, sin ejecutarlas.
   2. Cambiar al perfil de navegador de `autmesa`. En el **Inicio**, mostrar la tarjeta **Desempeño como Autoridad de Mesa** con su mesa, sede y turno.
   3. Ir a **Mis asignaciones** y pulsar **Confirmar** en la asignación pendiente.
   4. Señalar que su menú **no** tiene «Registro de participación».
4. **Speech sugerido:**
   > «Una autoridad de mesa no es un usuario aparte: es un elector del padrón y del mismo claustro. Se puede cargar por CSV o seleccionarla a mano, y en ambos casos el sistema valida que sus datos coincidan con el padrón. Cada asignación tiene un turno de trabajo, y hay un máximo de autoridades por mesa y por turno.
   >
   > Una decisión de negocio importante: **la autoridad de mesa no registra la participación.** Esa tarea la hace el administrativo de junta. Así se separan las funciones de quien atiende la mesa y quien registra el resultado.»

**Transición:** «Con todo configurado, la Junta publica la elección.»

---

## Etapa 4 — Publicación y cambios de sede

1. **Tiempo estimado:** 1,5 minutos (06:30 – 08:00).
2. **Funcionalidad:** publicación de la elección y resolución de solicitudes de cambio de sede.
3. **Acciones:**
   1. Volver al perfil de `juanb`. En **Configurar elección**, pasar el cursor sobre la etapa **Publicada**.
   2. *(Opcional)* Mostrar la captura del diálogo **Publicar elección** tomada durante la preparación (ver la sección de preparación).
   3. Ir a **Cambios de sede** en el menú. Mostrar el listado con el filtro por estado, la tabla de mesas por sede y las acciones de resolución masiva (**Aceptar todas sin límite de mesas nuevas**, **Aceptar con límite de mesas nuevas**).
   4. Señalar el aviso **«Cambios de sede en modo lectura: el padrón imprimible ya fue generado…»**.
4. **Speech sugerido:**
   > «Al publicar, el sistema pide dos fechas límite: la de solicitudes de cambio de sede y la de justificativos de autoridades de mesa. Además, avisa a los electores que el padrón definitivo está disponible.
   >
   > Mientras la elección está Publicada, cada elector puede pedir **una sola vez** votar en otra sede. La Junta puede aprobar las solicitudes de a una o seleccionarlas en grupo. El sistema estima cuántas mesas nuevas hacen falta y permite fijar un máximo total. Cada resolución se notifica al elector.
   >
   > Ahora estos botones están bloqueados a propósito: **una vez emitido el padrón imprimible, los cambios de sede quedan en modo lectura**, porque los QR impresos ya indican la mesa de cada elector.»

**Transición:** «Eso nos lleva al día de la elección y al padrón impreso.»

---

## Etapa 5 — Inicio de la elección y padrón imprimible con QR

1. **Tiempo estimado:** 1,5 minutos (08:00 – 09:30).
2. **Funcionalidad:** inicio de la elección, generación del padrón imprimible y funcionamiento del troquel.
3. **Acciones:**
   1. En **Configurar elección**, pasar el cursor sobre **En curso**.
   2. Entrar en **Ver reportes** → **Generar padrón imprimible**. Abrir el PDF (o tener abierto el que ya se generó).
   3. En el PDF, mostrar la **carátula** de `MESA_DEMO`: claustro, «INFORMACIÓN DE MESA», sede, departamento, código de mesa y el QR grande con el texto «Escanee este código para comenzar el registro de la mesa».
   4. Mostrar una hoja con las columnas **N.º, DNI, Apellido/s, Nombre/s, Firma del elector** y **Comprobante de voto**. Esta última es el troquel con su QR.
   5. Levantar el padrón impreso, que ya tiene recortados los troqueles de quienes votaron.
4. **Speech sugerido:**
   > «Al iniciar la elección, cada elector recibe una notificación con su sede y su mesa. Recién en este estado se puede generar el padrón imprimible: antes podía haber cambios de sede y eso cambiaría los QR.
   >
   > El padrón tiene una carátula por mesa con un QR que la identifica, y luego hojas de hasta 15 electores. El circuito es simple: **el elector firma, la autoridad recorta el troquel y se lo entrega como comprobante de voto.** Al terminar la jornada, en la hoja solo quedan los QR de **quienes no votaron**.
   >
   > Los QR no contienen el DNI. Llevan la elección, la mesa y un identificador del elector, y están **firmados digitalmente**. El sistema rechaza un QR adulterado, uno de otra elección o uno de otra mesa.»

**Transición:** «Terminó la votación. Pasemos al celular del administrativo de junta.»

---

## Etapa 6 — Jornada electoral: escaneo QR con el celular

1. **Tiempo estimado:** 3,5 minutos (09:30 – 13:00).
2. **Funcionalidad:** registro de inasistencias escaneando el padrón con la aplicación web en el celular, la validación de mesa y la carga manual por DNI.
3. **Acciones** (celular en el soporte, con la sesión de `administrativojunta` ya iniciada):
   1. En **Registro de participación**, pulsar **Comenzar escaneo**.
   2. Poner la **carátula de `MESA_DEMO`** bajo la cámara. Suena un tono de confirmación y aparece **«Mesa a escanear»** con departamento, claustro, sede, estado y cantidad de electores.
   3. Pulsar **Comenzar escaneo de electores**.
   4. **Validación representativa:** poner una hoja de **otra mesa**. Suena un tono de error y aparece «El QR es de la mesa N. Registrá primero la mesa `MESA_DEMO`.». Retirar la hoja.
   5. Poner la **hoja 1 de `MESA_DEMO`** y mantenerla quieta. El contador **Inasistencias registradas** sube. A los 3 segundos se registra sola: «Hoja registrada (N QR). Pasar a la siguiente.»
   6. Cambiar a la **hoja 2** y repetir.
   7. **Error simulado:** pulsar **Carga Manual**, ingresar el DNI de Carlos Gómez y pulsar **Registrar**. Aparece «Inasistencia registrada en la mesa `MESA_DEMO`.».
   8. Pulsar **Registrar Mesa**. El diálogo muestra «Inasistencias registradas: N». Pulsar **Confirmar**.
   9. Mostrar el **Resumen de mesa**: «Mesa `MESA_DEMO` procesada».
4. **Speech sugerido:**
   > «El administrativo de junta usa el navegador del celular; no hace falta instalar ninguna aplicación. Primero escanea la carátula para indicar qué mesa va a registrar.
   >
   > Si por error pongo una hoja de otra mesa, el sistema la rechaza y me pide terminar primero la mesa actual. Así no se mezclan padrones.
   >
   > Ahora pongo las hojas de la mesa. El celular lee **todos los QR de la hoja a la vez**. Cuando la hoja está quieta, la registra sola y me pide la siguiente. Si un QR ya estaba registrado, no se duplica.
   >
   > Si un QR no se puede leer, existe la carga manual por DNI, con las mismas validaciones y la misma auditoría. Acá vamos a simular un error humano: el operador carga por equivocación el DNI de Carlos, que sí votó y tiene su troquel.
   >
   > Por último, confirmo la mesa. La mesa pasa de Pendiente a En proceso y luego a Procesada, y queda registrado quién hizo cada operación y cuándo.»

**Transición:** «Mientras tanto, la Junta sigue todo en tiempo real desde la computadora.»

---

## Etapa 7 — Tablero de participación y notificación a ausentes

1. **Tiempo estimado:** 2 minutos (13:00 – 15:00).
2. **Funcionalidad:** tablero de participación, registro manual de una mesa y confirmación del escaneo con notificación a los ausentes.
3. **Acciones** (perfil de `juanb`):
   1. Ir a **Registro de participación**. Mostrar los indicadores **Mesas escaneadas**, **Participación**, **Justificativos recibidos** y **Justificativos aceptados**.
   2. En la tabla **Mesas**, señalar `MESA_DEMO` como **Procesada**, con la columna **Votaron**. Filtrar **Estado de la mesa = Pendiente**: solo queda `MESA_MANUAL`. Señalar que todavía **no aparece** el botón para confirmar el escaneo.
   3. Pulsar **Registrar** en `MESA_MANUAL`. El diálogo muestra la cantidad de electores e inasistencias. Pulsar **Confirmar registro**.
   4. Aparece **Confirmar escaneo y notificar ausentes**. Pulsarlo, completar **Último día para presentar justificativos** (por ejemplo, dentro de una semana) y pulsar **Confirmar y habilitar período**.
   5. *(Opcional, 10 segundos)* Mostrar en Mailpit (`http://localhost:8025`) los correos enviados a los ausentes.
4. **Speech sugerido:**
   > «El tablero muestra el avance por mesa y se puede filtrar por claustro, sede, departamento y estado. La participación se calcula **solo sobre las mesas procesadas**, para no contar como votos las mesas que todavía no se escanearon.
   >
   > Si una mesa no se puede escanear, la Junta puede registrarla manualmente desde aquí.
   >
   > Hasta que todas las mesas están procesadas, el sistema no permite notificar a los ausentes. Ahora sí: la Junta fija la fecha límite para justificar, y el sistema envía la notificación a cada ausente, por correo y dentro de la aplicación. Esta acción se ejecuta una sola vez por elección y queda auditada.»

**Transición:** «Veamos qué recibió Carlos.»

---

## Etapa 8 — Experiencia del elector: reclamo con su troquel

1. **Tiempo estimado:** 2 minutos (15:00 – 17:00).
2. **Funcionalidad:** notificaciones, información electoral del elector y presentación de un reclamo «Voté, pero aparezco como ausente» con validación del QR del troquel.
3. **Acciones** (perfil de `alumnocg`; recargar la página):
   1. Mostrar la campana de **Notificaciones** con el contador y abrir el aviso de inasistencia.
   2. En **Inicio** («Mi información electoral»), señalar la situación **⚠ En Curso - Voto No Registrado**, la mesa `MESA_DEMO`, la sede y la fecha límite de justificación.
   3. Ir a **Mis justificativos**. Marcar **«Voté, pero aparezco como ausente»**: se ocultan «Ausencia a justificar» y «Tipo».
   4. Adjuntar la foto JPG del troquel de Carlos. Escribir un comentario breve (por ejemplo, «Voté en la mesa `MESA_DEMO`, adjunto mi comprobante»). Pulsar **Presentar** y luego **Confirmar**.
4. **Speech sugerido:**
   > «Carlos recibió el aviso por correo y en la aplicación. En su inicio ve su mesa y figura con el voto no registrado.
   >
   > Como votó, no necesita inventar un motivo. Marca "Voté, pero aparezco como ausente" y sube una foto del troquel que le dieron en la mesa. Si lo hubiera perdido, puede indicarlo y la Junta revisaría la firma en el padrón en papel.
   >
   > Al subir la imagen, el sistema **lee el QR del troquel y verifica su firma, la elección y que corresponda a este elector**. Esta validación solo ayuda a la Junta: la ausencia no se borra hasta que una persona apruebe el reclamo.»

**Transición:** «Volvamos a la Junta, que quiere cerrar la elección.»

---

## Etapa 9 — Intento de cierre y resolución del justificativo

1. **Tiempo estimado:** 1,5 minutos (17:00 – 18:30).
2. **Funcionalidad:** validación de cierre y resolución de un justificativo con el comprobante validado.
3. **Acciones** (perfil de `juanb`):
   1. En **Configurar elección**, pulsar **Finalizar elección →** y confirmar. El sistema lo rechaza: **«No se puede finalizar la elección con justificativos pendientes.»**
   2. Ir a **Justificativos** → pestaña **Inasistencia de electores**. Señalar el indicador **«QR válido para el elector»** en el reclamo de Carlos y pulsar **Resolver**.
   3. En **Revisar justificativo**, mostrar el detalle de la validación («El QR corresponde al elector y a la mesa N.») y **Ver documento adjunto**.
   4. Elegir **Aprobar**, completar una observación breve y pulsar **Guardar resolución**.
4. **Speech sugerido:**
   > «La elección no se puede cerrar con justificativos pendientes ni con mesas sin procesar. Así nadie queda como infractor por un trámite que nadie revisó.
   >
   > En la bandeja, la Junta ve que el comprobante es válido. Esta tarea también la puede hacer el administrativo de junta. Al aprobar el reclamo, **se anula el registro de ausencia**: se guarda una copia y queda en la auditoría. Si después cambiara a rechazado, la ausencia se restaura. Carlos recibe la resolución por correo y en la aplicación.»

**Transición:** «Ahora sí podemos cerrar la elección.»

---

## Etapa 10 — Cierre: finalizar la elección y exportar infractores

1. **Tiempo estimado:** 1,5 minutos (18:30 – 20:00).
2. **Funcionalidad:** finalización de la elección, exportación de infractores y cierre de la presentación.
3. **Acciones:**
   1. Con `juanb`, en **Configurar elección**, pulsar **Finalizar elección →**. El diálogo advierte que el período de justificación sigue vigente. Pulsar **Finalizar elección** para confirmar. La línea de tiempo muestra **Finalizada**.
   2. Ir a **Ver reportes** → **Exportar infractores** y abrir el CSV. Aparecen los ausentes que no justificaron, con `estado_justificativo` igual a `sin_justificativo` o `rechazado`. **Carlos no aparece.**
   3. *(Si sobra tiempo)* En el perfil de `alumnocg`, abrir **Historial Electoral**: la elección figura como **✔ Inasistencia Justificada**.
4. **Speech sugerido (cierre):**
   > «Al finalizar, la elección queda solo para consulta: no se puede modificar nada más. Quien tiene una ausencia registrada y no presentó justificativo, o se lo rechazaron, pasa a ser infractor. La Junta exporta esa nómina en un clic, y Carlos no figura porque su reclamo fue aprobado.
   >
   > Recapitulando, recorrimos una elección completa: configuración con validaciones, publicación y cambios de sede, un padrón impreso con QR firmados, registro de ausencias con un celular, notificaciones automáticas, justificativos con verificación del comprobante y el cierre con los infractores. Cada rol hace solo lo que le corresponde y cada operación queda auditada. Muchas gracias; quedamos a disposición para sus preguntas.»

---

## Validaciones priorizadas

Se muestran en vivo solo las validaciones más representativas. El resto se menciona en el speech.

| Validación | Cómo se presenta |
|---|---|
| QR de otra mesa durante el escaneo | **En vivo** (etapa 6) |
| Confirmar el escaneo y notificar ausentes solo con todas las mesas procesadas | **En vivo**: el botón aparece después de registrar la última mesa (etapa 7) |
| Validación del QR del troquel en el reclamo | **En vivo** (etapas 8 y 9) |
| No finalizar con justificativos pendientes | **En vivo** (etapa 9) |
| Configuración en modo lectura desde Publicada | **Visible** en la pantalla (etapas 1 y 2) |
| Cambios de sede bloqueados tras emitir el padrón | **Visible** en la pantalla (etapa 4) |
| Importación CSV bloqueada si hay errores | Mencionada (etapa 2) |
| Una sola elección activa | Mencionada (etapa 1) |
| Autoridad del mismo claustro, máximo por mesa y turno | Mencionada (etapa 3) |
| Una solicitud de cambio de sede por elector y elección | Mencionada (etapa 4) |

---

## Preparación previa

### Por qué la elección debe llegar "En curso" a la demo

- El padrón imprimible **solo se genera con la elección En curso**, y emitirlo bloquea los cambios de sede.
- **Solo puede existir una elección no finalizada.** Por eso no se puede crear ni configurar otra elección en vivo.
- Conclusión: la demo arranca con la elección ya **En curso** y el padrón ya emitido e impreso. Las etapas 1 a 5 se muestran en modo consulta, que es como el sistema las presenta en ese estado. En vivo solo se ejecutan las acciones de la jornada y del cierre.

### Datos de prueba

1. Levantar el entorno con `docker compose up -d` desde la raíz del repositorio. Verificar que existan los catálogos estándar; si faltan, ejecutar `python manage.py cargar_parametros_estandar` dentro del contenedor `web`.
2. Verificar que **no haya otra elección sin finalizar**. Tener en cuenta que `seed_demo_data` crea una elección en estado Publicada, que impediría crear la de la demo.
3. Verificar que `juanb` tenga el rol activo de **Administrador de junta** y `administrativojunta` el de **Administrativo de junta**.
4. Recorrer el flujo real con `juanb`:
   1. **Crear elección** con el claustro Estudiantes.
   2. Completar **Sedes y departamentos** y los turnos de autoridades.
   3. Importar el padrón CSV (por ejemplo, `padron_estudiantes_500.csv`). Debe incluir a `alumnocg` (DNI 38999222) y `autmesa` (DNI 28111333) con el mismo DNI, legajo, nombre y correo que tienen en Keycloak.
   4. Configurar las reglas de asignación de sedes y el **máximo de electores por mesa**. Se recomienda 30 o menos, para que `MESA_DEMO` tenga carátula y dos hojas.
   5. Importar las autoridades por CSV (por ejemplo, `plantilla_autoridades_5_Estudiantes.csv`) incluyendo a `autmesa`. **Dejar su asignación pendiente** para confirmarla en vivo (etapa 3).
   6. **Publicar elección**, completando las fechas solicitadas. Se generan automáticamente hasta 70 solicitudes ficticias de cambio de sede, según los electores y sedes elegibles.
   7. Revisar y resolver las solicitudes pendientes antes de confirmar las autoridades definitivas. Para mostrar una solicitud en la etapa 4, aprobar al menos una de un elector que **no sea** Carlos.
   8. **Iniciar elección** y **Generar padrón imprimible**.
5. Anotar `MESA_DEMO` (la mesa de Carlos, que figura en su Inicio) y elegir `MESA_MANUAL`.
6. **Procesar todas las demás mesas** antes de la demo con el botón **Registrar** del tablero. Solo deben quedar pendientes `MESA_DEMO` y `MESA_MANUAL`.
7. **No dejar justificativos pendientes** que no sean el de la demo; si no, no se puede finalizar. Los comandos `generar_justificativos_electores_demo` y `generar_justificativos_autoridades_demo` crean dos cada uno cuando hay registros elegibles.

> Los nombres `padron_estudiantes_500.csv` y `plantilla_autoridades_5_Estudiantes.csv` son los archivos del equipo. No están en el repositorio y **no hay un comando que arme este escenario automáticamente**: hay que prepararlo con el flujo anterior.

### Padrón impreso

1. Imprimir del PDF **solo** la carátula y las hojas de `MESA_DEMO`, más **una hoja de otra mesa** para la validación de la etapa 6.
2. **Recortar los troqueles** de la mayoría de los electores de `MESA_DEMO` (los que "votaron"). Dejar unos pocos sin recortar, que serán los ausentes.
3. Recortar también el troquel de **Carlos Gómez**. Sacarle una **foto nítida en JPG/PNG**, guardarla en la notebook y probar que el reclamo devuelva «QR válido para el elector».
4. Llevar copias impresas de reserva por si una hoja se dobla o se mancha.

### Dispositivos y red

1. La notebook y el celular deben estar en la **misma red Wi-Fi**. Abrir en el firewall de la notebook los puertos **8443** (aplicación por HTTPS) y **8080** (Keycloak).
2. En el celular, entrar a `https://<IP-de-la-notebook>:8443` y aceptar el certificado interno. La cámara solo funciona con HTTPS. Iniciar sesión como `administrativojunta` y dejarlo en **Registro de participación**.
3. Dar permiso de cámara al navegador y **subir el volumen**: los tonos de éxito y error forman parte de la demo.
4. Ajustar la altura del soporte para que una hoja completa entre en el cuadro, con buena iluminación y sin reflejos. Probar con las hojas reales.
5. *(Recomendado)* Duplicar la pantalla del celular en el proyector para que los profesores vean el escaneo.
6. Tener **conexión a internet**: el gráfico «Historial de participación» del tablero carga Chart.js desde una CDN.
7. Usar **un perfil de navegador (o una ventana de incógnito) por rol** (`juanb`, `autmesa`, `alumnocg`), con la sesión iniciada poco antes de empezar. Así se evita que la sesión única de Keycloak abra el usuario equivocado.
8. Tener abierta una pestaña de Mailpit (`http://localhost:8025`) y el PDF del padrón ya generado.

### Respaldo y ensayos

1. Finalizar la elección **no se puede deshacer**. Con el escenario listo, sacar un respaldo de la base:
   `docker exec voto_utn_db pg_dump -U <usuario> -Fc <base> > demo_inicial.dump`
   Después de cada ensayo, restaurarlo con `pg_restore`.
2. Tomar capturas del diálogo **Publicar elección** y de la vista previa de una importación con errores durante la preparación. Sirven de apoyo si preguntan por pasos que no se ven en vivo.
3. Ensayar al menos dos veces con cronómetro. Si van atrasados, recortar primero lo opcional (Mailpit y el historial del elector) y luego acortar la etapa 2.

### Plan de contingencia

| Problema | Alternativa ya implementada |
|---|---|
| La cámara no lee la carátula | Escribir el código de mesa y pulsar **Buscar mesa**. |
| Un QR del padrón no se lee | **Carga Manual** por DNI en el celular. |
| Falla el escaneo de la mesa completa | Botón **Registrar** de la mesa en el tablero de escritorio. |
| La foto del troquel no se valida | Presentar el reclamo con **«Perdí el comprobante de votación»** y un comentario. La Junta lo revisa manualmente. |
