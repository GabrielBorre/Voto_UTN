# Decisiones funcionales confirmadas

## Aplicación de asistencia

- Es una aplicación web responsive.
- Se utiliza desde el navegador del dispositivo móvil.
- No existe una aplicación móvil nativa.
- El administrativo de junta registra la participación.
- La autoridad de mesa no registra participación.
- El registro por QR o carga manual identifica a quienes no votaron; la ausencia
  de un registro implica que se presume que el elector votó.
- El historial electoral se muestra a electores y autoridades de mesa, y cada
  persona solo consulta sus propios registros y justificativos.
- Un elector autenticado puede acceder al historial aunque todavía no exista en
  el padrón local; en ese caso se muestra vacío.
- El inicio del elector muestra la información de la elección únicamente cuando
  está Publicada o En curso. Una elección En preparación no debe ser visible allí.
- Las elecciones Publicadas y En curso aparecen en el historial electoral y
  muestran «En Curso» hasta que el administrador de junta confirma el escaneo de
  todas las mesas. Esa confirmación actualiza únicamente la situación de los
  electores de esa elección: «Voto Emitido» si no tienen registro de ausencia o
  «En Curso - Voto No Registrado» si lo tienen. «Voto Emitido» es definitivo
  desde esa confirmación. Para quien sí tiene ausencia, «En Curso - Voto No
  Registrado» se mantiene durante el período de justificación; al vencer el
  plazo, pasa a «Infractor» si no hay un justificativo que determine otro
  estado. Los justificativos aplicables conservan prioridad. La confirmación
  de una elección no modifica las situaciones de las demás elecciones del
  historial.
- Al finalizar una elección, quien tenga una ausencia registrada y no haya
  presentado un justificativo figura como «Infractor», con independencia de que
  se haya abierto el período de justificación o vencido su fecha límite. Quien
  no tenga registro de ausencia figura como «Voto Emitido». Los justificativos
  presentados conservan prioridad y su estado histórico.
- Dentro del período habilitado, un justificativo pendiente figura como
  «Pendiente de Revisión»; uno aprobado, como «Inasistencia Justificada»; y uno
  rechazado, como «Infractor - Justificación Rechazada».
- Al confirmar el escaneo de todas las mesas, el administrador de junta indica
  la fecha límite inclusiva para justificar ausencias. La misma acción notifica
  a los electores ausentes y abre el período de justificativos hasta esa fecha.
  Si el escaneo ya se había confirmado sin abrir el período, el administrador
  puede definir el plazo posteriormente sin volver a generar notificaciones.
- La pantalla de fechas administrativas muestra el período real de justificativos
  electorales: su inicio es la fecha local de la primera notificación y su fin
  es el plazo inclusivo ingresado al abrirlo. Antes de abrirlo, informa que la
  fecha límite se solicitará al notificar las ausencias. No se configura ese
  plazo como una fecha administrativa independiente; la definición genérica y
  sus comunicaciones de calendario quedan inactivas sin eliminar su historial.
- Mientras la elección siga En curso, el administrador de junta puede cambiar
  el plazo desde Fechas administrativas, incluso después de su vencimiento. El
  cambio solo puede extender el período: la nueva fecha límite debe ser
  posterior a la vigente y no anterior a la fecha actual. El inicio no cambia;
  una fecha futura vuelve a habilitar la presentación. El cambio requiere confirmación y
  genera nuevas notificaciones solo para electores ausentes que no hayan
  presentado un justificativo electoral. Los envíos previos se conservan como
  historial; los errores de correo se informan sin revertir el plazo ni los
  envíos ya realizados.
- Solo se puede presentar un justificativo electoral durante el período
  habilitado y si existe un registro de ausencia. La fecha límite configurada
  es inclusiva. Antes de finalizar la elección, al vencer el plazo la ausencia
  sin solicitud pasa a «Infractor»; una solicitud pendiente o rechazada conserva
  su estado propio.
- La tarjeta «Justificación de inasistencia electoral» del inicio se muestra
  únicamente a registros con estado «En Curso - Voto No Registrado» o
  «Justificativo Pendiente de Revisión». Se oculta para quienes figuran como
  «Voto Emitido», «Inasistencia Justificada», «Infractor - Justificación
  Rechazada» o «Infractor».

## Elecciones, claustros, sedes y departamentos

- En estado **En curso** la configuración se conserva consultable, pero no
  modificable desde las pantallas ni sus endpoints. Las excepciones son las
  fechas administrativas existentes, la emisión del padrón imprimible y el
  avance a Finalizada. No se incorpora por ahora la solicitud de fechas al
  cambiar de estado ni una nueva clasificación de fechas por estado.
