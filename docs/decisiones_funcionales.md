# Decisiones funcionales confirmadas

## Solicitudes de demostración de la instancia 2

- Se conserva el lote de hasta treinta estudiantes de Sistemas y se agregan
  hasta veinte solicitudes de estudiantes de Industrial y cuatro de Naval,
  estas últimas de Campus a Medrano. Con el padrón actual, el lote de 54
  requiere una mesa nueva de Sistemas y otra de Naval al aprobarlo completo.
  Se usa el padrón existente; no se agregan personas para completar cupos.
- Solo la instancia identificada con `INSTANCIA_DEMO=2` aplica este complemento.
  La publicación y el comando de carga comparten la misma selección, conservan
  solicitudes y resoluciones anteriores y no duplican personas al repetirse.
- Se excluye a Carlos Gómez y a quienes tengan una designación de autoridad.
  Se mantienen los controles de actividad, QR, sedes y registros adicionales.
  Si faltan solicitantes compatibles de un cupo, no se los sustituye por
  más estudiantes de Sistemas ni por otros departamentos.
- Las solicitudes no crean mesas hasta su aprobación ni modifican las
  autoridades. No se fuerza una mesa nueva si alcanza la capacidad existente.
  Los nueve titulares son un objetivo de cobertura, con mínimo de uno y máximo
  de tres por cada uno de tres turnos; no se alteran las mesas existentes ni se
  crean personas para alcanzar nueve.
  Los cuatro trasladables de Naval permiten intentar cubrir al menos un titular
  por turno en la mesa nueva; los otros seis permanecen en su mesa de Campus.

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
- Las elecciones Publicadas y En curso aparecen en el historial electoral.
  Antes de confirmar el escaneo de todas las mesas, muestran su estado actual
  («Publicada» o «En Curso», respectivamente), ambos con indicador azul. La
  confirmación actualiza únicamente la situación de los
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
  desde Fechas administrativas, solo extendiéndola y hasta confirmar las
  autoridades definitivas; cada extensión notifica a los electores activos que
  todavía no presentaron una solicitud. La nueva fecha no puede ser anterior
  a hoy; el campo propone el día siguiente al límite actual, o hoy si ese día
  ya pasó. Presentar una solicitud es opcional.
  A partir de la confirmación de autoridades el período queda cerrado. En el
  inicio del elector se muestra mientras la elección siga Publicada, no se
  hayan confirmado las autoridades y no haya vencido el plazo; cierra por la
  fecha o por la confirmación, lo que ocurra primero.
- Al confirmar las autoridades definitivas se inicia el período de eximición de
  autoridades de mesa y en esa misma acción se solicita su fecha límite. El
  administrador de junta puede modificarla desde Fechas administrativas
  mientras la elección siga Publicada, solo extendiéndola: debe ser posterior
  al límite vigente y no anterior a hoy. El campo propone por defecto el día
  siguiente al límite vigente. En el inicio del elector se muestra a las
  autoridades asignadas hasta la fecha límite inclusive o hasta que la elección
  pase a En curso, lo que ocurra primero. Cada modificación notifica a las
  autoridades confirmadas.
- Solo se pueden agregar o quitar claustros en **En preparación**. Los nuevos
  heredan las sedes de la elección; eliminar un claustro con datos vinculados
  se rechaza sin borrar padrones ni modificar sus alcances.
- El padrón imprimible con QR solo se genera **En curso**. Su emisión deja
  **todos** los cambios de sede de la elección en modo lectura, incluidos los
  rechazos individuales y masivos. No se permite rehabilitar cambios de
  configuración en curso ni invalidar los QR impresos desde ese flujo.
- Todas las páginas del PDF del padrón imprimible, incluidas las carátulas
  de mesa, llevan la marca de agua «Demo Proyecto Final» y «VOTO UTN» en dos
  renglones, en todas las instancias.
  Se dibuja detrás del contenido y del fondo blanco de los QR para preservar
  su lectura; no modifica los códigos, las asignaciones ni la paginación.
