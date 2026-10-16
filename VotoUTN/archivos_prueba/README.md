# Archivos de prueba: padrones y autoridades

Las [variantes solo de alumnos](variantes_alumnos/README.md) incluyen archivos
separados para errores de importación, restricciones de cursada, distribución,
faltantes y cambios de sede, con instrucciones y resultados esperados.

Estos archivos sirven para una elección de prueba. La base local `1234` aportó los 500 registros de Estudiantes: se conservaron sus identificadores, nombres, correos y departamentos para que una nueva importación los reconozca. **El responsable del proyecto confirmó que los datos son inventados. Todos los CSV de prueba se incluyen en el repositorio para reproducir los escenarios.**

## Archivos disponibles

- `padron_estudiantes_500.csv`: los 500 electores de la base local. Las primeras 250 filas ordenadas por legajo tienen vacías `Sede donde cursa` y `Turno`; las otras 250 conservan la sede donde cursan y reciben un turno distribuido entre los turnos activos.
- `autoridades_estudiantes_500.csv`: nominación de los 500 electores como posibles autoridades. El CSV solo identifica personas; sede, turno laboral y mesa se determinan en la aplicación.
- `padron_docentes_50.csv`: 50 personas ficticias para probar Docentes, mitad sin sede/turno y mitad con Campus y turno.
- `autoridad_no_en_padron.csv`: identificador que no pertenece al padrón, para comprobar el rechazo de un archivo inválido. Cargalo por separado: la validación rechaza el lote completo si hay una fila inválida.

El padrón de Estudiantes conserva los departamentos de la elección local. Antes de importarlo en una elección nueva, habilitá todos esos departamentos para Estudiantes y las sedes Campus y Medrano. Deben estar disponibles los nombres de turno del catálogo local (Mañana, Tarde y Noche). El padrón Docente de ejemplo usa el departamento `K` y la sede `Campus`.

## Configuración recomendada para ver las casuísticas

Para una primera pasada completa sugiero:

- Máximo de **25 electores por mesa**. Con la distribución actual por departamento y sede, esto debería producir alrededor de **27 mesas**; puede variar si cambian las reglas de asignación de sedes.
- Habilitar **Mañana, Tarde y Noche** como turnos de trabajo, con horarios no superpuestos.
- Empezar con **1 titular y 1 suplente por mesa y turno**. Si las 27 mesas están activas en los tres turnos, el objetivo sería hasta 81 titulares y 81 suplentes. La elegibilidad puede dejar vacantes, que también conviene observar.
- Para probar capacidad y faltantes, cambiar luego a **2 titulares y 1 suplente** por mesa/turno. Eso aumenta el requerimiento y hace más visible el agotamiento de candidatos en departamentos/sedes pequeños.

No empezaría con más titulares: la regla prioriza cubrir primero una titular por mesa/turno y luego completa los cupos. Con 500 candidatos nominados, el primer perfil permite ver cobertura y los límites; el segundo sirve como prueba de estrés.

## Secuencia sugerida

1. Crear una elección nueva y habilitar Docentes y Estudiantes, sus departamentos, Campus y Medrano, y los turnos.
2. Importar y confirmar `padron_estudiantes_500.csv` y `padron_docentes_50.csv`. Configurar máximo de electores por mesa y aplicar reglas de sede; verificar que todas las asignaciones estén calculadas.
3. Generar las mesas automáticas para toda la elección. Confirmar que se hayan creado antes de gestionar autoridades.
4. Configurar los cupos recomendados por turno.
5. En Docentes, agregar autoridades **manualmente** desde la búsqueda del padrón. Probar con documento `40000001`, legajo `800001` o nombre `Ana Pérez`. No existe importación por archivo para la prueba manual: el archivo de 50 personas solo sirve como padrón fuente.
6. En Estudiantes, importar `autoridades_estudiantes_500.csv` y recalcular la distribución.
7. Usar `autoridad_no_en_padron.csv` aparte para probar el rechazo por elector inexistente.
8. Para probar cambio de sede, generar una vacante en una mesa de una sede y comprobar que se proponga una persona elegible de otra sede. La propuesta no debe alterar el padrón hasta ser confirmada; no debe dejar vacía la mesa de origen.

## Casos de prueba

- **No pertenece al padrón:** archivo `autoridad_no_en_padron.csv`; debe rechazarse porque el DNI/legajo no existe en el claustro de la elección.
- **Misma sede donde cursa:** tomar una persona de la mitad del archivo que tiene sede informada y verificar que no pueda cubrir una mesa en su sede de cursada, aunque su turno de trabajo no se superponga. La regla vigente prohíbe trabajar en la sede donde cursa sin importar el turno.
- **Conflicto de turno:** una persona que cursa por la mañana en Campus no debe asignarse en un turno de trabajo que se superponga. Para aislar este control, la mesa objetivo y la sede electoral deben ser Medrano; probar turno laboral Mañana (rechazo) y luego un turno sin superposición (elegible, si cumple el resto de las reglas).
- **Cursada sin sede:** una persona con Sede y Turno vacíos no tiene restricción por sede/horario de cursada; todavía debe respetar claustro, departamento, sede electoral y disponibilidad.
- **Cambio de sede electoral:** dejar una mesa sin titular y candidatos suficientes asignados a otra sede del mismo departamento. Debe proponerse el movimiento a una sede habilitada y esperar confirmación. El elector no puede ser el único de su mesa de origen.
- **Vías de carga:** Docentes por búsqueda manual; Estudiantes por CSV. Ambas nominaciones deben apuntar a electores activos del padrón; no crean identidades.

**Aclaración:** “misma sede en cualquier turno” y “misma sede pero con turno no superpuesto” no son dos resultados distintos: la regla actual bloquea la sede donde cursa incluso con turnos distintos. El segundo caso distinto que sí vale probar es **otra sede, pero turno superpuesto**.

## Otras casuísticas recomendadas

- DNI/legajo duplicados en el archivo, elector ya nominado, excluido o inactivo.
- Elector de otro claustro/departamento, o combinación DNI y legajo que apunte a personas distintas.
- Sede de cursada informada sin Turno (debe fallar el padrón), turno inactivo/inexistente y sede vacía con turno vacío.
- Intentar distribuir sin mesas o sin turnos configurados; candidatos insuficientes; suplentes faltantes.
- Una mesa, varias mesas y departamentos/sedes con muy pocos electores; comprobar que no se creen autoridades de otro departamento y que ninguna mesa quede sin titular si existe candidato elegible.
- Rechazar una designación y recalcular; quitar una candidatura; comprobar vacantes y exclusión.
- Intentar cambiar la nómina después de emitir el padrón imprimible (debe bloquearse).

La cantidad final de mesas y la cobertura de autoridades dependen de las reglas de sede, departamentos habilitados y cupos configurados. Los CSV preparan los datos, pero no configuran esas relaciones por sí solos.