- Al pasar una elección a **Publicada** se inicia el período de solicitudes de
  cambio de sede. En esa transición se solicita su fecha límite y se registra
  el inicio real. El administrador de junta puede modificar la fecha límite
  desde Fechas administrativas hasta confirmar las autoridades definitivas; a
  partir de esa confirmación el período queda cerrado. En el inicio del elector
  se muestra mientras la elección siga Publicada, no se hayan confirmado las
  autoridades y no haya vencido el plazo; cierra por la fecha o por la
  confirmación, lo que ocurra primero.
- Al confirmar las autoridades definitivas se inicia el período de eximición de
  autoridades de mesa y en esa misma acción se solicita su fecha límite. El
  administrador de junta puede modificarla desde Fechas administrativas
  mientras la elección siga Publicada. En el inicio del elector se muestra a
  las autoridades asignadas hasta la fecha límite inclusive o hasta que la
  elección pase a En curso, lo que ocurra primero. Cada modificación notifica a
  las autoridades confirmadas.
- Solo se pueden agregar o quitar claustros en **En preparación**. Los nuevos
  heredan las sedes de la elección; eliminar un claustro con datos vinculados
  se rechaza sin borrar padrones ni modificar sus alcances.
- El padrón imprimible con QR solo se genera **En curso**. Su emisión deja
  **todos** los cambios de sede de la elección en modo lectura, incluidos los
  rechazos individuales y masivos. No se permite rehabilitar cambios de
  configuración en curso ni invalidar los QR impresos desde ese flujo.
- La junta puede resolver cambios de sede en Publicada y En curso hasta la
  primera emisión del padrón imprimible. Puede seleccionar solicitudes,
  estimar las mesas adicionales y aprobar únicamente las marcadas. La
  estimación simula la capacidad de cada mesa en el mismo orden de aprobación.
- Los correos y las tarjetas de inicio identifican la mesa mediante su código
  canónico (por ejemplo, `K-001`), no solo su número.
- Configurar elección abre directamente la configuración actual y muestra
  los cuatro estados e indicadores de pendientes. Al crear la elección se
  continúa por Sedes y departamentos. El inicio de junta muestra cuatro
  tarjetas informativas sin acciones, o Crear elección si no hay una actual.
- La participación del inicio reutiliza el dashboard: solo computa electores
  de mesas procesadas; los QR escaneados representan ausencias. Se aclara ese
  denominador en la tarjeta para no presentar mesas sin procesar como votos.
- Las confirmaciones y avisos interactivos usan diálogos propios, y las
  operaciones demoradas muestran un indicador de procesamiento.

- Puede existir como máximo una elección en estado En preparación, Publicada o
	En curso en conjunto. Las elecciones finalizadas pueden ser múltiples; mientras
	exista una elección no finalizada no se permite crear otra.
- Una elección finalizada queda en modo de consulta: no se pueden editar sus datos
  ni modificar sus alcances, fechas administrativas, padrón, mesas, autoridades,
  listas, candidaturas ni resoluciones de justificativos. El historial conserva el acceso de consulta; el
  dashboard por elección finalizada queda pendiente y no forma parte de esta entrega.
- Cualquier usuario con el rol activo de administrador de junta puede editar y
	administrar cualquier elección, sin importar quién la creó o qué elección
	figure en su asignación de rol.
- Cualquier usuario con el rol activo de administrativo de junta puede realizar
	en todas las elecciones las tareas que ya corresponden a su rol: registrar
	participación y gestionar justificativos. Esto no le concede permisos para
	importar padrones, crear o editar elecciones, cambiar su estado,
	administrar parámetros ni configurar padrones, tareas reservadas al
	administrador de junta o al administrador del sistema. La asignación de este
	rol puede ser global, sin elección, sede ni mesa asociadas.

La configuración de sedes se realiza en cascada:

1. Se seleccionan las sedes habilitadas para toda la elección.
2. Se seleccionan los claustros participantes.
3. Cada claustro hereda inicialmente todas las sedes habilitadas para la elección.
4. Se pueden quitar sedes para cada claustro.
5. Cada `EleccionClaustroDepartamento` hereda inicialmente todas las sedes habilitadas para su `EleccionClaustro`.
6. Se pueden quitar sedes para cada departamento.
7. Una mesa solo puede asignarse a una sede habilitada en el nivel correspondiente.

## Entidades agrupadoras

Usar nombres explícitos:

- `EleccionSede`
- `EleccionClaustro`
- `EleccionClaustroSede`
- `EleccionClaustroDepartamento`
- `EleccionClaustroDepartamentoSede`