- Todas las páginas del PDF de boletas llevan esos mismos dos renglones,
  centrados en cada uno de los ocho octantes y detrás de sus marcos y contenido.
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
- Una elección finalizada queda en modo de consulta. Como excepción operativa,
  el administrador de junta puede asociar a una lista un puesto que ya estaba
  habilitado para esa elección y claustro. Esta acción no crea ni habilita puestos,
  no modifica candidatos ni otros datos de la lista. El resto de los datos,
  alcances, fechas administrativas, padrón, mesas, autoridades, candidaturas y
  resoluciones de justificativos permanece bloqueado. El historial conserva el acceso de consulta; el
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

- La identidad electoral se valida dentro de la elección que se está importando, no globalmente. DNI y legajo deben identificar al mismo elector si ya existe en el padrón de esa elección y son únicos dentro de esa elección; la misma combinación de identificadores puede corresponder a registros de electores independientes en elecciones distintas.
- La importación no reutiliza una identidad encontrada únicamente en otra elección. Si DNI y legajo no existen en el padrón de la elección actual, crea un registro de elector para esa elección aunque los identificadores aparezcan en padrones históricos.
- La previsualización muestra electores en el archivo, electores nuevos para incorporar, electores ya incluidos en el padrón y errores. Los existentes se identifican por la coincidencia de DNI y legajo con el mismo elector en esa elección. Las cantidades de nuevos y existentes cuentan solo filas válidas; si hay errores, la importación completa queda bloqueada hasta corregirlos.
- La pantalla de gestión de padrones muestra por claustro la cantidad de electores con registro activo en esa elección.

## Autoridades

- Una autoridad de mesa es también un elector.
- Al asignar o trasladar autoridades, el registro elegido debe conservar el tipo de su mesa electoral: ordinaria a ordinaria y especial a especial, dentro del mismo alcance departamental. La regla también se exige al trabajar en otra mesa sin cambiar dónde vota, y antes de aceptar destinos laborales o selecciones fijadas. Una persona con registros de ambos tipos puede aportar el compatible, pero mantiene una sola designación por elección.
- Si la propuesta cambia la sede electoral de una persona, todos sus registros activos de esa elección se trasladan juntos a esa misma sede, preservando departamento y tipo de mesa. Esto también se aplica si el traslado se origina en una designación de autoridad desde su registro principal o desde uno adicional. No se modifica la sede de cursada y se mantienen los controles de capacidad, QR, destinos habilitados y solicitudes pendientes.
- La etiqueta visible «Autoridad de Mesa» requiere una asignación no rechazada
  en una elección Publicada o En curso con autoridades confirmadas. Antes de esa
  confirmación se muestra «Elector». Esta regla solo cambia la etiqueta visual:
  no modifica la navegación ni las funcionalidades asociadas a la asignación.
  Las asignaciones de elecciones en preparación o finalizadas no modifican el
  rol visible de Elector.
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

