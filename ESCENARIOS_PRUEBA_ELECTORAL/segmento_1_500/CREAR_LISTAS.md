# Crear las listas donde se cargarán los candidatos

## Ejecución rápida para compartir el escenario

Desde la raíz del repositorio, con Docker y la instancia 2 ya levantada:

```powershell
git switch develop
git pull --ff-only origin develop
docker cp ./ESCENARIOS_PRUEBA_ELECTORAL/segmento_1_500/. voto-utn-2-web-1:/tmp/candidatos_segmento_1
docker exec voto-utn-2-web-1 python /tmp/candidatos_segmento_1/cargar_candidatos_csv.py --proyecto /app --eleccion 1 --usuario juanb --aplicar
```

Este comando agrega las listas y candidaturas que faltan y carga los catorce
archivos, sin vaciar las listas existentes. Si faltan puestos o los cupos son
antiguos, agregar `--preparar-puestos` para configurarlos según estos casos.
Para probar primero sin guardar cambios, quitar `--aplicar`.
Cambiar el contenedor, ID de elección o usuario si son diferentes en ese equipo.

La elección debe estar En preparación y tener los cuatro claustros, sus
departamentos y el padrón de segmento_1_500 ya cargados. Los candidatos no pueden
ser autoridades activas en esa base. El comando no importa padrones, no elimina
autoridades y no cambia estados de elección. El usuario indicado debe tener
permisos locales de administrador de junta. Si falla algún requisito, revierte
todo, incluido el vaciado de las listas anteriores.

`crear_listas_para_csv.py` está en esta carpeta común a los cuatro claustros.
Lee los metadatos y los CSV ya preparados en `listas_*_sin_autoridades/`.
Prepara catorce presentaciones y cincuenta asociaciones con puestos:

| Claustro | Presentaciones | Asociaciones con puestos |
|---|---:|---:|
| Estudiantes: 19 y 3 | 2 | 12 |
| Graduados: 19 y 3 | 2 | 12 |
| Docentes: 19 y 2, tres sublistas y una lista solo DASUTeN por familia | 8 | 20 |
| No docentes: 9 y 3, Superior, Directivo y DASUTeN | 2 | 6 |

`crear_listas_para_csv.py` no carga candidatos. Se pueden cargar manualmente desde
**Importar por CSV (uno o varios puestos)** o usar `cargar_candidatos_csv.py` para
procesar todos los archivos en una sola operación. En Estudiantes se usa la
variante de `multipuesto/`; el importador la elige automáticamente.

Los apoderados de los archivos son ejemplos ficticios externos al padrón. Si una
presentación ya existe, se conserva su código y su apoderado registrado. No se
reemplazan datos, candidatos ni asociaciones existentes. Se agregan solamente
las listas y asociaciones que falten, con auditoría, en una única transacción.

## Requisitos

- Elegir explícitamente una elección mediante su ID; debe estar **En preparación**.
- Esa elección debe tener asociados los claustros y los departamentos K, I y R
  necesarios para los archivos elegidos.
- En Parámetros deben estar habilitados los puestos para cada claustro y deben
  haberse generado en la elección. Se puede sincronizar con el comando existente
  `python manage.py sincronizar_puestos_eleccion ID` después de configurar los parámetros.
- Los cupos deben admitir las cantidades de los CSV y permitir cubrir al menos
  el 50 % por tipo. Para **Directivo de Docentes se usa 2 titulares y 2 suplentes**,
  según lo confirmado para estos casos. Los demás cupos corresponden a los LEEME
  de cada claustro. DASUTeN de No docentes carga 1+1 sobre el cupo estándar 2+2.
- Usar el Python y las variables de entorno del proyecto existente. No se incluyen
  conexiones ni credenciales en el script.

El script `crear_listas_para_csv.py` no crea puestos ni modifica cupos, claustros, departamentos o padrones.
Si falta configuración o hay identidades ambiguas/inactivas, informa los motivos
y no guarda nada. La repetición del número 19 o 2 entre sublistas docentes se
resuelve con sus códigos y nombres diferentes. Una lista existente se busca por
código y, si no coincide uno, por claustro, número y nombre; no basta el número.

## Ejecutar con Python del proyecto

Desde la raíz del repositorio, reemplazando `4` por el ID correspondiente:

```powershell
python .\ESCENARIOS_PRUEBA_ELECTORAL\segmento_1_500\crear_listas_para_csv.py --eleccion 4
```

Sin `--aplicar`, solamente valida y previsualiza; no escribe datos ni auditoría.
Para guardar:

```powershell
python .\ESCENARIOS_PRUEBA_ELECTORAL\segmento_1_500\crear_listas_para_csv.py --eleccion 4 --aplicar
```

Para un solo claustro, agregar `--claustro estudiantes`, `--claustro graduados`,
`--claustro docentes` o `--claustro no_docentes`. Se puede repetir ese argumento.
Opcionalmente, `--usuario nombre_usuario` registra al usuario activo indicado
como responsable de auditoría; sin él queda identificado el origen del script.

## Ejecutar en la instancia Docker actual

Copiar esta carpeta al contenedor, desde la raíz del repositorio:

```powershell
docker cp .\ESCENARIOS_PRUEBA_ELECTORAL\segmento_1_500\. votoutn-validacion-web-nuevo:/tmp/segmento_1_500_listas
docker exec votoutn-validacion-web-nuevo python /tmp/segmento_1_500_listas/crear_listas_para_csv.py --proyecto /app --eleccion 4
```

Para guardar, repetir el segundo comando agregando `--aplicar`.
La conexión será la configurada en ese contenedor. No se crea otra base.
Si cambian los CSV o el script, repetir la copia antes de ejecutarlo.

## Cargar automáticamente todos los candidatos

`cargar_candidatos_csv.py` crea o reutiliza las listas y sus asociaciones y aplica
cada archivo a su presentación y claustro. Usa la previsualización y confirmación
nativas de la aplicación: valida padrón activo, claustro, departamento, autoridades,
tipo, orden y cupos. No importa padrones ni configura parámetros por defecto.

`--preparar-puestos` configura explícitamente los puestos y cupos requeridos por
estos CSV y genera los puestos de la elección. Conserva otras asociaciones del
catálogo y rechaza órganos/puestos ambiguos, inactivos o con alcance incompatible.
También rechaza reducciones incompatibles con candidaturas existentes. En conjunto
con `--reiniciar-listas`, primero vacía las candidaturas de esa elección y después
prepara sus puestos, todo dentro de la misma transacción. Los cambios quedan
auditados. No crea los claustros ni departamentos de la elección.

Después de copiar nuevamente esta carpeta al contenedor, previsualizar en la
instancia 2 con el ID de elección y usuario de junta correspondientes:

```powershell
docker cp .\ESCENARIOS_PRUEBA_ELECTORAL\segmento_1_500\. voto-utn-2-web-1:/tmp/candidatos_segmento_1
docker exec voto-utn-2-web-1 python /tmp/candidatos_segmento_1/cargar_candidatos_csv.py --proyecto /app --eleccion 1 --usuario juanb --ajustar-asociaciones
```

Para guardar, agregar `--aplicar` al segundo comando. Sin esa opción se simula
la carga completa y se revierte al terminar. Si falla cualquier archivo, se
revierte toda la operación. Se puede filtrar con `--claustro`, igual que en la
creación de listas. Las candidaturas idénticas ya cargadas se validan y omiten;
se pueden completar listas parcialmente cargadas sin reemplazar personas.

Para empezar de cero en la elección indicada, usar `--reiniciar-listas`:

```powershell
docker exec voto-utn-2-web-1 python /tmp/candidatos_segmento_1/cargar_candidatos_csv.py --proyecto /app --eleccion 1 --usuario juanb --reiniciar-listas --aplicar
```

Esta opción elimina las candidaturas, las asociaciones y todas las presentaciones
anteriores de esa elección, incluidas las creadas manualmente, antes de cargar
los catorce CSV. Guarda su copia en auditoría. Conserva los puestos configurados,
sus cupos, los padrones y las demás elecciones. No se puede combinar con filtros
de claustro. Un error revierte tanto el vaciado como la carga; sin `--aplicar`
también revierte todo al terminar la previsualización.

`--ajustar-asociaciones` retira de estas presentaciones únicamente asociaciones
vacías que ya no aparecen en los CSV: por ejemplo, Directivo en las listas
docentes de DASUTeN. También permite retirar asociaciones vacías a puestos
inactivos reemplazados desde Parámetros. Si tienen candidatos, se cancela en
lugar de borrarlos. Sin esa opción se conservan las asociaciones adicionales.

Los archivos contienen 460 candidaturas para 340 personas distintas:
Estudiantes 88; Graduados 72; Docentes 272 (152 personas, por Superior compartido);
No docentes 28. Cada lista de No docentes incluye Superior 5+5, Directivo 1+1
y DASUTeN 1+1. Las dos listas docentes de DASUTeN tienen solo ese cuerpo, 2+2.
La repetición de Superior dentro de las sublistas docentes produce advertencias
informativas de la aplicación y se conserva como parte del caso solicitado.

Los candidatos se eligieron excluyendo las autoridades de la foto original de
instancia 3. En una base distinta, el importador vuelve a comprobar las autoridades
actuales: si alguien tiene una designación activa, rechaza el archivo. No elimina
ni desactiva autoridades para hacer pasar la importación.

## Pruebas de creación y carga

Las pruebas están en `test_crear_listas_para_csv.py`, junto al script. Se ejecutan
con Django y PostgreSQL en su base de pruebas separada:

```powershell
docker exec voto-utn-2-web-1 python manage.py test /tmp/candidatos_segmento_1 --pattern=test_*csv.py --noinput
```

Comprueban creación sin candidatos, carga de los catorce CSV, previsualización
sin cambios persistidos, repetición sin duplicados, continuación de cargas
parciales, puestos ocupados por otra persona, roles de usuario, asociaciones
adicionales vacías o con candidatos y reversión ante errores.

La previsualización de la elección 4 del 18 de noviembre de 2026 encontró sin
asociar Graduados y No docentes y detectó puestos faltantes de Docentes y
Superior de Estudiantes. No se ejecutó `--aplicar` sobre la base habitual.