No utilizar `DivisionElectoral` como reemplazo de `EleccionClaustroDepartamento`.

## Departamentos

`Departamento` es parametrizable.

Campos mínimos:

- `id`
- `nombre`
- `codigo`
- `activo`

Ejemplo: `Sistemas de Información` / `K`.

## Mesas

- Cada mesa pertenece a una elección.
- Cada mesa pertenece a una combinación `EleccionClaustroDepartamento`.
- Cada mesa se asigna a una sede habilitada.
- La mesa funciona durante toda la jornada electoral y no tiene turno.
- El elector puede votar en cualquier momento de la jornada y no recibe un turno.
- `numero` es único dentro de toda la elección.
- El prefijo del departamento no permite repetir números.
- `K-001` y `E-001` no pueden coexistir dentro de la misma elección.

## Importación del padrón

- La previsualización muestra electores en el archivo, electores nuevos para incorporar, electores ya incluidos en el padrón y errores. Los existentes se identifican por la coincidencia de DNI y legajo con el mismo elector. Las cantidades de nuevos y existentes cuentan solo filas válidas; si hay errores, la importación completa queda bloqueada hasta corregirlos.
- La pantalla de gestión de padrones muestra por claustro la cantidad de electores con registro activo en esa elección.

## Autoridades

- Una autoridad de mesa es también un elector.
- El rol visible de Autoridad de Mesa requiere una asignación no rechazada en
  una elección Publicada o En curso. Las asignaciones de elecciones en
  preparación o finalizadas no modifican el rol visible de Elector.
- No se crea una identidad duplicada.
- Debe existir previamente como elector.
- Debe pertenecer al padrón de la elección.
- Debe pertenecer al mismo claustro.
- La importación CSV solo acepta una fila si coinciden DNI, legajo, nombre, apellido, correo electrónico y departamento con los datos del elector y su registro activo de padrón. Los nombres se comparan sin distinguir mayúsculas, espacios repetidos ni tildes; el correo se compara sin distinguir mayúsculas.
- No puede ser autoridad de otro claustro.
- Puede incorporarse por CSV o selección manual.
- Ambos mecanismos producen la misma asignación.
- Cada asignación de autoridad tiene un único turno de trabajo.
- Una mesa puede tener varias autoridades en el mismo turno y autoridades en turnos diferentes para cubrir los cambios de ronda.
- Los turnos se habilitan por elección desde la gestión de autoridades y no desde la creación inicial de la elección.
- El máximo de autoridades se aplica por mesa y por turno.
- Conserva las funcionalidades de elector.
- La autoridad de mesa no registra participación.

## Partidos y candidatos

- El parámetro reutilizable es el puesto a elegir y el órgano o cuerpo al que pertenece; DASUTeN se modela como órgano, no como atributo de una lista. El puesto indica si permite limitar por claustros y si permite limitar por departamentos; ambas capacidades son independientes.
- Las agrupaciones, nombres y números de lista y apoderados no son parámetros reutilizables: se registran como presentaciones propias de cada elección.
- El modelo histórico `Partido` se conserva únicamente por compatibilidad con registros anteriores y no participa del nuevo flujo de parámetros.
- En cada elección, un filtro de claustros desactivado incluye todos los claustros y uno activado permite elegir un subconjunto. El filtro de departamentos funciona del mismo modo y no exige activar el de claustros. Si ambos están activos se combinan; si ambos están inactivos se incluyen todos los alcances disponibles.
- El código de presentación identifica una lista y su alcance dentro de la elección. El número de lista puede repetirse en presentaciones o alcances distintos.
- Las listas y candidaturas pueden cargarse manualmente o mediante un CSV con previsualización y confirmación.
- Toda candidatura nueva debe vincularse con un elector del padrón activo de la elección. La carga manual y los CSV permiten buscar por tipo de documento y documento (DNI, CUIL o LEGAJO). DNI/CUIL exigen coincidencia de `Elector.tipo_documento` y del número almacenado actualmente en `Elector.dni`; LEGAJO consulta exclusivamente `Elector.legajo`. No se deriva un CUIL a partir de un DNI. Su claustro y, cuando el puesto lo exige, su departamento deben coincidir con los de la lista.
- La carga manual muestra el nombre encontrado antes de guardar, sin permitir editarlo; esa consulta no crea candidaturas. Se revalida el padrón al guardar y al confirmar la importación. Los CSV anteriores con columna `dni` mantienen compatibilidad y se interpretan como tipo DNI.
- El nombre y el correo de la candidatura se toman del elector; no se cargan como identidad independiente. El identificador de persona queda únicamente para preservar datos históricos.
- Una misma persona puede integrar más de una candidatura. Si su DNI aparece en presentaciones competidoras, la importación lo permite pero genera una advertencia para revisión de la Junta.
- Las candidaturas históricas que no tengan elector asociado se conservan sin borrado automático, pero no pueden volver a guardarse mediante los flujos de alta o edición sin vincularlas al padrón.