- El parámetro reutilizable es el puesto a elegir y el órgano o cuerpo al que pertenece; DASUTeN se modela como órgano, no como atributo de una lista. El puesto indica si es departamental o general, a qué claustros se asocia y cuántas personas titulares y suplentes se eligen en cada uno.
- Las agrupaciones, nombres y números de lista y apoderados no son parámetros reutilizables: se registran como presentaciones propias de cada elección.
- El modelo histórico `Partido` se conserva únicamente por compatibilidad con registros anteriores y no participa del nuevo flujo de parámetros.
- En Parámetros generales → Puestos a elegir, «Editar» concentra la configuración de cada puesto: órgano, alcance (departamental o general), claustros asociados y, por cada claustro, la cantidad de titulares y de suplentes (mínimo 1 de cada tipo). Un puesto departamental se genera una vez por cada departamento habilitado del claustro y solo admite electores de ese departamento; uno general se genera una vez por claustro y admite a cualquier elector del claustro, sin importar su departamento. La limitación a un departamento específico se retiró; los valores históricos se conservan sin afectar la generación. La edición ya no ofrece asociar claustros desde botones del listado.
- Los puestos de cada elección no se cargan, editan ni importan por CSV dentro de la elección. Las elecciones en preparación los generan y actualizan automáticamente a partir de los parámetros: al guardar un puesto, al agregar un claustro, al guardar sus departamentos, al ejecutar la semilla o con `python manage.py sincronizar_puestos_eleccion [id_eleccion]`. Los puestos sin listas que dejan de corresponder (claustro desasociado, departamento quitado) se retiran; los que tienen listas se conservan y las cantidades no se reducen por debajo de las candidaturas cargadas, condición que el formulario del puesto rechaza. Las elecciones publicadas, en curso y finalizadas no se modifican. Los órganos históricos se conservan como clasificación interna, sin ABM propio.
- El código de presentación identifica una lista y su alcance dentro de la elección. El número de lista puede repetirse en presentaciones o alcances distintos.
- Las listas y candidaturas pueden cargarse manualmente o mediante un CSV con previsualización y confirmación.
- El PDF de boletas agrupa los puestos por elección, claustro, número y nombre de lista y, para los puestos departamentales, por departamento. No se mezclan candidatos de distintos claustros. Los puestos sin departamento (como Consejo Directivo) se incluyen en la boleta del mismo claustro y lista. El PDF usa páginas legales apaisadas, con dos filas por página y cuatro columnas en este orden: Consejo Superior, Consejo Directivo, Consejo Departamental y Ciencias Básicas. Cada cuadrante ocupado contiene una boleta completa; las categorías sin candidaturas quedan vacías. Ciencias Básicas ocupa la cuarta columna para Docentes, Estudiantes y Graduados. Para Docentes y Estudiantes, Ciencias Básicas se incluye junto a cada departamento de la misma lista y claustro, sin generar un grupo de departamento independiente. En Docentes también se incluye en la repetición departamental. En Estudiantes la cuarta columna de la segunda fila física de cada página queda vacía, incluso si esa fila corresponde a la única boleta de Ciencias Básicas de otra lista. Si no hay otro departamento con candidaturas para esa lista, Ciencias Básicas se agrupa junto a sus puestos generales, sujeto a esa regla de ubicación. Para los demás claustros, la repetición departamental ocupa solo la tercera columna. DASUTeN se imprime en una fila independiente, solo en la primera columna, sin duplicarse entre departamentos. Las filas continúan en páginas adicionales manteniendo la grilla de dos por cuatro.
- Al crear una lista manualmente se pueden asociar en el mismo formulario uno o más puestos generados para el claustro. No se crean puestos desde la lista: si falta uno, se configura en Parámetros generales → Puestos a elegir. El listado de listas queda visible después de crearla y desde allí se abre la carga de candidatos. El detalle permite agregar otros puestos de forma opcional, o asociar el primero si la lista se creó sin puestos.
- La gestión web de listas comienza mostrando todos los claustros participantes. Al ingresar en uno se presentan las listas del claustro con el total de candidatos cargados y un acceso directo para cargar candidatos en cada una, además del formulario para crear listas. La carga de candidatos se abre desde la lista correspondiente. El detalle de cada lista informa, por puesto, titulares y suplentes cargados respecto de sus cupos; al cambiar de puesto desde la pestaña CSV, se conserva esa pestaña. La importación CSV de uno o varios puestos tiene su propia pestaña junto a carga manual y CSV del puesto seleccionado. «Editar candidatos» selecciona el puesto y dirige a su tabla de candidatos; la edición de una persona y la importación dirigen al formulario correspondiente. Cambiar entre pestañas conserva la posición de desplazamiento.
- Cada tarjeta de claustro incluye un desplegable informativo con los puestos activos asociados a ese claustro en Parámetros generales. La cantidad de puestos registrados en la elección es independiente: los departamentales se generan según los departamentos habilitados.
- Las asociaciones puesto-claustro existentes conservaron sus cantidades al migrar; sin antecedentes se usa 1 titular y 1 suplente. Las elecciones en preparación ya creadas se completan con el comando indicado.
- La semilla estándar carga los cupos iniciales por claustro: Consejero/a Superior (general, Docentes 15 y 15; Estudiantes, Graduados y No docentes 5 y 5); Consejero/a directivo/a (general, Docentes, Estudiantes y Graduados 5 y 5; No docentes 1 y 1); Consejero/a departamental para Docentes (5 y 5), Estudiantes (3 y 3) y Graduados (2 y 2); Consejero/a Ciencias Básicas general para Estudiantes (3 y 3) y Graduados (2 y 2); y Consejero/a DASUTeN (general, 2 y 2) para Docentes y No docentes. Para Docentes, Ciencias Básicas corresponde al puesto departamental ordinario de Z; la tabla de parámetros muestra ese cupo en la fila de Ciencias Básicas identificándolo como departamental, sin asociarlo al puesto general. Las cantidades ya editadas no se restablecen al volver a ejecutarla. Una migración actualiza solo los cupos solicitados y sus puestos generales en elecciones en preparación; rechaza reducciones que dejen candidaturas fuera del cupo y conserva las elecciones históricas. La migración anterior renombra los puestos conservando sus relaciones; si existen varios equivalentes, informa el conflicto sin fusionarlos. La semilla también rechaza conflictos o conversiones de Ciencias Básicas que afecten puestos departamentales en preparación. Ciencias Básicas (código Z) es un departamento ordinario: aparece en Departamentos y claustros, tiene sedes y su padrón se identifica con ese código. Los alcances exclusivos de puesto creados por versiones anteriores se convierten en ordinarios al seleccionar el departamento.
- Al crear una lista, los puestos que se pueden asociar aparecen en grupos desplegables estáticos por claustro y tipo de órgano (departamentales, directivos, Consejo Superior, DASUTeN, generales y otros) debajo del campo “Puestos de la lista”. Los puestos generales de un órgano departamental aparecen en «Generales», no en «Departamentales». Todos los grupos están disponibles sin depender de JavaScript; el servidor valida que solo se asocien puestos del claustro seleccionado.
- En un puesto departamental solo pueden postularse electores con registro activo en ese departamento; en uno general, cualquier elector activo del claustro, independientemente de su departamento. El servidor rechaza cantidades inferiores a 1 titular o 1 suplente al configurar el puesto.
- Al ejecutarse, la semilla restablece las asociaciones puesto-claustro y el alcance de los puestos estándar, y sincroniza las elecciones en preparación, sin eliminar puestos con listas ni candidaturas históricas.
- Las candidaturas pueden eliminarse mediante una acción explícita con confirmación. Eliminar una candidatura conserva el elector y su padrón, y registra la operación en auditoría. Las listas y candidaturas previamente inactivas pueden reactivarse desde sus tablas, pero no se ofrece desactivar desde esas pantallas. Los estados existentes se conservan.
- La importación CSV de candidatos admite el formato de un puesto seleccionado. Su plantilla incluye `puesto`, `departamento`, `tipo_documento`, `documento`, `tipo_candidatura` y `orden`; completa puesto y departamento según el alcance seleccionado, con departamento vacío para puestos generales. Los CSV anteriores sin esas columnas siguen admitidos, y los valores informados deben coincidir con el puesto seleccionado.
- Una lista también admite un CSV de uno o varios puestos con `puesto`, `departamento`, `tipo_documento`, `documento`, `tipo_candidatura` y `orden`, sin seleccionar puestos durante la importación. El departamento vacío identifica un puesto general. La pantalla permite consultar los puestos activos ya asociados a esa lista. Cada combinación debe identificar un único puesto activo asociado a la lista; si falta uno, hay que asociarlo antes de importar. La confirmación carga los candidatos atómicamente sin crear asociaciones ni reemplazar candidatos existentes. Las validaciones y la elegibilidad se vuelven a verificar al confirmar.
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
- El padrón completo de un claustro puede vaciarse mediante confirmación explícita mientras la elección esté en En preparación. Se eliminan sus registros y asignaciones calculadas, además de mesas automáticas que queden vacías. Las identidades de electores sin registros en otros padrones, candidaturas históricas, perfiles de usuario ni notificaciones también se eliminan, liberando sus DNI y legajos; se conservan las que siguen vinculadas a esos datos. Las notificaciones se mantienen con su destinatario, independientemente de su estado de envío y de la elección a la que pertenezcan. El resumen previo y la eliminación contemplan esos mismos vínculos. Se mantienen el historial/archivos de importación y las mesas manuales. Las importaciones confirmadas de ese ciclo pasan a mostrarse como «Padrón eliminado»; las previsualizaciones y rechazos no cambian. La operación se bloquea ante emisiones QR o datos dependientes (participaciones, justificativos, autoridades o candidaturas) y queda auditada.
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

