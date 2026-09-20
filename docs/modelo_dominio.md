# Modelo de dominio objetivo

## Configuración

- `Sede`
- `Claustro`
- `Turno`
- `Departamento`
- `FechaAdministrativa`
- `TipoJustificativo`

`FechaAdministrativa` es una definición reutilizable con código estable,
modalidad y duración sugeridas, roles, alcance de claustros, criterio de
destinatarios y evento sugerido. La fecha concreta por elección continúa en
`FechaAdministrativaEleccion`.

`Departamento` tendrá como mínimo:

- `id`
- `nombre`
- `codigo`
- `activo`

## Elecciones

- `Eleccion`
- `EleccionSede`
- `EleccionClaustro`
- `EleccionClaustroSede`
- `EleccionClaustroDepartamento`
- `EleccionClaustroDepartamentoSede`
- `Mesa`

### Relaciones conceptuales

`Eleccion 1 --- N EleccionSede N --- 1 Sede`

`Eleccion 1 --- N EleccionClaustro N --- 1 Claustro`

`EleccionClaustro 1 --- N EleccionClaustroSede N --- 1 Sede`

`EleccionClaustro 1 --- N EleccionClaustroDepartamento N --- 1 Departamento`

`EleccionClaustroDepartamento 1 --- N EleccionClaustroDepartamentoSede N --- 1 Sede`

`EleccionClaustroDepartamento 1 --- N Mesa`

### Mesa

Campos conceptuales:

- `id`
- `eleccion`
- `eleccion_claustro_departamento`
- `sede_habilitada`
- `numero`
- `codigo`
- `activa`

Restricción obligatoria:

`UNIQUE(eleccion, numero)`

Por lo tanto, `K-001` y `E-001` no pueden coexistir en una misma elección.

## Electores y padrón

- `Elector`
- `RegistroPadron`

`RegistroPadron` representa la participación/habilitación del elector en una elección concreta y debe relacionarlo con su claustro, departamento, sede y mesa según corresponda.

La emisión de QR queda registrada en `qr_generado_en` y `numero_mesa_qr`. Esa
marca protege la correspondencia entre el papel emitido y la asignación de mesa.

## Autoridades

- `AsignacionAutoridad`
- `PreferenciaAutoridad`

Una autoridad es el mismo elector con una asignación adicional; no una persona duplicada.

## Participación

- `RegistroParticipacion`

Debe contemplar:

- elección;
- registro de padrón;
- mesa;
- fecha y hora;
- usuario registrador;
- método QR/manual;
- troquel, si corresponde;
- observación;
- contexto técnico mínimo.

No registra el voto.

## Partidos y candidatos

- `Partido`
- `OrganoElectivo`
- `CargoElectivo`
- `PuestoEleccion`
- `ParticipacionPartido`
- `ListaCandidatos`
- `Candidato`
- `ImportacionCandidaturas`

`CargoElectivo` es el puesto reutilizable, pertenece a un `OrganoElectivo` e indica
si permite filtrar claustros y departamentos de forma independiente. Los valores
concretos no forman parte del parámetro. `PuestoEleccion` representa cada alcance
resultante en una elección: un claustro sin filtro departamental o una combinación
de claustro y departamento, con cantidades de titulares y suplentes. Una misma
operación puede crear varios alcances. `ParticipacionPartido`
representa una presentación electoral propia de la elección y conserva código,
número y nombre de lista, claustro y apoderado. Su vínculo con `Partido` es opcional
y existe solamente para compatibilidad histórica.

`ListaCandidatos` vincula una presentación con un `PuestoEleccion`. `Candidato`
conserva sus datos identificatorios, tipo y orden; puede vincularse opcionalmente
con `Elector` y no requiere pertenecer al padrón. `ImportacionCandidaturas` conserva
la previsualización, errores, advertencias, usuario y confirmación de cada CSV.

## Justificativos

- `TipoJustificativo`
- `JustificativoAusencia`

## Notificaciones

- `PlantillaNotificacion`
- `ComunicacionFechaAdministrativa`
- `VarianteComunicacionFechaAdministrativa`
- `EnvioNotificacion`

La comunicación define referencia temporal, desplazamiento y hora sugerida. Sus
variantes enlazan plantillas por prioridad y por un criterio adicional
controlado. Esta estructura es configuración reutilizable: no ejecuta todavía
una programación automática por elección.

## Importaciones

- `ImportacionPadron`
- `FilaImportacion`, si se justifica

## Auditoría

- `EventoAuditoria`

## Propiedad de modelos por aplicacion

La modularizacion de dominio asigna cada modelo a la aplicacion que contiene su
comportamiento principal:

- `parametros`: `Sede`, `Claustro`, `Turno`, `Departamento` y `FechaAdministrativa`.
- `elecciones`: `Eleccion` y sus configuraciones de sedes, claustros, departamentos,
  turnos y fechas administrativas.
- `padron`: `Elector`, `RegistroPadron`, `ImportacionPadron` y
  `ErrorImportacionPadron`.
- `mesas`: `Mesa` y `AsignacionMesa`.
- `autoridades`: `CandidaturaAutoridad`, `AsignacionAutoridad` y
  `PreferenciaAutoridad`.
- `partidos`: `Partido`, `OrganoElectivo`, `CargoElectivo`, `PuestoEleccion`,
  `ParticipacionPartido`, `ListaCandidatos`, `Candidato` e `ImportacionCandidaturas`.
- `justificativos`: `TipoJustificativo` y `JustificativoAusencia`.
- `notificaciones`: `PlantillaNotificacion`, `ComunicacionFechaAdministrativa`,
  `VarianteComunicacionFechaAdministrativa` y `EnvioNotificacion`.
- `asistencia`: `RegistroParticipacion`.
- `usuarios`: `PerfilUsuario` y `AsignacionRol`.
- `auditoria`: `EventoAuditoria`.

Los modelos trasladados conservan sus tablas fisicas historicas `elecciones_*`.
Las migraciones de modularizacion modifican el estado de Django sin recrear,
renombrar ni eliminar esas tablas. Tambien actualizan los `ContentType` para
preservar los permisos asociados a los modelos existentes.
