# Autoridades: modalidades por claustro

Desde Configuración de elección → Autoridades → Claustro:

1. Configurar los turnos y cupos de titulares/suplentes por mesa y aplicar esos cambios.
2. Elegir un modo de asignación. Cambiar el selector no guarda ni ejecuta cambios.
3. En sorteo, pulsar el botón para cubrir vacantes. En nómina, subir el archivo,
   revisar la previsualización y confirmar. Las asignaciones anteriores se conservan;
   si una reducción de cupos las afecta, primero hay que editarlas manualmente.
   La edición manual está disponible desde cada mesa, en todos los modos.

En modo aleatorio, «Recalcular» solicita confirmación y genera una distribución
desde cero con los cupos guardados, reemplazando las asignaciones aleatorias y
manuales anteriores.
También descarta los destinos laborales fijados en selecciones o traslados previos;
conserva las exclusiones, el padrón, las sedes y mesas de votación y los horarios
de cursada. Puede elegir nuevamente a la misma persona por azar. La operación
completa se revierte si falla el cálculo o el guardado.

## Consulta de asignaciones

El listado conserva el formato de tabla, con columnas separadas para Mesa,
Departamento, Sede, Turno, Titulares, Suplentes y Autoridades. Cada turno tiene
una fila; las celdas de mesa, departamento y sede se agrupan. Los cupos se muestran
como «1 de 2». «Ver autoridades» despliega debajo del grupo una tabla con las
personas, titulares antes de suplentes por turno, y las acciones de reemplazo.

Se pueden combinar filtros por departamento, sede y cobertura (todas las mesas,
titulares faltantes, suplentes faltantes o cobertura completa). Las opciones de
departamento y sede pertenecen al claustro actual. La paginación conserva los
filtros y muestra hasta 25 mesas por página; filtrar vuelve a la primera página.
Estos filtros afectan al listado: las acciones de distribución y eliminación
mantienen su alcance sobre todo el claustro, indicado en la confirmación.

## Eliminar todas las asignaciones

Al final de la pantalla está «Eliminar todas las asignaciones». Pide confirmación
y deja las mesas de ese claustro sin autoridades, sin ejecutar un nuevo sorteo.
Limpia también las selecciones manuales y los destinos laborales
fijados. Se conservan el padrón, las mesas de votación, la nómina y sus exclusiones,
el modo, los turnos y los cupos. Permite comenzar una nueva asignación después.
Está disponible en cualquiera de los modos, con los mismos bloqueos por QR,
elección abierta/cerrada y avisos de ausencia. Se registra quién la ejecutó y
cuáles eran las asignaciones eliminadas.

## Sorteo por mesa

Selecciona entre electores activos de cada mesa, sin cargar una nómina. Excluye
candidatos electorales, personas excluidas y turnos incompatibles con la cursada.
Al volver a aplicar, conserva las asignaciones vigentes que siguen siendo elegibles
y ocupan un cupo habilitado; completa las vacantes y los cupos nuevos al azar.
Cuando hay varios titulares por mesa y turno, se conserva a cada persona en un
cupo distinto. Nunca se cuenta a una misma persona para cubrir varios cupos.

El cálculo utiliza caminos aumentantes iterativos: puede reorganizar elecciones
del nuevo sorteo para aprovechar personas con compatibilidad en varios turnos.
Prioriza un titular por mesa/turno, los titulares restantes y después suplentes.
Dentro de cada ronda de igual prioridad, sortea también el orden de los cupos
para no favorecer siempre los primeros turnos o números de mesa ante escasez.
Al completar, las asignaciones conservadas son restricciones fijas; solo
«Recalcular» puede reorganizarlas. El mensaje informa esa diferencia cuando
quedan vacantes.

La auditoría `autoridades.distribuidas` distingue `completar` y `recalcular`,
registra los totales persistidos, las asignaciones anteriores/resultantes
(registro, mesa, turno, función, orden) y el contexto de cada vacante.

## Ajuste manual dentro de cualquier modo

Desde el panel del claustro se puede abrir cualquier mesa y editar su selección
sin cambiar el modo general. Elegí la persona de esa mesa, turno y función; si
el cupo está ocupado, indicá cuál designación reemplazás. El ajuste queda fijado
para esa mesa y se conserva al completar vacantes; «Recalcular» descarta también
estas selecciones y comienza desde cero. Solo se modifica antes
de abrir la elección y emitir QR, con los controles de elegibilidad y auditoría.