- En la demostración, publicar genera hasta treinta solicitudes exclusivamente
  de Estudiantes sin designación de autoridad en ningún registro de la elección.
  Carlos queda reservado para su solicitud manual. Se eligen candidatos sin
  actividad ni QR y con otra sede habilitada para todos sus registros. Si no
  hay treinta, se crean las posibles sin informar faltantes. Se conservan
  solicitudes existentes y autoridades; un error revierte publicación y lote.
  Los planes fijos históricos siguen disponibles para el guion externo.

- «Aprobar» en una solicitud individual aplica directamente la resolución y el
  recálculo, sin pasar por «Revisar cambios de sede». Conserva los permisos,
  bloqueos por emisión de QR, auditoría y notificación al elector. Las
  aprobaciones masivas mantienen la revisión de su propuesta antes de aplicar.
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
- «Eliminar todas las asignaciones», al final del detalle del claustro, requiere confirmación y vacía las autoridades sin volver a distribuir. Elimina asignaciones, roles de autoridad de sus mesas y todas las candidaturas de autoridad del claustro, incluidas las excluidas; también quita sus selecciones manuales, destinos laborales y marcas históricas de reacomodo del padrón. Conserva personas, padrón, mesas de votación, modo, turnos, cupos e historial de archivos importados. Funciona aunque ya no haya asignaciones, para retirar candidaturas que siguen bloqueando el vaciado del padrón. La confirmación informa que también se elimina la nómina de posibles autoridades; se descartan las propuestas y comparaciones guardadas en la sesión, y la auditoría conserva las asignaciones y candidaturas eliminadas. No afecta otros claustros y respeta los mismos bloqueos por QR, estado electoral y avisos de ausencia. La operación es atómica, queda auditada y solo admite POST autorizado con CSRF y confirmación explícita.
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

