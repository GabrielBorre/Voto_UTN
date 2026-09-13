# Decisiones funcionales confirmadas

## Aplicación de asistencia

- Es una aplicación web responsive.
- Se utiliza desde el navegador del dispositivo móvil.
- No existe una aplicación móvil nativa.
- El administrativo de junta registra la participación.
- La autoridad de mesa no registra participación.

## Elecciones, claustros, sedes y departamentos

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
- `numero` es único dentro de toda la elección.
- El prefijo del departamento no permite repetir números.
- `K-001` y `E-001` no pueden coexistir dentro de la misma elección.

## Autoridades

- Una autoridad de mesa es también un elector.
- No se crea una identidad duplicada.
- Debe existir previamente como elector.
- Debe pertenecer al padrón de la elección.
- Debe pertenecer al mismo claustro.
- No puede ser autoridad de otro claustro.
- Puede incorporarse por CSV o selección manual.
- Ambos mecanismos producen la misma asignación.
- Conserva las funcionalidades de elector.
- La autoridad de mesa no registra participación.

## Partidos y candidatos

- Un partido se registra una vez y puede participar en distintas elecciones.
- La participacion define el numero y nombre de lista dentro de una eleccion.
- Las listas se organizan por claustro y, cuando corresponda, por departamento.
- Un candidato puede vincularse opcionalmente con un elector existente.
- No es obligatorio que el candidato pertenezca al padron.
- Si el candidato esta en el padron de la eleccion, debe coincidir con el claustro y departamento de la lista.
- Una misma persona no puede integrar dos listas diferentes dentro de la misma eleccion.

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

## Catálogos administrativos, mensajes y emisión de QR

- Los catálogos reutilizables son sede, claustro, departamento, turno, fecha administrativa, tipo de justificativo y plantilla de mensaje.
- Todos admiten alta, edición, activación y desactivación. No existe eliminación física desde la gestión web.
- Una fecha administrativa define el alcance y criterio base de destinatarios. Sus variantes de comunicación solo pueden reducir ese alcance.
- Las plantillas usan texto plano y un conjunto controlado de variables; no incluyen DNI, legajo ni adjuntos.
- Las plantillas automáticas o transaccionales no pueden seleccionarse en la pantalla de envío manual.
- El calendario por elección y el motor de envíos automáticos quedan fuera de esta entrega. Se conserva temporalmente el calendario electoral existente.
- Las mesas se generan automáticamente desde el padrón y continúan siendo de consulta; no se incorpora un ABM manual de mesas.
- Las mesas y el padrón pueden ajustarse hasta la primera emisión de QR del claustro.
- Cada `RegistroPadron` conserva la fecha de emisión y el número de mesa incluido en su QR.
- Después de emitir un QR no se permite reimportar el padrón ni regenerar automáticamente las mesas del claustro.
- Volver a producir el mismo QR para la misma mesa no cambia su primera marca de emisión; producirlo para otra mesa se rechaza.
