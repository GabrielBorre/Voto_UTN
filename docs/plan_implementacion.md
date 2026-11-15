# Plan de implementacion

## Estado actual

**Cierre de modularizacion completado**

El sistema conserva un unico proyecto Django y distribuye el dominio entre apps
propietarias. El detalle verificable de cada entrega se mantiene en
`docs/registro_de_cambios.md`.

## Etapas implementadas

### Etapa 0 - Auditoria y estabilizacion
**Estado:** completada

Dependencias compatibles con Python 3.12 y Django 5.2, PostgreSQL por entorno,
secretos fuera del repositorio y base de pruebas del QR.

### Etapa 1 - Unificacion de nomenclatura
**Estado:** completada

Dominio, contratos principales y migraciones utilizan nomenclatura en espanol.

### Etapa 2 - Modelo base definitivo
**Estado:** completada

Incluye parametros, relaciones electorales, mesas, electores y padron.

### Etapa 3 - Usuarios, roles y permisos
**Estado:** completada con autenticacion local de desarrollo

Incluye perfiles, asignaciones de rol, alcance por eleccion, sede y mesa, y
navegacion inicial por permisos. La integracion institucional con Keycloak queda
en el backlog externo.

### Etapa 4 - Integracion definitiva del QR
**Estado:** completada

El QR utiliza un identificador opaco de `RegistroPadron`, firma separada,
validacion de eleccion y mesa, registro atomico y prevencion de duplicados.

### Etapa 5 - Gestion de elecciones
**Estado:** completada

Incluye parametros, creacion, configuracion por alcance, ciclo de estados y
gestion de mesas.

### Etapa 6 - Padrones e importaciones
**Estado:** completada

Incluye CSV, previsualizacion, validacion, confirmacion, errores e historial.

Complemento de departamentos adicionales: implementado en `feat/padron-update`
con migraciones de unicidad, mesas especiales, sede compartida, traslados y QR
por registro. Incluye justificativo único por persona y elección, reclamo con
selección de mesa, notificaciones agrupadas por persona y cargos generales
exclusivos del registro principal. Las migraciones propias y las anteriores de
justificativos se aplicaron a la base habitual; la dependencia de lectura de QR
también está instalada en el contenedor habitual. La verificación actualizada
se registra en `docs/registro_de_cambios.md`.

### Etapa 7 - Autoridades de mesa
**Estado:** en actualización por las nuevas decisiones sobre titulares y confirmación definitiva

El flujo permite sorteo, selección por archivo o nómina común por claustro, con
cupos por turno y edición manual desde cada mesa. La nómina se calcula y
previsualiza antes de confirmarse; conserva las designaciones existentes y
permite reordenar padrones y mesas según las opciones de movilidad. Se eliminan
las suplencias de mesa y una vacante puede cubrirse mediante una propuesta de
traslado de un titular que debe confirmar la Junta. La confirmación definitiva
requiere que no haya solicitudes de cambio de sede pendientes, sin esperar al vencimiento del plazo;
cierra nuevas solicitudes, establece el plazo de justificación, registra y envía convocatorias y bloquea la
edición general. El inicio exige resolver los justificativos pendientes
de autoridades y los traslados respetan el mínimo configurado por mesa y turno.
El recálculo y la aprobación de cambios de sede muestran movimientos y vacantes
antes de confirmar. El retorno a una mesa anterior se aplica directamente si no
desplaza a otros electores; si requiere reordenar, se presenta a la Junta. Cuando
no existe una partición válida con las mesas existentes o hay datos protegidos,
se informa el conflicto para revisión.
El plan anterior de continuidad, las decisiones C/C y las verificaciones están en
[plan_autoridades_tres_modos.md](plan_autoridades_tres_modos.md).
El detalle de uso y archivos está en `docs/autoridades_modalidades.md`.

### Etapa 8 - Justificativos
**Estado:** completada

Incluye presentacion, documentacion, bandeja, resolucion y trazabilidad.

