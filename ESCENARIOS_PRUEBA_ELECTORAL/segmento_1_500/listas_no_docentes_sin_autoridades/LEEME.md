# Dos listas de No docentes

- Lista 9 — Unión y Participación: `lista_9_union_y_participacion.csv`.
- Lista 3 — Integración: `lista_3_integracion.csv`.

Cada lista tiene catorce personas distintas: cinco titulares y cinco suplentes
para Consejo Superior, un titular y un suplente para Consejo Directivo, y un
titular y un suplente para Consejo DASUTeN.
Con los cupos estándar de No docentes, Directivo cubre el 100 % (1+1 de 1+1)
y DASUTeN cubre el 50 % (1+1 de 2+2). Se respeta el mínimo por cuerpo y tipo.
Superior cubre el 100 % (5+5 de 5+5). No se incluyen cargos departamentales.

Origen: padrón de No docentes de segmento_1_500 sin autoridades asignadas de la
foto de instancia 3. Se usan 28 de las 464 personas disponibles; quedan 436.
Ninguna persona se repite entre cargos o listas. Los dos apoderados son ejemplos
ficticios externos al padrón, sin candidatura; reemplazarlos por los datos reales
cuando corresponda. Sus datos están en `listas_y_apoderados.csv`.

## Cargar dentro de una lista

Crear cada lista en No docentes con los datos de `listas_y_apoderados.csv` y
asociarle los puestos Consejero/a Superior, Consejero/a directivo/a y Consejero/a DASUTeN.
Desde **Importar por CSV (uno o varios puestos)** cargar el archivo `lista_*.csv`
correspondiente de esta carpeta. Son catorce candidatos por archivo, con columnas:
`puesto;departamento;tipo_documento;documento;tipo_candidatura;orden`.

Los tres puestos son generales: departamento queda vacío. El orden empieza en 1
para cada combinación de puesto y tipo. Se usa UTF-8 con BOM y punto y coma.
Los puestos deben estar habilitados para No docentes en la elección.

Como alternativa, los archivos de `importacion_completa/` incluyen las trece
columnas de presentación, apoderado y candidatos para cargar desde
`/gestion/elecciones/<id>/candidaturas/importar/`. Elegir una vía por lista.

`detalle_candidatos.csv` permite revisar nombres, documentos y legajos;
`cobertura.csv` informa las cantidades por cuerpo, y `resumen.json` registra
el origen, sus huellas SHA-256 y la semilla de selección.

Regenerar con `python scripts/generar_listas_no_docentes_demo.py`.
Se generan archivos de prueba: no se cambia el padrón, los parámetros ni la base.