## QR

- El objetivo funcional es sustituir el legajo por DNI antes de aplicar la protección criptográfica.
- El DNI no debe exponerse en claro.
- Base64 no se considera cifrado.
- Debe verificarse el mecanismo criptográfico real del código existente.
- Si se usa DNI en el payload, debe existir cifrado apropiado y separación de claves.
- El servidor debe validar siempre elección, mesa, identidad/registro de padrón, firma y reglas de negocio.

## Keycloak

- El proveedor institucional será Keycloak.
- No se debe confiar en un JWT por el solo hecho de decodificarlo.
- Debe validarse criptográficamente antes de utilizar sus datos.
- Validar firma, `iss`, `aud`, `exp` y algoritmo permitido según la configuración institucional.

## Notificaciones

Debe existir una entidad de configuración/plantilla sin destinatario y otra entidad por envío.

La entidad de envío debe contener:

- destinatario;
- fecha de programación;
- fecha de envío;
- estado;
- error, si corresponde;
- estado o fecha de lectura interna.

Reglas:

- Toda notificación se envía por correo electrónico.
- Toda notificación se muestra también dentro de la aplicación web.
- La notificación interna muestra el mismo contenido del correo.
- El módulo interno administra plantillas, programación, estados, historial y lectura.
- El envío efectivo puede delegarse a un proveedor externo mediante un adaptador desacoplado.
- Los envíos pueden pertenecer a un usuario local o a un elector del padrón.
  Los electores autenticados por Keycloak no necesitan una cuenta en `auth.User`
  para consultar sus mensajes; el listado, el detalle y el contador de no leídas
  utilizan la misma identificación del destinatario.
- La primera resolución de un justificativo genera una notificación persistente,
  con asunto y contenido renderizados compartidos por correo y web. Se conserva
  el comportamiento de no reenviar ni duplicar el aviso al editar esa resolución.
  La notificación interna permanece disponible si el correo falla o falta una
  dirección; el envío registra el error y no se marca como enviado.
- No se reconstruyen avisos de resoluciones anteriores a esta integración: esos
  correos no conservaron una copia persistente del contenido enviado.

## Catálogos administrativos, mensajes y emisión de QR

- Los catálogos reutilizables son sede, claustro, departamento, turno, fecha administrativa, tipo de justificativo y plantilla de mensaje.
- Todos admiten alta, edición, activación y desactivación. No existe eliminación física desde la gestión web.
- Una fecha administrativa define el alcance y criterio base de destinatarios. Sus variantes de comunicación solo pueden reducir ese alcance.
- Las plantillas usan texto plano y un conjunto controlado de variables; no incluyen DNI, legajo ni adjuntos.
- Las plantillas automáticas o transaccionales no pueden seleccionarse en la pantalla de envío manual.
- El calendario por elección y el motor de envíos automáticos quedan fuera de esta entrega. Se conserva temporalmente el calendario electoral existente.
- El calendario administrativo reutilizable no ofrece «Exhibición del padrón provisorio» ni «Publicación del padrón definitivo». Sus definiciones y comunicaciones existentes se desactivan sin borrar los registros históricos ni las plantillas de notificación; las fechas ya programadas se conservan, pero no se muestran ni cuentan como hitos configurables.
- Las mesas automáticas se calculan para toda la elección usando la sede electoral asignada, agrupando por claustro, departamento cuando corresponda y sede. «Sede donde cursa» no determina la mesa.
- El cálculo automático se dispara al cambiar el máximo de electores por mesa o al recalcular las sedes electorales. Solo se aplica cuando todos los claustros tienen máximo configurado y sus electores activos tienen una sede electoral asignada; si no, conserva la distribución anterior e informa lo pendiente.
- El recálculo reemplaza únicamente mesas automáticas y asignaciones de padrón; conserva las mesas manuales. Se realiza como operación atómica para todos los claustros y no asigna autoridades.
- Los futuros flujos de solicitud de cambio de sede y asignación de autoridades deberán actualizar el destino del mismo elector y disparar el recálculo; no crearán un segundo registro de elector.
- Las mesas y el padrón pueden ajustarse hasta la primera emisión de QR de la elección.
- Cada `RegistroPadron` conserva la fecha de emisión y el número de mesa incluido en su QR.
- Después de emitir un QR no se permite reimportar el padrón ni regenerar automáticamente las mesas de la elección.
- Volver a producir el mismo QR para la misma mesa no cambia su primera marca de emisión; producirlo para otra mesa se rechaza.

