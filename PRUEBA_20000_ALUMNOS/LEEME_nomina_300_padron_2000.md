# Nómina de autoridades para probar las cinco alternativas

Preparada para `padron_alumnos_2000_filas.csv`, con 75 mesas, máximo 30 registros
por mesa, Campus y Medrano y los turnos Mañana, Tarde y Noche. Los cupos son
mínimo 1 y máximo 3 titulares por mesa y turno.

## Qué archivo cargar

**`nomina_autoridades_300_padron_2000.csv`**: 300 personas distintas del padrón
reducido, con los encabezados `Tipo documento,Documento,Legajo`.

- 210 personas tienen solo registro principal.
- 90 tienen principal y adicional; aparecen una sola vez en la nómina.
- 240 votan en Campus y 60 en Medrano, concentradas en algunas mesas para hacer
  visibles los movimientos entre alternativas.
- `control_nomina_300_padron_2000.csv` es solo de consulta: muestra las mesas y
  sedes de votación anteriores a confirmar cambios. No fija puestos ni turnos.

## Resultados de la prueba aislada del 9 de noviembre

Se usaron el código real y una réplica ficticia en PostgreSQL separado: 1.850
personas, 2.000 registros y las 75 mesas de partida. Las cinco alternativas se
previsualizaron completas, sin errores. Se confirmó además «Cambia de sede y
reordena mesas» y se comprobaron 300 autoridades distintas, un solo puesto por
persona, tipos de mesa correctos, máximo 30 por mesa y sede común de todos los
registros activos. Los datos de esa prueba se revirtieron.

| Alternativa | Titulares | Sin asignar | Cupos máximos pendientes | Registros que cambian mesa | Registros que cambian sede |
|---|---:|---:|---:|---:|---:|
| Vota y ejerce en su mesa | 195 | 105 | 480 | 0 | 0 |
| Vota y ejerce en mesas distintas | 300 | 0 | 375 | 0 | 0 |
| Vota y ejerce en otra mesa | 300 | 0 | 375 | 646 | 0 |
| Vota y ejerce en otra sede | 195 | 105 | 480 | 0 | 0 |
| Cambia de sede y reordena mesas | 300 | 0 | 420 | 759 | 30 |

«Vota y ejerce en mesas distintas» permite que 105 autoridades trabajen en otra
mesa, manteniendo su mesa de votación. Las columnas de cambios cuentan registros
de padrón: una persona con principal y adicional puede aportar dos cambios.

Los cupos pendientes se comparan con el máximo de 3 titulares por turno, no con
el mínimo de 1. Al crear mesas también crece ese máximo total: por eso una
alternativa puede cubrir más personas y mostrar más cupos máximos pendientes.

La corrección de elegibilidad ya impide mezclar mesas ordinarias y especiales.
Los cambios se hacen entre mesas del mismo tipo y departamento. Si cambia la
sede electoral de una autoridad, todos sus registros activos acompañan el
traslado a esa sede, sin modificar su sede de cursada ni duplicar su identidad.

## Cómo probar en la aplicación

1. Entrar en Autoridades del claustro y elegir **Nómina común**.
2. Cargar `nomina_autoridades_300_padron_2000.csv` y previsualizar.
3. Comparar las cinco alternativas; confirmar la que se quiera probar.
4. Para repetir desde cero, usar **Eliminar todas las asignaciones**, que
   también elimina las candidaturas, y volver a cargar la nómina. El padrón
   conserva los cambios que ya se hayan confirmado: las cifras de la tabla
   corresponden a la distribución inicial de 75 mesas.

Generar y verificar estos archivos no cargó candidaturas ni guardó autoridades
en la elección habitual. Las cantidades pueden cambiar si se alteran sedes,
mesas, cupos, exclusiones o registros.

## Rendimiento observado

En el ensayo aislado, la alternativa de otra sede sin reordenar demoró unos
5 minutos y 31 segundos; las otras alternativas demoraron aproximadamente
8, 11, 40 y 30 segundos. Se ejecutó la suite de regresión en otra base durante
parte del ensayo, por lo que estos tiempos no son una medición exclusiva ni
una garantía para la aplicación habitual. La optimización de consultas de
ubicación repetidas sigue pendiente; el indicador permanece hasta la respuesta.
