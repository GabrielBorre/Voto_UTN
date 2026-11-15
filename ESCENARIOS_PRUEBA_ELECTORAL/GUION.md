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

`reservar` excluye de autoridades a los diez solicitantes originales y a Carlos.
En el primer caso no excluye a los nueve adicionales: tres están en las nóminas
de doce y de 198 personas para mostrar el aviso de autoridades afectadas.
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

`cambios` carga el lote completo del segmento en una sola ejecución: diecinueve
solicitudes en el primer caso, veinte en el segundo y cuarenta en el tercero.
Revisar el impacto, que incluye la futura solicitud manual de Carlos. Repetir con
`--aplicar` para crear únicamente las solicitudes automáticas pendientes.
Si ya existen algunas, aunque estén aprobadas o rechazadas, se conservan y solo
se crean las faltantes. Se informan las nuevas, existentes por estado, pendientes
totales y cuántos de los tres solicitantes de la nómina pequeña están designados.
Iniciar sesión como Carlos y solicitar manualmente Campus → Medrano.

Si se prueba solo Estudiantes y se acepta que los solicitantes también puedan
ser autoridades ya sorteadas, agregar `--solo-estudiantes --conservar-autoridades`
al comando de cambios. En este modo no se exige `reservar`: se conservan las
designaciones existentes al presentar. La aprobación y el recálculo posteriores
siguen siendo manuales y pueden mostrar autoridades afectadas.

Para el primer caso, si se está probando solo Estudiantes, alcanza este comando:

```powershell
python ejecutar_escenario.py cambios --contenedor $contenedorPrueba --eleccion $eleccionPrueba --segmento $segmentoPrueba --solo-estudiantes
```

Revisar la previsualización y repetir con `--aplicar`. No se duplican solicitudes
ni se presenta la de Carlos. La carga conserva todas las designaciones, incluidas
las de solicitantes sorteados. `ampliar_cambios` queda como alias compatible del
mismo lote completo; ya no hace falta ejecutarlo por separado.

Los padrones no cambian. Los nueve casos adicionales trasladan conjuntamente
principal y secundario, permitiendo una mesa ordinaria de Sistemas y una especial
de Industrial en Medrano. Tres de esos solicitantes figuran en la nómina pequeña
y en ambas nóminas de 198; sus documentos están en `control.json`, clave
`solicitantes_nomina_pequena`. Para mostrar el aviso deben estar efectivamente
designados: importar y confirmar la nómina pequeña o la completa antes de revisar
los cambios de sede. Pertenecer al CSV no los designa automáticamente. Puede
haber más autoridades afectadas por sorteo o por el reparto de otras personas.
Volver al listado para generar una propuesta nueva: la anterior se invalida al
cambiar las solicitudes. Si se usa un límite, indicar al menos dos. La simulación
se realiza con el estado actual: mesas ya creadas pueden cambiar la estimación.
Si ya se aprobó parte del lote, no se exige crear otras dos mesas al completar
las solicitudes faltantes; se conserva lo resuelto y se informa el impacto restante.

5. Revisar y aprobar por interfaz. Se esperan entre una y nueve mesas nuevas. Si el estado ya cambió y el script detecta otro resultado, revierte el lote: revisar reglas y movimientos en lugar de forzarlo.
6. Previsualizar y confirmar el recálculo, revisar personas desplazadas y autoridades afectadas. Completar vacantes conservando designaciones válidas. Comprobar todos los mínimos antes de confirmar autoridades definitivas. Cerrar el período de cambios conforme al flujo de la interfaz.

## Comparar las opciones con una nómina que requiere movilidad

En el primer segmento usar `nomina_estudiantes_movilidad.csv` (198 personas).
Es una alternativa a la nómina completa habitual; no se agrega encima de ella.
El padrón y las reglas son los mismos. Cuatro personas de Electrónica/Medrano
se reemplazan por cuatro elegibles de Electrónica/Campus, sin actividad ese día.

Para que se vea la diferencia, empezar sin designaciones previas completas.
Si ya se confirmó otra nómina o el sorteo, usar «Eliminar todas las asignaciones»
del claustro para esta comparación: quita asignaciones y candidaturas previas,
conservando padrón, mesas y reglas. También quita exclusiones: volver a ejecutar `reservar --aplicar` antes de
continuar con este archivo o con un sorteo.

Previsualizar el archivo y comparar «Vota y ejerce en su mesa», «Vota y ejerce
en otra sede» y «Cambia de sede y reordena mesas». Sin cambio de sede faltan
autoridades en Medrano; permitirlo permite cubrirlas. «Otra sede» cambia sede
y mesa de votación de esas personas sin desplazar al resto; «Cambia de sede y
reordena mesas» además puede reacomodar el padrón. Permitir solo otra mesa de
la misma sede no alcanza para resolver el déficit entre Campus y Medrano.

Consultar `control.json`, clave `nomina_movilidad`, para ver las personas
reemplazadas, donantes y mesa con déficit. Comparar antes de confirmar una
alternativa: la confirmación conserva sus designaciones en cálculos posteriores.

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