## Emisión de QR y cambios de sede

- La emisión del padrón imprimible y de QR no exige que el plazo de cambios de sede esté vencido, pero requiere que no exista ninguna solicitud de cambio de sede pendiente en la elección.
- Las mesas conservan su tipo ordinario o especial después de emitir QR para alguno de sus registros.

## Mesas especiales por departamento adicional

- Una persona conserva una mesa principal y tendrá una mesa especial por cada departamento adicional, con registros de participación independientes.
- Todas sus mesas deben compartir la sede electoral del registro principal. Una mesa especial puede estar en una sede habilitada para otro departamento del mismo claustro, sin habilitar allí mesas ordinarias de su departamento.
- Una persona puede tener una sola designación de autoridad por elección, aunque tenga varios registros de padrón. La distribución debe rechazar una propuesta que la ocupe en más de un cupo.
- La importación acepta una fila por departamento, exige una fila principal y datos personales comunes consistentes; los datos académicos pueden variar. Una fila única sin principal explícito conserva la compatibilidad y se considera principal.
- La generación, el recálculo, las solicitudes, los traslados de autoridades y sus retornos distinguen los registros principales y adicionales y validan su sede conjunta. Si no existe una distribución segura con las mesas disponibles, la operación informa el conflicto sin aplicar un traslado parcial.
- Los conteos de personas de la importación y de la nómina no duplican identidades por sus registros departamentales.
- La persona presenta un solo justificativo de inasistencia a votar por elección. Su estado y resolución cubren todos sus registros activos marcados como ausentes, tanto principales como adicionales; los registros donde votó conservan su estado. También cubre ausencias de esa elección registradas posteriormente, sin presentar otra solicitud.
- Las ausencias como autoridad conservan su trámite separado. El reclamo «Voté, pero aparezco como ausente» conserva el alcance del registro y comprobante cuestionado: no anula ausencias de otras mesas.
- En el cálculo separado de padrones de votación, los cargos generales corresponden únicamente al registro principal; cada adicional recibe solo los cargos de su departamento. La detección de cargos duplicados se realiza por persona.
- Los avisos de publicación, de mesas al iniciar la elección y de ausencia se generan una vez por persona y elección. El aviso de inicio incluye todas sus mesas; el aviso de ausencia indica únicamente las mesas donde figure ausente.
- Al presentar «Voté, pero aparezco como ausente» se elige la mesa si hay varias ausencias. El servidor limita la selección a los registros activos de la propia persona en esa elección con ausencia registrada y sin solicitud previa para esa mesa. La firma y el identificador del QR se validan contra el registro elegido.