## Asignación de sede electoral desde el padrón

- Cada elector tiene un único `RegistroPadron` por elección; no se define prioridad entre claustros para una misma persona.
- La sede electoral se configura por claustro y sus alcances departamentales, sin depender de los cargos o listas que se votarán.
- Si un alcance tiene una sola sede activa habilitada, se le asigna automáticamente. Si tiene varias, se evalúan reglas ordenadas; cada regla define una única sede destino y puede aplicarse a todos los alcances con varias sedes o a varios alcances seleccionados.
- Para un elector cuyo departamento no tenga habilitada la sede destino de una regla, esa regla se omite y se evalúa la siguiente. No se reemplaza por una sede distinta.
- Si ninguna regla aplicable coincide en un alcance con varias sedes, la asignación queda pendiente para revisión; no se elige una sede arbitrariamente.
- El cálculo produce una asignación provisional por elector y no modifica «Sede donde cursa», ni genera listas o QR. Si el alcance tiene una sola sede activa habilitada, el sistema la asigna automáticamente y no requiere reglas. Solo los alcances con más de una sede necesitan reglas; si ninguna regla aplicable coincide, la asignación queda pendiente. Al calcular mesas se revisan primero las asignaciones de sede. Agregar o quitar sedes vuelve a evaluarlas y recalcula las mesas automáticamente cuando todos los requisitos están completos. Si el cambio deja asignaciones pendientes, se quitan las mesas automáticas obsoletas del alcance afectado y se informa el motivo; las mesas manuales y las vinculadas a QR, participaciones o autoridades se protegen.
- Las prioridades de reglas se mantienen consecutivas desde 1. Al agregar, eliminar o reordenar una regla, el sistema recalcula automáticamente las sedes y mesas; no se requiere un botón manual de cálculo. Confirmar o vaciar un padrón, cambiar sus datos usados por reglas, habilitar/quitar departamentos o sedes también actualiza las asignaciones afectadas. Cambiar el máximo de electores por mesa recalcula las mesas automáticamente; no altera por sí solo la sede electoral asignada.
- El padrón completo de un claustro puede vaciarse mediante confirmación explícita mientras la elección esté en En preparación. Se eliminan sus registros y asignaciones calculadas, además de mesas automáticas que queden vacías. Las identidades de electores sin registros en otros padrones, candidaturas históricas ni perfiles de usuario también se eliminan, liberando sus DNI y legajos; se conservan las que siguen vinculadas a esos datos. Se mantienen el historial/archivos de importación y las mesas manuales. Las importaciones confirmadas de ese ciclo pasan a mostrarse como «Padrón eliminado»; las previsualizaciones y rechazos no cambian. La operación se bloquea ante emisiones QR o datos dependientes (participaciones, justificativos, autoridades o candidaturas) y queda auditada.
## Flujo actualizado de autoridades de mesa

- El padrón incorpora `Turno` junto a `Sede donde cursa`. Si se indica sede, el turno es obligatorio; si no se indica sede, el elector no tiene restricción de cursada por campus/horario. No se infieren turnos para filas históricas.
- Los cupos de autoridades de mesa se configuran por claustro y turno únicamente para titulares. Se registra el faltante cuando la nómina no alcanza; no hay suplentes de mesa.
- El CSV de autoridades solo contiene tipo de documento, documento y/o legajo. La identidad, departamento y elegibilidad se resuelven desde el padrón activo del claustro.
- Las importaciones de nómina conservan el archivo, su huella, usuario, fecha, cantidad válida, estado y errores para consulta en el historial del claustro. La previsualización no aplica asignaciones; confirmar las registra y cancelar conserva el historial.
- La selección manual busca por documento, legajo o nombre y agrega a la misma nómina que el CSV. Cada cambio confirmado recalcula las asignaciones completas.
- Se prioriza cubrir una titular por mesa y turno; luego se distribuyen las titulares restantes hasta el máximo. La distribución es pareja entre mesas.
- La autoridad debe pertenecer al mismo claustro, departamento y sede electoral habilitada; se prioriza su mesa de elector. No puede tener turno laboral superpuesto con su cursada. Puede trabajar en la sede donde cursa y se prefiere esa sede entre alternativas equivalentes; esta regla sustituye la prohibición anterior.
- Si la cobertura exige cambiar sede de trabajo, el sistema propone el traslado para confirmación de la Junta y limita destinos a sedes habilitadas del mismo alcance. Se conservan sede y mesa electorales; no se regenera el padrón por un traslado laboral.
- Al aprobar la justificación de una autoridad titular, su puesto queda vacante; no se promueve automáticamente a otra persona. Si hay titulares en otra mesa del mismo departamento, sede y turno, y esa mesa conserva al menos un titular, se propone el traslado para confirmación de la Junta. La persona conserva su mesa de votación y se notifica el cambio de mesa de trabajo. Si no hay propuesta compatible, la vacante continúa visible. Rechazar la justificación conserva la designación. Las asignaciones de suplentes de mesa existentes se eliminan por decisión explícita y no se crean nuevas.
- Quitar una designación permite liberar la asignación actual o excluir al elector de futuras distribuciones de toda la elección. No se crean usuarios o identidades al asignar autoridades.

