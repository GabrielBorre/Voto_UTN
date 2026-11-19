# Docentes: dos familias de sublistas y dos listas DASUTeN

Origen: `padron_docentes_sin_autoridades.csv` de segmento_1_500, contrastado con las
autoridades asignadas de la foto de instancia 3. Se cuentan personas por documento,
sin duplicar a quienes tienen registros en dos departamentos: hay 385 personas y 451 registros.

Las familias 19 — 19 de agosto y 2 — Integración tienen tres sublistas cada una:
Sistemas (K), Industrial (I) y Electrónica (R). Son seis presentaciones distintas.
El número 19 o 2 se mantiene dentro de cada familia; el nombre y el código de
presentación distinguen cada sublista. La familia es una agrupación de estos
archivos de prueba; no crea una entidad nueva en la aplicación.

Además hay dos presentaciones, una por familia, exclusivamente para DASUTeN.

| Presentación | Superior T+S | Directivo T+S | Departamental T+S | DASUTeN T+S |
|---|---:|---:|---:|---:|
| Cada una de las seis sublistas departamentales | 15+15 | 2+2 | 5+5 del propio departamento | — |
| Cada una de las dos listas DASUTeN | — | — | — | 2+2 |

El cupo de Directivo de estos casos es 2+2, confirmado por el usuario.
Todos los cuerpos cubren el 100 % de los cupos de este escenario y superan el mínimo del 50 %.
El estándar documentado del proyecto es 5+5 para Directivo: estos archivos no cambian
los parámetros ni la base. Antes de importarlos, configurar 2 titulares y 2
suplentes para Directivo de Docentes y habilitar los demás puestos con los cupos
indicados arriba. Con un cupo de 5+5, estos candidatos de Directivo representarían
el 40 %, por debajo del mínimo solicitado.

Alcanzan los tres departamentos: K dispone de 172 personas,
I de 100 y R de 40.
Se reservan veinte de cada departamento para completar las dos departamentales.
Los candidatos a Superior, Directivo y DASUTeN pueden pertenecer a cualquier departamento.

Se seleccionan 152 personas distintas; quedan
233 sin seleccionar. Los CSV contienen
272 candidaturas: los mismos quince titulares y quince suplentes
de Superior se repiten, con idéntico orden, en las tres sublistas de su familia.
Las dos familias tienen nóminas diferentes. No hay otras repeticiones entre cargos,
sublistas ni listas DASUTeN. Los apoderados son ocho ejemplos ficticios externos al
padrón, sin candidatura; pueden reemplazarse por los datos reales antes de importar.

## Carga

1. Consultar `listas_y_apoderados.csv` para crear las ocho listas con sus nombres,
   números, códigos y apoderados. Asociar los tres puestos de cada sublista o
   el único puesto de cada lista DASUTeN, según corresponda.
2. Dentro de cada lista, abrir **Importar por CSV (uno o varios puestos)** y elegir
   el archivo `lista_*.csv` correspondiente de esta carpeta.
3. Revisar la previsualización y confirmar. Al cargar las siguientes sublistas de
   una familia, la aplicación puede advertir que Superior figura en otra
   presentación. Esa repetición es intencional y está solicitada para estos casos.

Alternativamente, `importacion_completa/` contiene los mismos ocho CSV con trece
columnas para `/gestion/elecciones/<id>/candidaturas/importar/`: incluyen los datos
de cada presentación y permiten crearla con sus asociaciones. Elegir una sola vía
de carga para cada lista.

Los archivos principales tienen seis columnas:
`puesto;departamento;tipo_documento;documento;tipo_candidatura;orden`.
Se usa UTF-8 con BOM, separador punto y coma y nombre completo de departamento.
Los puestos generales dejan departamento vacío. El orden empieza en 1 para cada
puesto y tipo de candidatura. No se incluye Ciencias Básicas como puesto adicional.

## Revisión

- `detalle_candidatos.csv`: identidades, cargos, departamento principal y registros
  departamentales de origen. Superior aparece tres veces por persona.
- `cobertura.csv`: cantidades y cobertura por puesto de cada presentación.
- `resumen.json`: personas distintas, candidaturas, distribución por departamento
  principal, huellas SHA-256 y metadatos de las ocho listas.

Regenerar con `python scripts/generar_listas_docentes_demo.py --directivo 2`.
El generador comprueba identidad, pertenencia departamental, cupos, órdenes,
exclusión de autoridades y que la única repetición sea Superior dentro de su familia.
No modifica el padrón ni crea candidatos en la base de datos.