## Plantilla explicativa del padrón

- La plantilla descargable contiene once columnas de dominio, sin `TieneDiscapacidad` ni columna auxiliar `Instrucciones`. Usa el encabezado `Sede donde asiste`; el importador conserva las variantes históricas y el soporte opcional de discapacidad.
- Incluye cuatro registros ficticios de tres personas, departamentos variados y sede/turno presentes o vacíos. La cuarta fila repite la identidad de la tercera y conserva su departamento principal para ilustrar una mesa especial en otro departamento.
- Después de los ejemplos se agrega una fila vacía y una fila con descripciones, opciones y restricciones bajo cada columna. El archivo se prepara reemplazando los ejemplos y las descripciones por los datos del padrón. Por decisión posterior se retira la columna Instrucciones y su aviso; los archivos anteriores con esa columna vacía siguen siendo compatibles en CSV y Excel.
- Departamento y departamento principal deben corresponder a parámetros activos habilitados para el claustro en la elección; sede y turno deben existir y estar activos. Informar sede exige turno.
- `Nivel` indica el año o nivel de la carrera que cursa el estudiante o en el que dicta clases el docente. Se expresa como número entero y queda vacío cuando no corresponde; no es un catálogo parametrizable.


## Mensajes del autoguardado de configuración del padrón

- Al elegir fecha de votación y máximo por mesa no se muestran mensajes de estado bajo el botón dentro del recuadro de configuración, incluidos los de cambios pendientes, guardado en curso, resultado y fallo.
- Se conserva el botón Guardar configuración y el funcionamiento previo del autoguardado. La validación de campos, el procesamiento de mesas y el aviso al intentar salir con cambios que no pudieron guardarse mantienen su comportamiento.


## Posición de la página tras operar en la misma pantalla

