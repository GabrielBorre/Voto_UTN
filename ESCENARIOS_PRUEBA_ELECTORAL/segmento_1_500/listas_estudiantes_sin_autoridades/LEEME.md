# Dos listas de candidatos estudiantiles

Listas 19 — 19 de agosto y 3 — Franja Morada.
Origen: padrón estudiantil de segmento_1_500 sin autoridades de la foto de instancia 3 y sin Carlos Gómez (38999222).

El mínimo solicitado es 50 % por cuerpo. Los datos permiten cubrir el 100 % en ambas listas:

| Cuerpo / alcance | Titulares por lista | Suplentes por lista | Cobertura |
|---|---:|---:|---:|
| Consejo Superior, cualquier departamento | 5 | 5 | 100 % |
| Consejo Directivo, cualquier departamento | 5 | 5 | 100 % |
| Consejo Departamental — Sistemas (K) | 3 | 3 | 100 % |
| Consejo Departamental — Industrial (I) | 3 | 3 | 100 % |
| Consejo Departamental — Electrónica (R) | 3 | 3 | 100 % |
| Ciencias Básicas, cualquier departamento | 3 | 3 | 100 % |

Cada lista contiene 44 personas: 22 titulares y 22 suplentes. Se usan 88 personas distintas,
sin repetirlas entre cargos ni entre listas; quedan 241 estudiantes sin seleccionar.
Hay 163 personas disponibles de K, 89 de I y 32 de R. Cada departamento necesita doce
para completar ambas listas, por lo que alcanzan los tres departamentos.

Los apoderados son datos ficticios externos al padrón y no aparecen como candidatos.
Sus nombres y correos de ejemplo se informan en listas_y_apoderados.csv.

## Importación completa

Importar los archivos lista_19_19_de_agosto.csv y lista_3_franja_morada.csv
desde la importación general de candidaturas de la elección:
`/gestion/elecciones/<id>/candidaturas/importar/`.
Estos CSV incluyen los datos de la presentación, del apoderado y los seis puestos.
Los puestos deben estar habilitados para Estudiantes en la elección y sus cupos deben ser los indicados arriba.

## Importación en listas creadas manualmente

Como alternativa, crear cada lista con los datos de listas_y_apoderados.csv, asociarle los seis puestos
y usar el archivo de su mismo nombre dentro de multipuesto/ en la pestaña CSV de uno o varios puestos.
Elegir esta vía o la importación completa para cada lista.

Los departamentos de los puestos generales quedan vacíos; para los departamentales se usa el nombre completo.
Los archivos usan UTF-8 con BOM y separador punto y coma, según las plantillas de la aplicación.

## Revisión y regeneración

detalle_candidatos.csv contiene nombres, documentos, legajos, departamentos y la candidatura de cada persona.
cobertura.csv muestra los cupos completos, los mínimos redondeados del 50 % y la cobertura propuesta.
resumen.json registra el origen, las huellas SHA-256 y la semilla de selección.

```powershell
python scripts/generar_listas_estudiantes_demo.py
```

Se generan archivos de prueba; no se crean listas ni candidatos en una base de datos.
