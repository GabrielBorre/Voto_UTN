# Variantes de prueba: alumnos

Estos CSV derivan del padrón local de 500 estudiantes. Conservan sus identidades
y contienen datos ficticios, según confirmó el responsable del proyecto. Los CSV
están incluidos en Git para reproducir las pruebas. La carpeta
`controlados` modifica únicamente cursada y nivel para preparar escenarios.
El generador no consulta ni modifica la base de datos.

## Dónde cargar cada archivo

- `padron_...` y `error_padron_...`: importación de **padrón de Estudiantes**.
- `autoridades_...` y todos los archivos de `sobre_padron_500`: importación de
  **autoridades de Estudiantes**.
- La columna `Turno` del padrón es de **cursada**, no de trabajo. El CSV de
  autoridades no asigna sede, turno ni mesa: identifica candidatos.
- Cargar cada archivo individualmente. Los archivos con errores son pruebas
  negativas; no mezclarlos con los válidos.
- Los nombres de sedes y turnos deben existir y estar activos: Campus, Medrano,
  Mañana, Tarde y Noche. Usar horarios de trabajo/cursada no superpuestos salvo
  cuando el caso pida deliberadamente un conflicto.

## A. Variantes sobre el padrón existente de 500 alumnos

Primero importar `../padron_estudiantes_500.csv` (desde esta carpeta, está un nivel
arriba). Habilitar sus departamentos, calcular sedes y mesas, y configurar turnos
y cupos antes de cargar autoridades.

| Archivo en `sobre_padron_500/` | Filas | Qué verificar |
|---|---:|---|
| `01_sin_restriccion_cursada.csv` | 12 | Sin restricción de sede/horario de cursada; deben respetar departamento y sede electoral. |
| `02_cursan_campus_manana.csv` | 12 | No pueden trabajar en Campus en ningún turno ni en otra sede durante Mañana. Tarde en Medrano puede ser compatible. |
| `03_cursan_medrano_manana.csv` | 12 | Caso inverso: Medrano bloqueado; Campus/Tarde puede ser compatible. |
| `04_solo_departamento_K.csv` | 12 | No deben cubrir vacantes de otros departamentos. |
| `05_un_candidato_faltantes.csv` | 1 | Mostrar las vacantes que no puede cubrir una sola persona. |
| `06_reimportar_mismo_candidato.csv` | 1 | Es la misma persona del archivo 05: no debe duplicarla. |
| `07_error_no_existe.csv` | 1 | Rechazar: documento y legajo ausentes del padrón fuente. |
| `08_error_duplicado_exacto.csv` | 2 | Rechazar el lote por repetición. |
| `09_error_documento_legajo_cruzados.csv` | 1 | Rechazar: ambos existen, pero pertenecen a distintas personas. |
| `10_error_sin_identificadores.csv` | 1 | Rechazar: faltan documento y legajo. |
| `11_error_lote_mixto_atomico.csv` | 3 | Dos válidos y uno inexistente: no debe incorporarse ninguno. Comparar nómina antes/después. |
| `12_valido_solo_documento.csv` | 1 | Resolver la identidad por documento. |
| `13_valido_solo_legajo.csv` | 1 | Resolver la misma identidad por legajo, sin duplicarla si ya existe. |
| `14_error_tipo_documento_incorrecto.csv` | 1 | Rechazar: declara CUIL para una identidad DNI. |
| `15_repetido_identificadores_alternativos.csv` | 2 | Misma persona por documento y por legajo: nunca duplicarla. El validador actual compara la combinación textual, por lo que puede aceptar el archivo y consolidarlo en una sola candidatura en lugar de informar duplicado. Registrar lo observado. |

Una importación válida incorpora personas a la nómina: **no garantiza que todas
sean asignadas**. Depende de cupos, mesas, sede electoral y elegibilidad. Las
importaciones suman candidatos; no sustituyen la nómina anterior. Para medir
faltantes con un solo candidato se necesita una nómina inicial vacía.

## B. Escenarios controlados: solo departamento K

Usar una elección de prueba preparada para cada escenario, sin QR emitidos.
Los padrones siguientes son **alternativas**, no archivos para acumular entre sí
ni para agregar al padrón de 500. Comparten identidades con él. Importar un
subconjunto no garantiza eliminar registros preexistentes. No vaciar un padrón
real para probarlos. El sistema permite una sola elección no cerrada.

Los 12 alumnos pertenecen a K. Los primeros seis tienen Nivel 1 y los otros seis
Nivel 2, para poder definir reglas de sede reproducibles. Los archivos de
autoridades 03 a 06 corresponden a ambos padrones 01 y 02.

### B1. Distribución pareja y faltantes

1. Importar `controlados/01_padron_12_sin_cursada.csv`.
2. Asignar sede electoral Medrano a todos. Máximo **6 electores por mesa**:
   verificar que se generen dos mesas de seis.
3. Habilitar solo Tarde para autoridades, con **2 titulares y 0 suplentes**.
4. Con nómina vacía, importar `04_autoridades_3_reparto.csv`.
5. Esperar tres titulares repartidos **2–1**, nunca 3–0.