## Nómina común

Cargar un archivo CSV o XLSX con documento o legajo de los electores disponibles.
Las nuevas filas se agregan a la nómina y las asignaciones anteriores se conservan.
El sistema calcula una propuesta antes de guardar y presenta titulares, suplentes,
personas sin asignar y cupos pendientes. La propuesta compara los resultados con
las distintas opciones de movilidad, e informa por claustro, departamento y sede
las mesas que se crearían o quitarían. Cancelar no guarda cambios; confirmar aplica
todo atómicamente y rechaza una propuesta si los datos cambiaron desde su cálculo.

Sin opciones, cada nueva autoridad se asigna a su propia mesa. «Votar en mesa
distinta» permite asignarla a otra mesa de la misma sede y conserva su mesa de
votación; el turno debe estar configurado y no superponerse con su cursada.
«Permitir cambio de mesa» conserva la regla de reacomodar el padrón para que los
titulares voten en la mesa donde trabajan. «Permitir cambio de sede» también
requiere esa opción y permite otra sede habilitada del mismo claustro y
departamento; no se traslada a quien cursa en su sede electoral de origen. Las
dos opciones de mesa son excluyentes. Entre soluciones con la misma cobertura,
se prioriza la mesa propia, luego otra mesa en la misma sede y finalmente otra
sede. Las opciones no mueven autoridades ya asignadas ni anulan sus destinos
confirmados.

Con «Permitir cambio de mesa», el padrón se reordena: titulares quedan al final
de la mesa de trabajo; se respeta el máximo por mesa, y mesas nuevas pueden
quedar con cupos pendientes para cubrir en cargas posteriores. Con «Votar en
mesa distinta», solo se mueve la asignación de autoridad: no cambia la mesa de
votación ni se agregan o quitan mesas. No se alteran QR emitidos. Las mesas
manuales o con datos vinculados se conservan.

## Avisos de ausencia y reemplazos

La autoridad informa que no asistirá desde «Mis asignaciones». En la tabla de
asignaciones del claustro, la Junta pulsa «Confirmar reemplazo». Se promueve al
primer suplente disponible de esa mesa y turno, se renumeran los restantes y se
registra quién confirmó y cuándo. Repetir la confirmación no promueve otra persona.
Sin suplente, queda la vacante. Los QR y mesas de votación se conservan, incluso
si el suplente vota en otra mesa. Puede confirmarse durante una elección abierta.

No se exige justificativo. Su aprobación o rechazo no altera el plantel. Tras
informar ausencias se bloquean redistribuciones generales para preservar estos
reemplazos. El plan completo y las decisiones confirmadas están en
[plan_autoridades_tres_modos.md](plan_autoridades_tres_modos.md).

## Archivos de esta ampliación

Creados:

- `VotoUTN/apps/autoridades/distribucion.py` y `tests_distribucion.py`.
- `VotoUTN/apps/autoridades/migrations/0006_candidaturaautoridad_mesa_manual_and_more.py`.
- `VotoUTN/apps/mesas/migrations/0004_asignacionmesa_autoridad_al_final.py`.
- `VotoUTN/apps/justificativos/services.py` y `migrations/0003_justificativoausencia_reemplazo_procesado_en.py`.
- `VotoUTN/templates/autoridades/seleccionar_mesa.html` y este documento.

Modificados:

- Autoridades: modelos, formularios, servicios, vistas, rutas, pruebas y plantilla de gestión por claustro.
- Mesas: modelo de asignación de elector.
- Padrón: protección de selecciones manuales al regenerar mesas.
- Justificativos: modelo y vista de resolución.
- Partidos: validación de incompatibilidad entre candidato y autoridad.
- Reportes: estado vigente de autoridades y orden del bloque final en PDF.
- Datos de demostración y pruebas de asistencia: referencias al estado vigente.
- Documentación: decisiones funcionales, modelo de dominio, plan y registro de cambios.

No se eliminan archivos ni migraciones anteriores. Se conservan los cambios
locales previos a esta ampliación.

## Verificación

```bash
docker exec voto_utn_web python manage.py check
docker exec voto_utn_web python manage.py makemigrations --check
docker exec voto_utn_web python manage.py migrate --plan
docker exec voto_utn_web python manage.py migrate
docker exec voto_utn_web python manage.py test --noinput --keepdb
```
