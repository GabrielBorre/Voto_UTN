# Padrones sin autoridades de la instancia 3

Origen: `.instancias\foto-instancia-3\postgres.sql`, foto del 2026-11-17T03:45:51.1205285-03:00.
Eleccion: Demo 2026 (id 1, en_curso).

Se excluyen personas con designacion en estado `asignada`, mediante tipo y numero de documento.
Las designaciones `rechazada` no excluyen por si solas a la persona.
Exclusion adicional solicitada en Estudiantes: Carlos Gomez, DNI 38999222.
Si una persona aparece en varios departamentos, se eliminan todas sus filas.
Se conservan las columnas, valores, orden y formato CSV de las filas restantes. Los originales no se modifican.

| Claustro | Filas originales | Personas excluidas | Filas excluidas | Filas nuevas | Personas restantes |
|---|---:|---:|---:|---:|---:|
| Estudiantes | 500 | 171 | 171 | 329 | 329 |
| Docentes | 600 | 115 | 149 | 451 | 385 |
| Graduados | 500 | 81 | 81 | 419 | 419 |
| No docentes | 500 | 36 | 36 | 464 | 464 |

`autoridades_instancia_3.csv` detalla las designaciones, sus mesas, turnos, estados y coincidencias.
`resumen.json` incluye cantidades, distribucion por departamento y huellas SHA-256.

La huella de la foto coincide con `huellas.json` al normalizar los finales de linea a LF.
La lectura del SQL es directa: no se restaura ni se modifica ninguna base de datos.

Para regenerar desde la raiz del repositorio:

```powershell
python scripts/generar_padrones_sin_autoridades.py
```