Para faltantes, usar `05_autoridades_1_faltantes.csv` sobre nómina vacía: una mesa
quedará sin titular. Para cupos/suplentes, cargar `03_autoridades_12.csv` y fijar
**2 titulares y 1 suplente**: con un solo turno y dos mesas deben asignarse cuatro
titulares y dos suplentes; los otros seis permanecen sin asignación.

Luego habilitar tres turnos con **1 titular y 1 suplente**: las 12 personas libres
de cursada permiten cubrir las 12 plazas. Cada persona debe ocupar una sola.
Como caso de escasez entre turnos, usar nómina de tres personas con dos mesas y
tres turnos: registrar qué turnos quedan cubiertos y comprobar la prioridad de
cobertura frente a plazas adicionales. No asumir que un CSV resuelve el orden
del algoritmo.

### B2. Misma sede y conflicto horario

1. Importar como alternativa `02_padron_12_cursan_campus_manana.csv`.
2. Todos cursan Campus/Mañana. Importar `03_autoridades_12.csv` después de
   configurar mesas y turnos.
3. Con sede electoral Campus: ninguna persona puede trabajar allí, ni Mañana ni
   Tarde. Para aislar el bloqueo, habilitar solo Campus como sede electoral.
4. En una preparación alternativa, asignar sede electoral Medrano y habilitar
   solo Mañana: no deben asignarse por superposición horaria.
5. Cambiar el turno laboral a Tarde, sin superposición: deben resultar elegibles
   hasta completar cupos. Si se habilitan varios turnos a la vez, el sistema
   puede asignarlas a uno compatible; eso no significa que ignoró el conflicto.

### B3. Cambio de sede con confirmación

1. Usar `01_padron_12_sin_cursada.csv`, Campus y Medrano habilitados para K.
2. Configurar reglas: **Nivel 1 → Campus; Nivel 2 → Medrano**. Recalcular sedes.
3. Máximo **6 electores por mesa**: verificar una mesa por sede.
4. Solo Tarde, **1 titular y 0 suplentes**.
5. Importar `06_autoridades_6_nivel_1_cambio_sede.csv`.
6. La nómina tiene seis candidatos de Campus y ninguno de Medrano: debe cubrir
   Campus y proponer un candidato disponible para Medrano.
7. Antes de confirmar, verificar que conserva su sede original. Después,
   comprobar cambio del mismo registro, recálculo de mesas/autoridades y que no
   se duplicó al elector. Con máximo seis, siete electores en destino pueden
   generar más mesas: revisar nuevamente cobertura; no esperar conservar dos.
8. No volver a aplicar las reglas iniciales durante esta comprobación, porque
   eso constituye otra operación de recálculo de sedes.

### B4. No dejar vacía la mesa de origen

1. Usar `12_padron_13_origen_no_movible.csv`: los 12 alumnos anteriores más uno
   de K con Nivel 3, todos sin restricción de cursada.
2. Reglas: **Nivel 3 → Campus; niveles 1 y 2 → Medrano**.
3. Máximo seis, solo Tarde, **1 titular y 0 suplentes**.
4. Importar `13_autoridad_unica_nivel_3.csv`: es el único elector de Campus.
5. No debe proponerse un traslado que vacíe su mesa; quedan faltantes en Medrano.
   Este caso cubre la protección de origen junto con la falta de candidatos
   libres; no aísla por sí solo la validación interna de una confirmación forzada.

`11_padron_1_origen_no_movible.csv` es una alternativa mínima de un solo elector;
se puede nominar con `05_autoridades_1_faltantes.csv`. Sirve para revisar el caso
de una única mesa/persona; no crea una mesa destino por sí solo.

### B5. Errores del padrón

Importar individualmente, en la pantalla de padrón de Estudiantes:

| Archivo en `controlados/` | Resultado esperado |
|---|---|
| `07_error_padron_sede_sin_turno.csv` | Rechazar por Campus sin turno de cursada. |
| `08_error_padron_turno_inexistente.csv` | Rechazar por turno inexistente. |
| `09_error_padron_sede_inexistente.csv` | Rechazar por sede inexistente. |
| `10_error_padron_sin_columna_turno.csv` | Rechazar porque falta la cabecera Turno junto a Sede donde cursa. |

## Casos que requieren acciones posteriores

Los mismos archivos válidos sirven para probar liberar/excluir/reincorporar,
confirmar/rechazar una designación y restricciones después de emitir QR o cerrar
la elección. Registrar el estado previo y el resultado. Probar QR y cierre al
final. Un alumno inactivo o de otra elección requiere cambiar/preparar su estado
en esa elección; no se simula inventando una columna en el CSV de autoridades.
Los permisos requieren ingresar con el rol correspondiente. La promoción
automática de suplentes sigue documentada como pendiente.

## Regeneración y alcance de la verificación

Desde la raíz del repositorio:

```powershell
python VotoUTN/archivos_prueba/generar_variantes_alumnos.py
```

Reescribe únicamente los CSV de este paquete. Comprueba identidades únicas del
padrón fuente, ausencia del identificador negativo y lectura idéntica de cada
CSV generado. Eso verifica los archivos, no certifica los resultados funcionales
en Django ni reemplaza las pruebas manuales descritas.
