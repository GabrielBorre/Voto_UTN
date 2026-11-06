# Autoridades de mesa: plan y registro de continuidad

Actualizado: 2026-10-23. Estado: implementación y pruebas automatizadas completadas;
pendiente de revisión visual del usuario y commit.

## Origen y autorización

Este documento recupera la conversación del 21 de octubre y las decisiones
confirmadas el 23 de octubre. El usuario autorizó documentar e implementar el
alcance completo. No depende de conservar una sesión. No hacer commit ni push
sin el circuito de revisión acordado. Conservar los cambios locales previos.

## Decisiones vigentes

Estas reglas sustituyen las descripciones anteriores incompatibles sobre
autoridades en `decisiones_funcionales.md` y el estado histórico de la etapa 7.

1. Configuración por claustro, con tres modos seleccionables:
   - Aleatorio: sortear electores elegibles de cada mesa para cubrir titulares
     y suplentes por turno. Tres titulares y un suplente requieren cuatro
     personas distintas por turno. Cada persona ocupa como máximo un lugar.
   - Manual por mesa: elegir elector, turno, función y orden de suplencia,
     desde pantalla o archivo con todas las mesas del claustro.
   - Nómina común: incorporar personas individualmente o por CSV/XLSX,
     distribuir priorizando mesa propia, misma sede y finalmente otra sede
     únicamente si se habilita y confirma el traslado.
2. Cubrir primero titulares de todas las mesas y turnos, en rondas parejas;
   después suplentes. Mostrar faltantes reales de ambos tipos, sin declarar
   cobertura completa por el solo hecho de guardar o importar.
3. Elector activo del mismo claustro y departamento, sin candidatura electoral
   activa. No crear identidades ni usuarios duplicados. No registrar participación.
4. No superponer trabajo con turno de cursada. Favorecer sede de cursada dentro
   de las prioridades de distribución. Un registro con sede de cursada sin turno
   requiere corregir el padrón; no inferir disponibilidad histórica.
5. Cambiar sede es optativo y exige confirmación de la Junta. Es un traslado de
   trabajo; no cambia por sí solo sede ni mesa de votación. Solo destinos
   habilitados del mismo alcance; no trasladar a quien cursa en la sede de origen.
   No quitar un titular necesario para cubrir otro destino. Revalidar propuesta,
   elegibilidad y cupo al confirmar; auditar origen y destino.
6. **Opción C confirmada: reacomodo mínimo de titulares.** Desactivado por defecto,
   solo para nómina común. Aprovechar asignaciones existentes; mover únicamente
   titulares que necesiten votar en su mesa de trabajo. El máximo de electores
   incluye autoridades; no reservar un cupo fijo ni restarlo siempre. Ejemplo:
   seis titulares, cuatro ya en su mesa: solo dos incorporaciones necesarias.
   Desplazar otros electores solo para liberar capacidad y dentro del mismo
   alcance y sede. El bloque final de titulares se ordena por apellido y nombre,
   separado del bloque general. Suplentes no se reubican, incluso al promoverse.
   No cambiar sede electoral mediante esta opción. Si no es posible respetar
   capacidad y alcance, informar y revertir toda la operación.
7. **Opción C confirmada: reemplazo separado del justificativo.** La autoridad
   informa que no asistirá. La Junta confirma el reemplazo desde autoridades,
   sin exigir presentación ni aprobación del justificativo. Promover al primer
   suplente disponible de la misma mesa y turno; compactar el orden restante.
   Si no hay suplente, conservar vacante visible. Confirmación idempotente,
   con usuario, fecha y auditoría. Aprobar o rechazar un justificativo no produce
   ni revierte reemplazos. No cambiar mesa electoral ni QR al promover.
8. Elección cerrada: solo consulta. Redistribuciones y reacomodo antes de apertura
   y de emisión de QR. El reemplazo operativo puede confirmarse con elección
   abierta o QR emitidos porque no altera el padrón. Permisos de Junta en backend,
   autoridad solo sobre su propia asignación, POST y CSRF para mutaciones.

## Dependencias y consumidores

- `autoridades/models.py`, migraciones, `forms.py`, `views.py`, `urls.py`,
  `services.py`, `distribucion.py`: configuración, nómina, validación y operaciones.
- Templates `autoridades/gestion_claustro.html`, `seleccionar_mesa.html`,
  `mis_asignaciones.html`: gestión de Junta y respuesta personal.
- `elecciones.EleccionClaustroTurno`: cupos y turnos; `parametros.Turno`:
  superposición de horarios.
- `padron.RegistroPadron`, `AsignacionSedePadron`, servicios de generación;
  `mesas.AsignacionMesa`: mesa de votación y marca de bloque final.
- `partidos.Candidato`: incompatibilidad en ambas direcciones.
- `justificativos/services.py`, vistas: resolución documental independiente.
- `usuarios` y `auditoria`: identidad existente, roles y trazabilidad.
- `reportes/services_pdf.py`: ordenar bloques sin alterar formato ni contenido QR.

## Subetapas y criterios de aceptación