- Los envíos de formularios y los enlaces de filtros o paginación que recarguen la misma ruta conservan la posición horizontal y vertical, aunque cambien los parámetros de consulta. Esto incluye agregar, eliminar y reordenar reglas de sede.
- Se captura la posición al abandonar realmente la página y se consume al cargar la siguiente. Cancelar una confirmación o hacer una operación sin navegación no deja una restauración pendiente.
- Una ruta distinta mantiene su navegación habitual; los enlaces a secciones explícitas conservan su ancla. El historial sigue utilizando la restauración nativa del navegador.
- El almacenamiento de sesión bloqueado o corrupto no interrumpe los diálogos ni el resto de la interfaz.


## Cambios de reglas rechazados por sedes protegidas

- Agregar, eliminar y reordenar reglas de sede y su recálculo forman una única transacción, con bloqueo de la elección y revalidación de permisos y estado antes de modificar datos.
- Si el cálculo de sedes rechaza el cambio por un registro protegido incompatible con su principal, se conservan la regla, sus prioridades y las referencias de asignación; la pantalla muestra el motivo en lugar de un error 500. Las protecciones de autoridades y cambios de sede aprobados se mantienen.

## Carga del módulo de conservación de posición

- La conservación de posición se carga desde un módulo independiente con URL versionada en las tres plantillas base. Se mantiene la URL única del módulo de diálogos para no duplicar sus instancias. La posición se restaura al terminar la carga de la página y en el siguiente cuadro de renderizado.

## Texto y departamentos de las reglas de sede

- El campo de condición se presenta como «Sede donde asiste», tanto al agregar como al consultar reglas existentes. Se conserva el identificador interno `sede_donde_cursa` y el dato de asistencia del padrón, distinto de la sede electoral asignada.
- Los controles de alcance se agrupan en «Ver departamentos afectados», un desplegable nativo que inicia cerrado. Abrir o cerrar no cambia selecciones ni envía el formulario. Se mantienen «Todos los departamentos disponibles» y la selección individual.
- Cuando un alta devuelve errores, el desplegable se muestra abierto, conservando los departamentos y mostrando sus errores. Se reutilizan los estilos del detalle de asignaciones y el JavaScript existente de selección, sin duplicar controladores.

## Función de la selección manual de autoridades

- La edición manual de una mesa no muestra un selector de función, dado que solo se admiten titulares. El formulario conserva el tipo como campo oculto, lo valida y utiliza Titular si no se informa.
- El reemplazo mantiene el turno y función de la designación original. Se conservan la validación de cupos, elegibilidad, horarios, permisos y la confirmación de asignación provisoria.

## Texto del botón de carga de nómina

- La carga de nómina de autoridades muestra «Validar archivo» al entrar y al cambiar de modalidad. Conserva el flujo existente de validación y revisión de la distribución antes de confirmar las asignaciones.

## Estado de las tarjetas de preparación por claustro

- Las tarjetas de Autoridades, Mesas y Puestos/listas/candidaturas evalúan todos los claustros participantes de la elección. Un claustro vacío no se excluye: su falta de padrón, mesas o candidaturas queda pendiente. Una elección sin claustros tampoco está lista.
- Mesas requiere padrón activo y configuración de fecha y máximo por claustro, mesas existentes, sede electoral resuelta y todos los registros activos asignados a mesas compatibles con elección, alcance, sede y tipo principal/adicional. Se informa si una mesa supera el máximo.
- Autoridades hereda los pendientes de padrón y mesas del claustro y exige turnos configurados y el mínimo de titulares activos en cada combinación de mesa y turno. Las autoridades rechazadas no cubren el mínimo. No se exige completar el máximo.
- Puestos/listas/candidaturas requiere padrón activo, puestos y presentaciones activos del claustro, listas con puesto activo de su mismo alcance y al menos un candidato activo por lista, válido en el padrón y dentro de los órdenes configurados. No exige llenar todos los cupos ni todos los puestos del catálogo. Las presentaciones sin claustro no completan otro claustro.
- Las tres tarjetas muestran cuántos claustros están listos y permiten desplegar el motivo por claustro. Se recalculan al consultar sin modificar datos ni cambiar las reglas de publicación, confirmación o inicio.
