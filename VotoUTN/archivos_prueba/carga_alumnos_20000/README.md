# Prueba de carga: alumnos, departamentos adicionales y nómina

Todos los datos son ficticios. Los 1.500 adicionales repiten identidades del
mismo archivo en otro departamento; no son 1.500 personas nuevas ni copias de
datos personales de la base habitual.
Los correos son ficticios y usan el prefijo `prueba.carga20k` y el dominio
institucional que exige el importador. El entorno de demo utiliza Mailpit.

## Archivos para cargar

1. `padron_alumnos_20000_filas.csv`: 20.000 filas, 18.500 personas distintas,
   18.500 registros principales y 1.500 adicionales. Se conservan DNI, legajo,
   nombre y correo al repetir una persona; cambia el departamento de esa fila.
2. `nomina_autoridades_630.csv`: 630 personas distintas del padrón. Una sola fila
   por persona. La aplicación decide el turno; el archivo no fija mesas ni turnos.

`control_mesas_esperadas.csv` y `control_personas_nomina.csv` son documentos de
control y no se importan. La referencia de mesa es una posición dentro del grupo
departamento/tipo, no el número global asignado por la aplicación.

## Configuración para reproducir el escenario

- Crear una elección nueva, con el claustro **Estudiantes** (alumnos).
- Habilitar los departamentos **K, I, R, O y S**. Cada uno tiene 3.700 principales
  y recibe 300 adicionales de otro departamento.
- Usar **Campus como única sede electoral** para esos departamentos.
- Configurar **máximo 300 electores por mesa** y una fecha de votación válida.
- Importar y confirmar el padrón; calcular las mesas si la pantalla lo solicita.
- En autoridades, configurar los turnos **Mañana, Tarde y Noche** y **3 titulares
  mínimos y 3 máximos por mesa y turno**, sin suplentes.
- Elegir **Nómina común** y cargar `nomina_autoridades_630.csv`.
- Elegir **Vota y ejerce en su mesa**, sin cambios de mesa ni de sede.

El padrón deja vacíos la sede y el turno de cursada para que ninguna persona
tenga una incompatibilidad horaria con los tres turnos de trabajo.
Las autoridades de mesas principales se eligieron entre personas con un único
departamento; las de mesas especiales son otras personas. Así hay una cobertura
posible sin ocupar dos cupos con la misma identidad.

## Resultado esperado

- **70 mesas:** 65 principales y 5 especiales.
- **60 mesas de 300 registros y 10 de 200**, según el reparto de remanentes que
  ya realiza la aplicación. Promedio: aproximadamente 286 registros por mesa.
- **630 autoridades:** 3 por turno × 3 turnos × 70 mesas, sin personas repetidas.
- Una sede compartida para los dos registros de cada persona.

La cantidad prevista supone este padrón sin otros archivos acumulados y la
configuración indicada. Agregar sedes o cambiar la capacidad cambia las mesas
necesarias y, por lo tanto, el tamaño requerido de la nómina.

Para repetir la generación: `python VotoUTN/archivos_prueba/generar_carga_alumnos_20000.py`.
Los CSV se escriben en UTF-8 con BOM y son compatibles con la importación web.
