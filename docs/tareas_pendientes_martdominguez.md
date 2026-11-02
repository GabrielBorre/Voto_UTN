# Tareas pendientes - Mart Domínguez

Última actualización: 2026-09-27

Este documento conserva el backlog acordado para continuar el desarrollo de Voto UTN. Las tareas deben abordarse de a una, con validación visual o funcional antes de crear cada commit.

## Forma de trabajo acordada

- Implementar un cambio aislado por vez.
- Validar el resultado antes de hacer commit.
- Si el cambio se aprueba, documentarlo y crear un commit independiente.
- Si no se aprueba, ajustarlo o revertir únicamente ese cambio.
- No considerar una sección completa solamente porque su formulario fue guardado.

## 1. Completar la unificación visual

Continuar aplicando la estética aprobada en las pantallas internas que todavía no fueron revisadas:

- [x] Sedes y departamentos.
- [x] Mesas automáticas.
- [x] Justificativos.
- [x] Reportes.
- [ ] Revisar las pantallas secundarias de importaciones y detalles.

### Criterios visuales acordados

- Tarjetas uniformes y responsive.
- Acciones alineadas y ubicadas de forma consistente.
- Botones de regreso fuera de las tarjetas y alineados con el contenido.
- Evitar numerar bloques cuando representan alternativas y no una secuencia obligatoria.
- Separar la gestión por claustro cuando los datos y las reglas pertenecen a cada claustro.

## 2. Adaptar la importación del padrón para claustros sin departamento

Tarea pendiente de coordinación: un compañero está trabajando actualmente sobre la importación de padrones. No modificar este flujo hasta integrar o coordinar los cambios para evitar conflictos.

- [ ] Coordinar el contrato del archivo con el trabajo de importación en curso.
- [ ] Mantener la columna `departamento` obligatoria para claustros organizados por departamento.
- [ ] Permitir omitirla o dejarla vacía para claustros sin distinción por departamento.
- [ ] Asignar automáticamente esos registros al alcance interno «Sin distinción por departamento».
- [ ] Conservar las validaciones de sede correspondientes al alcance interno.
- [ ] Incorporar pruebas de previsualización, confirmación e historial para ambos tipos de claustro.

## 3. Definir el circuito de ingreso de justificativos

- [ ] Definir desde qué pantalla y con qué identidad presenta un justificativo el elector.
- [ ] Validar que el elector pertenezca al padrón y que corresponda justificar su ausencia.
- [ ] Aplicar las fechas administrativas de apertura y cierre para la presentación.
- [ ] Definir documentos obligatorios, formatos, tamaño máximo y almacenamiento.
- [ ] Evitar presentaciones duplicadas o definir cuándo pueden reemplazarse.
- [ ] Definir los estados desde la presentación hasta la resolución.
- [ ] Notificar al elector cuando presenta el justificativo y cuando se resuelve.
- [ ] Auditar la presentación, las modificaciones y la resolución.

## 4. Definir el catálogo y circuito de reportes

- [ ] Definir qué necesidad operativa cubre cada reporte y quién lo utiliza.
- [ ] Confirmar el contenido y los campos de cada exportación.
- [ ] Definir cuándo queda disponible cada reporte durante la elección.
- [ ] Revisar permisos y alcance de los datos exportados.
- [ ] Acordar nombres comprensibles para las secciones y descargas.
- [ ] Confirmar el formato adecuado para cada salida: CSV, PDF o visualización en pantalla.
- [ ] Definir trazabilidad o auditoría de las descargas cuando corresponda.

## 5. Finalización explícita del padrón por claustro

- [ ] Incorporar una acción «Finalizar padrón» para cada claustro.
- [ ] Registrar quién confirmó el padrón y cuándo.
- [ ] Bloquear modificaciones posteriores a la finalización.
- [ ] Permitir una reapertura controlada antes de emitir códigos QR.
- [ ] Auditar tanto la finalización como la reapertura.
- [ ] Definir qué validaciones deben cumplirse antes de permitir la finalización.

La finalización debe ser una confirmación explícita. Guardar la fecha de votación, el máximo por mesa o cargar un archivo no debe marcar automáticamente el padrón como completo.

## 6. Generación de mesas mediante una acción o trigger explícito

- [ ] Incorporar un botón o una configuración que dispare la generación de mesas.
- [ ] Definir si el disparador será manual, automático al finalizar el padrón o configurable.
- [ ] Mostrar una previsualización o resumen antes de confirmar la generación.
- [ ] Impedir regeneraciones incompatibles cuando existan códigos QR emitidos.
- [ ] Registrar quién ejecutó la generación y cuándo.
- [ ] Definir el comportamiento al reabrir o actualizar un padrón que ya generó mesas.

La generación continuará respetando el claustro, el departamento, la sede, el orden alfabético y el máximo de electores por mesa.

## 7. Definir cuándo está completa cada sección

- [ ] Datos generales.
- [ ] Sedes y departamentos.
- [ ] Padrones por claustro.
- [ ] Autoridades por claustro.
- [ ] Puestos, listas y candidaturas.
- [ ] Fechas administrativas.

Para cada sección se debe documentar:

- Datos mínimos obligatorios.
- Validaciones necesarias.
- Confirmación explícita, si corresponde.
- Condiciones que obligan a reabrir o invalidar la confirmación.
- Usuario y fecha de la última confirmación.

## 8. Estados de avance en la configuración electoral

- [ ] Mostrar el estado de cada sección en las tarjetas del panel de configuración.
- [ ] Distinguir, como mínimo, entre pendiente, en progreso y completo.
- [ ] Mostrar el avance particular de cada claustro cuando corresponda.
- [ ] Evaluar si una barra o porcentaje aporta información real una vez definidos los criterios.
- [ ] Evitar porcentajes calculados únicamente a partir de acciones de guardado.

## 9. Asignación automática de autoridades de mesa

- [ ] Mantener la carga de candidatos mediante archivo sin exigir mesa ni turno en cada fila.
- [ ] Diseñar un proceso automático posterior que distribuya candidatos entre mesas y turnos.
- [ ] Definir criterios de sede, claustro, disponibilidad, preferencias y cupos.
- [ ] Respetar el máximo de autoridades por mesa y turno.
- [ ] Previsualizar la propuesta antes de confirmarla.
- [ ] Permitir ajustes manuales antes y después de la asignación automática.
- [ ] Registrar la ejecución y los cambios posteriores para conservar trazabilidad.

## Cambios ya completados relacionados

- [x] Navegación interna y botones «Volver a configuración» unificados.
- [x] Ocho tarjetas principales del panel de configuración uniformadas.
- [x] Gestión visual de puestos, listas y candidaturas reorganizada.
- [x] Autoridades separadas por claustro.
- [x] Turnos de autoridades configurables por claustro.
- [x] Gestión de padrones integrada por claustro.
- [x] Fecha de votación, máximo por mesa, carga e historial reunidos en la gestión del padrón.
- [x] Departamentos y sedes retirados de Padrones y centralizados en «Sedes y departamentos».
- [x] Modalidad por departamentos o sin distinción configurada por claustro.
- [x] Gestión de departamentos por claustro con selección individual o total.
- [x] Alcance interno «Sin distinción por departamento» creado automáticamente sin contaminar el catálogo.