## Confirmación de notificaciones a ausentes

- El administrador de junta confirma explícitamente el envío desde el tablero de participación, después de que todas las mesas de la elección estén procesadas.
- La acción se rechaza si existe alguna mesa pendiente o en proceso, si no hay mesas, si la elección no está en curso o si ya se confirmó el envío.
- Se notifica únicamente a los electores activos con un `RegistroParticipacion` en una mesa procesada; en el flujo vigente, el escaneo de su QR es el registro de ausencia.
- La confirmación y la creación de notificaciones se registran una sola vez por elección. Los avisos quedan disponibles en la aplicación aunque el correo no pueda enviarse; el resultado de correo se informa y audita.

## Presentación de justificativos por electores y autoridades

- La presentación de justificativos se habilita únicamente para la elección actual cuando se encuentra publicada (`PREPARADA`) o en curso (`ABIERTA`).
- La misma regla aplica a electores y autoridades de mesa; el servidor rechaza envíos aunque se intente omitir la restricción de la interfaz.
- No se habilita la presentación en elecciones en preparación, finalizadas ni cuando no existe una elección actual con padrón activo para la persona.
- La casilla «Voté, pero aparezco como ausente» permite reclamar una ausencia
  a votar. Solo se ofrece si la persona tiene una ausencia registrada
  (`RegistroParticipacion` por escaneo de QR) y todavía no presentó un
  justificativo de ausencia a votar. Al marcarla se ocultan «Ausencia a
  justificar» y «Tipo» y aparece «Perdí el comprobante de votación»; el
  servidor fija la ausencia a votar y no asigna tipo. Las descripciones de
  ambas casillas se muestran al pasar el cursor. Admite comprobante PDF/imagen
  o la declaración de comprobante extraviado junto con un comentario para
  revisar manualmente el padrón.
- Si el elector adjunta una imagen JPG/PNG del troquel, el sistema lee el QR y
  verifica la firma, la elección y el identificador del elector. El resultado
  (válido, no válido, sin QR detectado, revisión manual para PDF o comprobante
  extraviado) se muestra a la Junta, que puede volver a validarlo. Un resultado
  no válido no impide la presentación.
- La validación automática no modifica la ausencia. Solo cuando el
  administrador o el administrativo de junta aprueba el reclamo se elimina el
  `RegistroParticipacion`, con copia en el justificativo y evento de auditoría.
  Si la resolución cambia a rechazada, la ausencia se restaura. Mantiene el
  límite de una presentación por tipo de ausencia y la validación de adjuntos.

## Resolución de solicitudes de cambio de sede

- Cada elector puede registrar una única solicitud de cambio de sede por elección, independientemente de su estado (pendiente, aprobada o rechazada).
- El filtro por estado afecta solo el listado, incluso en modo lectura. Los
  resúmenes y las acciones masivas continúan abarcando todas las solicitudes
  pendientes; la cantidad y el estado del listado filtrado se muestran explícitos.
- La gestión muestra la cantidad actual de mesas de cada sede habilitada para la elección y una estimación de las mesas adicionales necesarias para las solicitudes pendientes.
- El administrador de junta puede aprobar solicitudes agregando como máximo una cantidad total de mesas nuevas definida en el formulario. El límite se aplica a toda la elección, no por sede.
- Al elegir la acción con límite, se informa cuántas mesas nuevas se crearían si se aceptaran todas las solicitudes pendientes y se solicita el máximo total permitido antes de confirmar.
- La resolución masiva ofrece una sola acción limitada, con máximo global de mesas nuevas; no se ofrece un límite independiente por sede. La tabla por sede es informativa.
- Las solicitudes que no puedan asignarse a una mesa existente ni crear una mesa sin superar el máximo permanecen pendientes para una resolución posterior.
- Una mesa existente solo se considera disponible si no alcanzó el máximo de electores por mesa configurado para el claustro. Si todas las mesas de la sede están completas, se crea otra únicamente si la acción y el límite lo permiten.
- En la pantalla de resolución, las acciones se ubican a la izquierda y el resumen de mesas por sede a su derecha; en pantallas angostas se apilan.