1. [x] Recuperar y documentar decisiones, alcance y dependencias.
2. [x] Configuración persistente de modos y opciones, migraciones seguras,
   valores por defecto compatibles y validación de opciones por modo.
3. [x] Validar los tres modos, exclusiones, unicidad, prioridades, distribución
   pareja, faltantes y cambio de sede laboral optativo y confirmado.
4. [x] Selección manual y archivo completo por claustro, errores sin cargas
   parciales, capacidad y reacomodo mínimo; PDF con bloque final ordenado.
5. [x] Aviso personal de ausencia, confirmación de Junta, promoción idempotente,
   orden de suplencia, vacante, auditoría y separación de justificativos.
6. [x] Pruebas de reglas críticas, permisos y regresiones; migraciones aplicadas,
   documentación de resultados y archivos afectados.

## Verificación reproducible

Ejecutar en `VotoUTN`, con Python 3.12, Django 5.2 y PostgreSQL. En el entorno
Docker, anteponer `docker exec voto_utn_web` a cada comando:

```text
python manage.py check
python manage.py makemigrations --check
python manage.py migrate --plan
python manage.py test
```

Aplicar migraciones nuevas con `python manage.py migrate` y volver a comprobar
el plan. No eliminar ni reescribir migraciones existentes. No usar SQLite.

Pruebas funcionales exigidas: modos aleatorio/manual/nómina; todos los turnos;
cupos insuficientes; candidatos excluidos; turnos superpuestos; traslado apagado,
confirmado y obsoleto; capacidad del padrón; opción de reacomodo apagada y activa;
suplente conserva mesa al promover; importación inválida atómica; protección QR;
aviso sin promoción; confirmación sin justificativo; doble confirmación; suplente
ineligible; falta de suplente; justificativo aprobado/rechazado sin cambios de
plantel; elección cerrada; permisos y auditoría.

## Punto de partida y continuidad

El árbol ya tenía cambios sin commit al comenzar esta tarea: distribución,
formularios, selección por mesa, configuración, protección QR, PDF y migraciones
0005/0006 de autoridades, 0003 de justificativos, 0004 de mesas y 0012 de padrón.
No se consideran terminados por existir archivos: se contrastarán con las reglas
de este documento y las pruebas. La resolución de justificativos aún promovía
automáticamente suplentes y el traslado de sede aún alteraba el padrón.

Al retomar: leer primero este documento y las cuatro referencias obligatorias,
consultar `git status`, revisar resultados abajo y continuar casillas pendientes.
No volver a pedir decisiones ya confirmadas ni asumir que una prueba pasó.

## Resultados de esta entrega

- `check`: sin errores.
- `makemigrations --check`: sin cambios de modelo pendientes.
- `migrate`: aplicada `autoridades.0007_traslados_y_reemplazos_independientes`.
  Las migraciones anteriores del árbol ya estaban aplicadas al consultar el plan.
- `migrate --plan`: sin operaciones pendientes.
- Suite completa: 335 pruebas correctas, 105,953 segundos.
- Después de los últimos ajustes de exportación, reacomodo y pruebas adicionales:
  63 pruebas de autoridades correctas, 9,966 segundos.
- `git diff --check`: sin errores de espacios; avisos de normalización LF/CRLF.
- Se usó PostgreSQL del contenedor `voto_utn_web`, con una base de pruebas
  independiente `test_autoridades_plan_20261023`, porque la base habitual estaba
  siendo utilizada por otra sesión. Se conserva mediante `--keepdb`.
- No se hicieron commits, push ni despliegues. No se eliminaron archivos.

Comando para repetir la suite aislada:

```text
docker exec voto_utn_web python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); from django.conf import settings; settings.DATABASES['default']['TEST']={'NAME':'test_autoridades_plan_20261023'}; from django.core.management import execute_from_command_line; execute_from_command_line(['manage.py','test','--noinput','--keepdb'])"
```

### Archivos creados en esta continuación

- Este documento.
- `VotoUTN/apps/autoridades/reemplazos.py`.
- `VotoUTN/apps/autoridades/tests_reemplazos.py` y `tests_traslados.py`.
- `VotoUTN/apps/autoridades/migrations/0007_traslados_y_reemplazos_independientes.py`.
- `VotoUTN/static/js/explicacion-modo-autoridades.js`: explicación dinámica del modo seleccionado.

### Archivos modificados o integrados en esta continuación

- `autoridades/models.py`, `services.py`, `distribucion.py`, `views.py`, `urls.py`,
  `tests.py`, `tests_distribucion.py`: traslados laborales, reacomodo mínimo,
  respuesta personal, reemplazos independientes y CSV seguro.
- `justificativos/services.py`: resolución documental sin promoción automática.
- `padron/services.py`: evitar pérdida de avisos y traslados al regenerar mesas.
- Templates `autoridades/gestion_claustro.html`, `mis_asignaciones.html` y
  `gestion/base.html` (versión de caché de estilos):
  confirmación de Junta, resultado y explicaciones del circuito.
