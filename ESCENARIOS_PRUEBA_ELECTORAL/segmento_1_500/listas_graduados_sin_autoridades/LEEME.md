# Dos listas de candidatos de graduados

Listas 19 — 21 de septiembre y 3 — Graduados Club.
Origen: padrón de graduados de segmento_1_500 sin autoridades de la foto de instancia 3.

El mínimo solicitado es 50 % por cuerpo. Los datos permiten cubrir el 100 % en ambas listas:

| Cuerpo / alcance | Titulares por lista | Suplentes por lista | Cobertura |
|---|---:|---:|---:|
| Consejo Superior, cualquier departamento | 5 | 5 | 100 % |
| Consejo Directivo, cualquier departamento | 5 | 5 | 100 % |
| Consejo Departamental — Sistemas (K) | 2 | 2 | 100 % |
| Consejo Departamental — Industrial (I) | 2 | 2 | 100 % |
| Consejo Departamental — Electrónica (R) | 2 | 2 | 100 % |
| Ciencias Básicas, cualquier departamento | 2 | 2 | 100 % |

Cada lista contiene 36 personas: 18 titulares y 18 suplentes. Se usan 72 personas distintas,
sin repetirlas entre cargos ni entre listas; quedan 347 graduados sin seleccionar.
Hay 191 personas disponibles de K, 116 de I y 41 de R. Cada departamento necesita ocho
para completar ambas listas, por lo que alcanzan los tres departamentos.

Los apoderados son datos ficticios externos al padrón y no aparecen como candidatos.
Sus nombres y correos de ejemplo se informan en listas_y_apoderados.csv.

## Cargar candidatos dentro de una lista

Crear cada lista en Graduados con los datos de listas_y_apoderados.csv y asociarle los seis puestos.
En la pestaña Importar por CSV (uno o varios puestos), cargar lista_19_19_de_agosto.csv
o lista_3_club_del_graduado.csv, según la lista. Cada archivo tiene 36 candidatos y seis columnas:
`puesto;departamento;tipo_documento;documento;tipo_candidatura;orden`.
Los puestos deben estar habilitados para Graduados en la elección y sus cupos deben ser los indicados arriba.

## Alternativa de importación completa

Los archivos de importacion_completa/ incluyen los datos de la presentación, del apoderado y los seis puestos.
Se cargan desde `/gestion/elecciones/<id>/candidaturas/importar/`.
Elegir esta vía o la carga dentro de cada lista.

Los departamentos de los puestos generales quedan vacíos; para los departamentales se usa el nombre completo.
Los archivos usan UTF-8 con BOM y separador punto y coma, según las plantillas de la aplicación.

## Revisión y regeneración

detalle_candidatos.csv contiene nombres, documentos, legajos, departamentos y la candidatura de cada persona.
cobertura.csv muestra los cupos completos, los mínimos redondeados del 50 % y la cobertura propuesta.
resumen.json registra el origen, las huellas SHA-256 y la semilla de selección.

```powershell
python scripts/generar_listas_graduados_demo.py
```

Se generan archivos de prueba; no se crean listas ni candidatos en una base de datos.
