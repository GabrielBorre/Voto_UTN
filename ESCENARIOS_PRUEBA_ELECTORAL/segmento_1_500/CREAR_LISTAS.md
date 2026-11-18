# Crear las listas donde se cargarán los candidatos

`crear_listas_para_csv.py` está en esta carpeta común a los cuatro claustros.
Lee los metadatos y los CSV ya preparados en `listas_*_sin_autoridades/`.
Prepara catorce presentaciones y cincuenta asociaciones con puestos:

| Claustro | Presentaciones | Asociaciones con puestos |
|---|---:|---:|
| Estudiantes: 19 y 3 | 2 | 12 |
| Graduados: 19 y 3 | 2 | 12 |
| Docentes: 19 y 2, tres sublistas y una lista DASUTeN por familia | 8 | 22 |
| No docentes: 9 y 3 | 2 | 4 |

No carga candidatos: después se cargan los CSV desde **Importar por CSV (uno o
varios puestos)** dentro de cada lista. El resultado del script indica el archivo
correspondiente. En Estudiantes hay que usar la variante de `multipuesto/`.

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

El script no crea puestos ni modifica cupos, claustros, departamentos o padrones.
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

## Verificación

Las pruebas están en `test_crear_listas_para_csv.py`, junto al script. Se ejecutan
con Django y PostgreSQL en su base de pruebas separada:

```powershell
docker exec votoutn-validacion-web-nuevo python manage.py test /tmp/segmento_1_500_listas --pattern=test_crear_listas_para_csv.py --noinput
```

Comprueban creación sin candidatos, previsualización sin escrituras, segunda
ejecución sin duplicados, reutilización de listas manuales, conservación del
apoderado, recuperación de asociaciones faltantes y reversión ante errores.

La previsualización de la elección 4 del 18 de noviembre de 2026 encontró sin
asociar Graduados y No docentes y detectó puestos faltantes de Docentes y
Superior de Estudiantes. No se ejecutó `--aplicar` sobre la base habitual.