- `docs/decisiones_funcionales.md`, `modelo_dominio.md`, `plan_implementacion.md`,
  `autoridades_modalidades.md`, `registro_de_cambios.md`: reglas y continuidad.

La base de tres modos incluía archivos locales anteriores o concurrentes;
su inventario está en `autoridades_modalidades.md`. Revisar el diff completo
antes de un commit para no atribuir todos los cambios del árbol a esta sesión.

### Comprobación manual

1. Junta → configuración de una elección en borrador/preparada → autoridades
   → claustro. Configurar turnos y cupos. Al cambiar el selector de modo se
   guarda y aplica automáticamente; revisar el mensaje y la cobertura resultante.
2. Sorteo: comprobar que se usan personas de cada mesa, sin cargar nómina.
3. Manual: abrir una mesa, seleccionar titular/turno y suplentes en orden;
   exportar el archivo, completar funciones e importarlo. Una fila inválida
   debe impedir aplicar el lote entero. Filas sin función no borran selecciones.
4. Nómina: cargar personas, observar faltantes y activar reacomodo únicamente
   cuando se desee. Revisar capacidad y orden del bloque final en PDF.
5. Habilitar traslado, revisar y confirmar una propuesta. Comparar antes/después:
   cambia el destino laboral; sede y mesa de votación permanecen iguales.
6. Con identidad de autoridad, informar que no asistirá. Con Junta, confirmar
   reemplazo en «Asignaciones registradas». Comprobar suplente promovido, orden,
   usuario y fecha. Repetir confirmación no debe promover a una segunda persona.
7. Aprobar o rechazar el justificativo: no debe cambiar el resultado anterior.
   Probar ausencia sin suplentes y observar la vacante. Probar con QR emitido:
   el reemplazo sigue disponible y el padrón permanece inalterado.

### Límites operativos explícitos

- El traslado laboral entre sedes no mueve automáticamente el voto a esa sede.
  El reacomodo solo opera dentro de la sede electoral original.
- Después de un aviso se utilizan los reemplazos; se bloquea la redistribución
  general y la regeneración que borraría el historial de respuestas.
- Desactivar el cambio de sede o cambiar de modo descarta destinos laborales
  confirmados y vuelve a distribuir, antes de apertura/QR/avisos.
- El campo histórico `JustificativoAusencia.reemplazo_procesado_en` permanece
  por compatibilidad. No gobierna las nuevas confirmaciones operativas.
- Las pruebas de vistas comprueban respuestas y plantillas. No se realizó una
  revisión visual interactiva en navegador; corresponde a la revisión previa al commit.

### Claridad de los modos en pantalla

La pantalla de gestión por claustro muestra junto al selector solo la explicación
del modo elegido. Cambia inmediatamente al modificar la selección, antes de
guardar; al cargar la página refleja el modo persistido. El cambio de modo se
guarda y aplica automáticamente. Los ajustes adicionales de nómina se guardan
con su propio botón. Las reglas comunes se
muestran por separado. Las opciones de cambio de sede y reacomodo solo aparecen
en nómina común; se desactivan al cambiar a otro modo. Nóminas y detalle de
asignaciones se paginan separadamente, con 25 personas y 25 mesas por página.
La tabla de asignaciones tiene una fila por mesa y agrupa sus turnos y personas.
Implementado en `templates/autoridades/gestion_claustro.html`,
`static/js/explicacion-modo-autoridades.js`, `static/css/gestion-electoral.css`
y la vista de autoridades.

### Ajustes manuales disponibles en todos los modos

El modo configurado sigue determinando la distribución general. Desde el panel
de cualquier claustro se puede entrar a cada mesa y fijar manualmente un elector,
turno y función, y elegir la designación a reemplazar si el cupo está ocupado.
La acción solo modifica esa elección y mesa; no cambia el modo general. La
selección queda guardada en los campos manuales existentes de
`CandidaturaAutoridad` y el algoritmo la respeta en recálculos futuros. No requiere
migración. El archivo masivo sigue reservado al modo de selección por mesa. Al
cambiar a ese modo desde sorteo o nómina, las asignaciones vigentes se convierten
en la selección inicial fija; después se pueden seguir editando por mesa o archivo.
El acceso «Editar» vive en cada fila del detalle paginado de asignaciones; no se
agrega un listado separado de enlaces por mesa.

## Ajuste posterior: dos modos y mesa de votación distinta

Decisión confirmada el 28 de octubre de 2026: el modo «Planilla de asignaciones»
se retira. Se mantienen Nómina común por archivo y Sorteo por mesa; la edición
manual sigue disponible desde el detalle de cada mesa.

En Nómina, la nueva opción «Votar en mesa distinta» permite a una autoridad
trabajar en otra mesa de la misma sede y turno compatible sin mover su mesa de
votación. Es excluyente con «Permitir cambio de mesa», que conserva el reacomodo
del padrón, y con «Permitir cambio de sede». Los modos históricos Planilla y
selección manual se migran a Sorteo sin alterar las designaciones ya guardadas.