### Etapa 9 - Notificaciones
**Estado:** base operativa completada

Incluye plantillas, generacion de envios, procesamiento, historial y lectura
interna. Tambien incluye el catalogo reutilizable de fechas, comunicaciones y
variantes, 26 plantillas institucionales, vista previa y separacion entre uso
manual y futuro uso automatico. La configuracion del proveedor de correo de
produccion queda pendiente.

### Complemento - Catalogos institucionales y proteccion de QR
**Estado:** completado

Incluye ABM sin baja fisica de siete catalogos, carga estandar idempotente,
auditoria de cambios y marca persistente de emision de QR. La emision bloquea la
reimportacion y regeneracion automatica de mesas del claustro para preservar los
QR ya impresos. Las mesas siguen siendo automaticas y de solo consulta.

### Etapa 10 - Reportes y exportaciones
**Estado:** completada

Incluye exportaciones operativas de padron, mesas, participacion, autoridades,
justificativos y errores de importacion.

### Etapa complementaria - Partidos y candidatos
**Estado:** completada

Incluye presentaciones propias de cada elección, puestos configurables por alcance,
listas, candidatos nuevos vinculados obligatoriamente a un elector del padrón e importación CSV con
previsualización. La carga manual y CSV comparten búsqueda por DNI, CUIL o legajo,
con consulta del nombre antes del guardado y revalidación del padrón al confirmar.

### Cierre de modularizacion
**Estado:** completado

- Los modelos pertenecen a sus apps de dominio.
- Las vistas, formularios, servicios, URLs y administracion estan separados.
- Las plantillas funcionales utilizan namespaces de su app propietaria.
- Los comandos de padron y notificaciones pertenecen a sus apps.
- `elecciones` conserva el nucleo transversal y `seed_demo_data` como orquestador.
- La app inactiva `pagina_web` fue eliminada; sus maquetas se conservan.

## Backlog externo a la modularizacion

- Integrar Keycloak mediante OIDC y validar criptograficamente los JWT.
- Incorporar gestion web completa de usuarios y asignaciones de rol.
- Configurar y verificar el proveedor real de correo electronico.
- Implementar el calendario por eleccion y el motor de programacion/envio automatico.
- Implementar los flujos de cambio de sede, cambio de turno, justificaciones y capacitacion que consumiran las plantillas estandar.
- Ejecutar una auditoria visual integral de las pantallas y sus maquetas.
- Preparar configuracion, observabilidad y seguridad para produccion.

## Actualizacion de autoridades - 28 de octubre de 2026

- Se retira la modalidad Planilla de asignaciones y se migra su configuración histórica a Sorteo, conservando las asignaciones persistidas.
- Se agrega en Nómina la opción «Votar en mesa distinta», limitada a otra mesa de la misma sede y a turnos disponibles. Esta opción no reacomoda el padrón ni altera las mesas electorales.
- Se conserva separada la opción anterior de reacomodar el padrón y el cambio de sede. Ambas reglas de reacomodo no se combinan con «Votar en mesa distinta».
- La migración conserva los valores de reacomodo y cambio de sede existentes y agrega el nuevo indicador desactivado.

## Justificativo único para ausencias departamentales - 8 de noviembre de 2026

- Presentar una sola solicitud de ausencia a votar por persona y elección, aunque tenga mesas especiales. Revalidar el permiso y la inexistencia de otra solicitud bajo bloqueo de la elección.
- Compartir la resolución en todas sus ausencias registradas y conservar el estado de las mesas donde votó. Permitir presentar cuando únicamente figure ausente en una mesa especial.
- Mostrar el alcance en la revisión y en el detalle; aplicar la misma regla al historial, los indicadores y el CSV de infractores.
- Conservar separados los justificativos como autoridad y los reclamos sobre un comprobante específico. Verificar con pruebas integradas en PostgreSQL y ejecutar las comprobaciones generales.