### Modalidades de asignación (octubre de 2026)

- El flujo configura turnos y cupos y ofrece sorteo aleatorio o nómina común por archivo. La selección manual se ofrece desde cada mesa en todos los modos y no es una modalidad separada.
- Al repetir el sorteo o cargar nómina se conservan las asignaciones vigentes; los cupos vacantes se completan. No se permite reducir cupos por debajo de las designaciones sin modificarlas explícitamente desde cada mesa.
- «Recalcular» solicita confirmación y vuelve a sortear desde cero: reemplaza todas las asignaciones, incluidas las manuales, y descarta sus destinos laborales fijados. Conserva el padrón electoral, turnos, cupos y exclusiones. Solo está disponible en modo aleatorio y antes de QR/apertura/avisos de ausencia. La misma persona puede resultar elegida otra vez por azar.
- «Eliminar todas las asignaciones», al final del detalle del claustro, requiere confirmación y vacía las autoridades sin volver a distribuir. Elimina asignaciones y roles de autoridad de sus mesas, limpia selecciones manuales, destinos laborales y marcas históricas de reacomodo del padrón. Conserva personas, mesas de votación, nómina y exclusiones, modo, turnos y cupos. No afecta otros claustros y respeta los mismos bloqueos por QR, estado electoral y avisos de ausencia. La operación es atómica, queda auditada y solo admite POST autorizado con CSRF y confirmación explícita.
- El detalle mantiene una tabla compacta con columnas Mesa, Departamento, Sede, Turno, Titulares y Autoridades. Agrupa turnos por mesa, muestra cupos como «1 de 2» y despliega las personas a pedido. Permite combinar filtros de departamento, sede y cobertura del claustro; conserva filtros al paginar hasta 25 mesas. Filtrar no cambia el alcance de las operaciones de distribución o eliminación.
- La cobertura se maximiza con prioridad para un titular por mesa/turno y luego los titulares restantes. «Sortear» optimiza los lugares libres conservando las asignaciones válidas y las selecciones manuales; «Recalcular» optimiza todo el plantel. Si la conservación limita la cobertura, se informa sin mover autoridades automáticamente.
- El azar desempata tanto personas compatibles como cupos de igual prioridad dentro de cada ronda; la escasez no debe favorecer siempre a los primeros turnos o mesas por su orden de listado.
- Cada persona cuenta para un único cupo. El guardado verifica que la solución y las filas persistidas coincidan; un error revierte toda la operación, incluidas las selecciones previas. La auditoría distingue completar/recalcular y registra las asignaciones anteriores/resultantes y las vacantes con su contexto.

- Cada claustro elige entre sorteo por mesa y nómina común por archivo. No existe una modalidad de planilla con mesa, turno y función predeterminados; esos cambios se realizan desde el detalle de cada mesa.
- Se completan los cupos de titulares de **todos** los turnos y mesas en rondas parejas. Cada persona tiene como máximo una asignación en la elección. Se informan todos los cupos faltantes, no solamente mesas sin ningún titular.
- El sorteo usa el padrón activo, sin exigir cargar una nómina previamente. La selección por mesa fija persona, mesa y turno. No se eligen candidatos electorales activos ni personas excluidas.
- En nómina, sin opciones cada persona nueva trabaja en su mesa. «Votar en mesa distinta» permite asignarla a otra mesa de la misma sede, sin mover su mesa de votación, si su horario es compatible con un turno configurado. «Permitir cambio de mesa» reacomoda el padrón para que titulares voten en la mesa donde trabajan. «Permitir cambio de sede» habilita otra sede del mismo claustro y departamento; sin reacomodo solo se admite si la mesa destino respeta el orden alfabético y su capacidad sin desplazar a otras personas. No se traslada a quien cursa en su sede electoral de origen. Las opciones de reacomodo y mesa de votación distinta son excluyentes.
- La distribución de nómina se previsualiza y confirma antes de guardar. Tras cargar el archivo se comparan cinco alternativas y se elige una en la misma tabla, que informa titulares, personas sin asignar, vacantes y detalles de cambios de mesa y sede. La elección se revalida contra la previsualización al confirmar. Las mesas nuevas pueden confirmarse con autoridades pendientes y completarse en cargas posteriores sin eliminar asignaciones previas.
- Con «Permitir cambio de mesa», los titulares votan en su mesa de trabajo y quedan al final de su padrón; el resto se distribuye alfabéticamente respetando capacidad. Con «Votar en mesa distinta», la mesa electoral no se modifica y la asignación de autoridad puede quedar en otra mesa de la misma sede. Las mesas manuales y con datos vinculados se conservan. Antes de confirmar se revalidan los datos, y la operación es atómica.
- La configuración y la distribución se bloquean con QR emitidos y después de abrir la elección. También se protegen los avisos de ausencia frente a redistribuciones generales. La confirmación de reemplazo por la Junta se permite únicamente mientras la elección está Publicada.
- La edición manual desde el detalle de cada mesa agrega, reemplaza o quita designaciones y conserva las restantes. La regeneración automática del padrón se bloquea si existen autoridades asignadas.
- Los cambios de configuración, distribuciones, selecciones, reacomodos y reemplazos quedan auditados. No se crean identidades al asignar autoridades.

