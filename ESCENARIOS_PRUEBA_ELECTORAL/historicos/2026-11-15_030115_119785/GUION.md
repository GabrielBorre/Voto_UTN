# Guion de prueba del flujo electoral

## Preparar los archivos

Desde esta carpeta, con Python 3.12:

```powershell
python generar_escenarios.py
python -m unittest test_generador.py
```

Editar el bloque JSON de `DECISIONES.md` para variar cantidades, pesos o límites.
Regenerar archiva automáticamente la versión anterior en `historicos/`.
No ejecutar el generador histórico dentro del directorio activo: para reproducir
una versión antigua, copiar la carpeta histórica a otro directorio y trabajar allí.

## Preparar una elección

Usar una elección nueva por segmento, una a la vez. Finalizar una antes de crear
la siguiente; no borrar ni reiniciar elecciones para pasar al siguiente escenario.
Comenzar por `segmento_1_500`, luego `segmento_2_1000` y finalmente `segmento_3_2000`.

1. Verificar que el entorno de prueba capture los correos en Mailpit o en memoria.
2. Crear/configurar los cuatro claustros con las abreviaturas y límites del documento de decisiones (`codigos_claustro` corresponde al campo «Abreviatura»).
3. Habilitar Campus y Medrano para estudiantes salvo Q, solo Campus. Docentes y graduados únicamente Medrano. No docentes, ambas sedes. Habilitar departamentos correspondientes, incluyendo Z solo para docentes y un alcance sin departamento para no docentes.
4. Configurar Mañana, Tarde y Noche para cada claustro: mínimo dos, máximo tres titulares, sin suplentes.
5. Configurar reglas de sede estudiantiles, en este orden: actividad en Medrano → Medrano; actividad en Campus → Campus; nivel ≥ 4 → Medrano; nivel ≤ 3 → Campus. La sede única prevalece automáticamente. Para no docentes, dos reglas según sede de actividad/trabajo. Docentes y graduados se asignan por su sede única.
6. Importar por la interfaz los cuatro archivos `padron_*.csv`, revisar las previsualizaciones y confirmar. Calcular sedes y mesas.
7. Comprobar coincidencias de identidad antes de confirmar cada padrón. Los scripts no importan ni actualizan electores. Carlos debe coincidir con el usuario existente por DNI y legajo; conservar sus accesos. Si otra identidad existente difiere, detener la importación y revisar.

## Usar los scripts con Docker

Los ejemplos son PowerShell. Reemplazar los valores por el contenedor y elección
que se estén probando. `--directorio-app` debe contener `manage.py` dentro del contenedor.

```powershell
$contenedorPrueba = 'votoutn62-web-1'
$eleccionPrueba = 123
$segmentoPrueba = 'segmento_1_500'
python ejecutar_escenario.py verificar --contenedor $contenedorPrueba --eleccion $eleccionPrueba --segmento $segmentoPrueba
python ejecutar_escenario.py reservar --contenedor $contenedorPrueba --eleccion $eleccionPrueba --segmento $segmentoPrueba --usuario USUARIO_JUNTA
```

`reservar` excluye de autoridades a los solicitantes automáticos y a Carlos.
Repetir el comando con `--aplicar` para guardar; sin esa opción revierte la operación.
Reservar antes de cualquier sorteo. Solo se acepta un usuario local activo con permiso.
Los scripts verifican configuración, cantidades e identidades y rechazan archivos
editados. No cambian parámetros, estados, usuarios, plazos ni configuraciones de la elección.

## Mostrar autoridades y cambios de sede

1. Consultar `control.json`: `manuales` propone dos personas con departamento, sede, tipo de mesa, ordinal dentro del grupo y turno. Usar las mesas reales de la interfaz, no asumir que el ordinal es su número global. Si hubo reordenamientos, verificar nuevamente compatibilidad.
2. Designar esas dos personas manualmente. Importar `nomina_estudiantes_pequena.csv`, previsualizar y confirmar conservando designaciones. Los archivos `nomina_CLAUSTRO.csv` contienen una nómina amplia para pruebas alternativas; no se necesitan para este guion.
3. Completar estudiantes por sorteo conservando las selecciones existentes. Sortear los demás claustros. Revisar mínimos por mesa/turno. Registrar tiempos de nómina y sorteo para cada segmento; la nómina pequeña también procesa el padrón completo.
4. Publicar la elección y habilitar el período de solicitudes. Ejecutar:

```powershell
python ejecutar_escenario.py cambios --contenedor $contenedorPrueba --eleccion $eleccionPrueba --segmento $segmentoPrueba
```

Revisar el impacto, que incluye la futura solicitud manual de Carlos. Repetir con
`--aplicar` para crear únicamente las solicitudes automáticas pendientes.
Iniciar sesión como Carlos y solicitar manualmente Campus → Medrano.

5. Revisar y aprobar por interfaz. Se esperan entre una y nueve mesas nuevas. Si el estado ya cambió y el script detecta otro resultado, revierte el lote: revisar reglas y movimientos en lugar de forzarlo.
6. Previsualizar y confirmar el recálculo, revisar personas desplazadas y autoridades afectadas. Completar vacantes conservando designaciones válidas. Comprobar todos los mínimos antes de confirmar autoridades definitivas. Cerrar el período de cambios conforme al flujo de la interfaz.

## Justificativos de autoridades

Con autoridades definitivas y plazo de justificación abierto, elegir un tipo activo:

```powershell
python ejecutar_escenario.py justificativos --contenedor $contenedorPrueba --eleccion $eleccionPrueba --segmento $segmentoPrueba --tipo 1
```

Revisar y repetir con `--aplicar`. Crea el número configurado de casos pendientes,
uno por grupo mesa/turno que tenga tres titulares. No aprueba ni informa ausencias
de Carlos. Repetir la ejecución no crea casos adicionales por encima del objetivo.
Resolver los casos por interfaz y comprobar que permanezcan al menos dos autoridades
por turno y que no queden solicitudes pendientes antes de iniciar la elección.

## Pruebas automatizadas

`test_generador.py` usa solo biblioteca estándar. `test_integracion.py` usa el
runner de Django y su base PostgreSQL de pruebas; nunca ejecutar contra la base
de la elección activa mediante `shell`.

Desde un entorno con el proyecto en el path y esta carpeta en `PYTHONPATH`:

```text
python manage.py test test_integracion
python manage.py check
python manage.py makemigrations --check
python manage.py migrate --plan
python manage.py test
```