### Decisiones C/C confirmadas el 23 de octubre

Las reglas anteriores sobre el destino electoral de titulares fueron actualizadas
por las decisiones de cambio de mesa y sede indicadas arriba.

- Se elimina la promoción de suplentes de mesa. La aprobación de una justificación deja vacante el puesto de autoridad titular y permite proponer a la Junta el traslado de un titular elegible de otra mesa compatible.
- El plan completo, criterios de aceptación y registro para retomar están en [plan_autoridades_tres_modos.md](plan_autoridades_tres_modos.md).

### Ajuste de modalidades de autoridades confirmado el 28 de octubre

- Se retira «Planilla de asignaciones» como modalidad. Los modos seleccionables son «Nómina común» y «Sorteo por mesa»; la edición manual continúa desde cada mesa.
- Cada claustro configura un mínimo de titulares por mesa y turno, entre 1 y el máximo del turno. Tanto en nómina como en sorteo se priorizan los cupos mínimos en rondas antes de los adicionales, respetando la elegibilidad y las asignaciones conservadas. Una mesa solo puede ceder una autoridad si conserva ese mínimo. No se inicia una elección con justificativos de autoridad pendientes y no se reciben nuevos justificativos de autoridad durante la jornada; las ausencias a votar conservan su propio flujo.
- La adaptación de vacantes mediante traslados corresponde después de confirmar las autoridades definitivas y aprobar las justificaciones de ausencia. La confirmación requiere resolver las solicitudes de cambio de sede pendientes, pero no espera al vencimiento de su plazo; al confirmar se cierra la recepción de nuevas solicitudes, se fija un plazo de justificación y se convoca a los titulares.
- La publicación no requiere turnos de autoridad configurados, ya que la distribución aún es provisoria. La configuración de turnos sigue siendo obligatoria para iniciar la elección.
- El inicio se bloquea mientras alguna mesa y turno no alcance su mínimo. El recálculo conserva las mesas necesarias; tras importar un padrón se ejecuta automáticamente e informa las designaciones provisorias que quedan vacantes. Los recálculos manuales y las aprobaciones de cambio de sede muestran el impacto y se revalidan antes de aplicar.
- Al aprobar una justificación se intenta devolver al elector a su mesa anterior sin desplazar a otras personas; si hace falta reordenar, la Junta revisa y confirma la propuesta. No se contraviene una solicitud de sede aprobada ni se desplaza la mesa de votación de otra autoridad definitiva.
- En Nómina, «Votar en mesa distinta» permite asignar a una persona a otra mesa de la misma sede y mantener su mesa de votación. Solo se consideran turnos habilitados que no se superpongan con su cursada.
- Esta opción no se combina con «Permitir cambio de mesa» ni «Permitir cambio de sede». «Permitir cambio de mesa» conserva el reacomodo del padrón; «Permitir cambio de sede» también puede usarse sin reacomodo en los casos compatibles con el orden y la capacidad existentes.
- Al usar «Votar en mesa distinta» no se reordenan personas, no se crean ni eliminan mesas y no se modifica el padrón electoral. Se mantienen la previsualización, confirmación, prioridad de mesa propia y conservación de asignaciones vigentes.
- Una migración convierte configuraciones históricas de Planilla o selección manual a Sorteo, conserva ambas opciones previas y agrega la nueva opción desactivada. Las asignaciones ya guardadas no se modifican.
