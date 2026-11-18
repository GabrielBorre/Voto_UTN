# Voto_UTN

Este es un proyecto para la **UTN FRBA** (Universidad Tecnológica Nacional - Facultad Regional Buenos Aires).

## Descripción

Proyecto académico desarrollado como parte del plan de estudios de la UTN FRBA.

## Contribuidores

- Gabriel Borre
- Nicolás Calle
- Martín Domínguez
- Omar Scarazzato

## Tres instancias Docker independientes

Desde la raiz del repositorio, en PowerShell:

```powershell
.\scripts\instancias.ps1 up
```

Docker Desktop agrupa los contenedores en los proyectos `voto-utn-1`,
`voto-utn-2` y `voto-utn-3`. Cada proyecto tiene sus propios seis contenedores
(PostgreSQL, Keycloak, Mailpit, Django, trabajador de notificaciones y Caddy), red y volumenes. No modifica
el despliegue existente de `docker-compose.yml`, que puede seguir funcionando.

| Instancia | App HTTPS | HTTP (redirige) | Keycloak | Mailpit | PostgreSQL | SMTP |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | https://localhost:8444 | 8001 | http://localhost:8081/instancia-1/ | http://localhost:8026 | 5433 | 1026 |
| 2 | https://localhost:8445 | 8002 | http://localhost:8082/instancia-2/ | http://localhost:8027 | 5434 | 1027 |
| 3 | https://localhost:8446 | 8003 | http://localhost:8083/instancia-3/ | http://localhost:8028 | 5435 | 1028 |

En una base nueva, las instancias 1 y 2 cargan automaticamente los parametros y las
identidades locales de `juanb` y `administrativojunta`, sin crear ninguna eleccion
ni padron. Los electores de Keycloak se vinculan al importar el padron; no se
asignan autoridades antes de crear la eleccion. La foto fija de PostgreSQL
descrita abajo ya no se restaura al levantar la instancia 2; solo se aplica con
la accion `restaurar-foto`. Keycloak importa el realm de demostracion por
separado en cada instancia.

### Foto fija actual de la instancia 3

La foto activa esta en `.instancias\foto-instancia-3-v2`, creada el 18 de
noviembre de 2026 a partir de la captura original. Corrige el apellido del
elector de demostracion Carlos a «Gómez», sin cambiar sus identificadores,
asignaciones, QR ni los demas datos. La foto anterior permanece intacta en
`.instancias\foto-instancia-3`; `up` ya no la selecciona.

Ambas carpetas contienen `postgres.sql`, `archivos.tar.gz` (volumenes `media`
y `generated_qrs`) y `huellas.json` con sus SHA-256. La captura original se
realizo el 17 de noviembre con Django y el trabajador detenidos; la nueva se
edito y verifico en bases temporales, sin incorporar cambios posteriores de la
instancia de trabajo. Incluye la eleccion «Demo 2026» con 352 inasistencias,
41 mesas procesadas y K-016, K-017, K-019 y K-046 pendientes. No incluye
Keycloak, los correos de Mailpit, las claves de entorno ni los certificados.
La nueva carpeta esta excluida de Git y debe conservarse junto con el entorno
`instancia-3.env`, necesario para validar los QR existentes.

**Cada `up` que incluya la instancia 3 reemplaza sus datos actuales por esa
foto, sin respaldo automatico**, incluso si sus volumenes ya existen:

```powershell
.\scripts\instancias.ps1 up
.\scripts\instancias.ps1 up -Instancia 3
```

Los cambios posteriores de la instancia 3 no se incorporan a la foto: el
arranque solo la lee y verifica sus huellas antes de detener servicios. Si falta
o fue alterada, cancela el arranque en lugar de crear datos alternativos.
La restauracion detiene Django y el trabajador, reemplaza el esquema `public`
en una transaccion y reemplaza los adjuntos y QR, eliminando archivos de trabajo
que no estaban en la captura. Si falla, no vuelve a levantar esos servicios;
PostgreSQL y archivos no forman una unica transaccion y se debe reintentar
`up -Instancia 3` despues de resolver el error.

`start -Instancia 3` reanuda los datos de trabajo sin restaurarlos. Solo en
la instancia 3 se omite `iniciar_instancia_demo`: Django aplica migraciones,
recopila estaticos y arranca sin ejecutar la carga inicial de demostracion.
El codigo de la aplicacion sigue reconstruyendose con `up`; la foto es de
datos, no una imagen congelada del codigo. En todas las instancias, el PDF del
padron imprimible incluye «Demo Proyecto Final» y «VOTO UTN» en dos renglones como marca de agua en sus hojas y
caratulas, detras del contenido para preservar la lectura de los QR.
Las instancias 1 y 2 mantienen
su comportamiento anterior.

Para actualizar solo el codigo web de la instancia 3 sin restaurar la foto:

```powershell
docker compose --project-name voto-utn-3 --env-file .instancias\instancia-3.env --file docker-compose.instancias.yml up -d --no-deps --build --force-recreate web
```

`build web` solo compila la imagen: no reemplaza el contenedor en ejecucion.
Tras recrearlo, se debe generar y descargar nuevamente el PDF para ver cambios.

### Foto fija de PostgreSQL para la instancia 2

La foto `.instancias\foto-instancia-1.sql` se conserva, pero `up -Instancia 2`
ya no la restaura: la instancia 2 inicia como la 1, con la carga inicial
de demostracion en una base nueva. La foto solo se aplica con la accion
`restaurar-foto` descrita abajo. La foto se capturo de la instancia 1 el
16 de noviembre de 2026 y no se actualiza al arrancar: los cambios posteriores
en la instancia 1 no se copian. El archivo queda excluido de Git porque contiene todos
los datos de PostgreSQL, incluidas las identidades locales. La foto no incluye
el historial de archivos de nómina y conserva los tipos de justificativo
«Certificado medico», «Enfermedad o accidente», «Obligaciones laborales»,
«Otro» y «Cuidado de familiar». También se retiraron las
designaciones de autoridades del claustro Estudiantes, sus 3 turnos
configurados (con sus máximos y mínimos de titulares) y sus 198 candidatos a
autoridad de mesa; los demás claustros, electores, mesas y candidaturas se
conservan. Estos ajustes no modifican las
bases actuales de las instancias. La foto tampoco incluye el historial de
importaciones de padrón ni sus errores asociados; los registros del padrón
permanecen intactos.

Para reemplazar **todos los datos actuales** de la instancia 2 por esa foto,
sin respaldo automatico:

```powershell
.\scripts\instancias.ps1 restaurar-foto -Instancia 2
```

La restauracion detiene Django y el trabajador de la instancia 2 y reemplaza su
esquema `public` dentro de una transaccion. Si falla, PostgreSQL revierte los
cambios y ambos quedan detenidos para revisar el error. No modifica la instancia 1, ni copia
archivos adjuntos, QR generados, claves Django/QR o datos de Keycloak. Las
referencias a archivos de la instancia 1 pueden no tener su archivo en la 2;
los QR firmados con la clave de la instancia 1 no se validan con la clave de la 2.
Los siguientes arranques conservan los datos existentes de la instancia 2.
Las pruebas del script se ejecutan sin modificar contenedores ni bases:

```powershell
.\scripts\tests_instancias.ps1
```

### Carga inicial de demostracion

Al publicar, se generan hasta 30 solicitudes de Estudiantes sin designacion de
autoridad. Si hay menos candidatos compatibles, solo se crean las posibles,
sin avisar faltantes. Carlos queda reservado para su solicitud manual y no se
modifican las solicitudes de elecciones ya publicadas.

La carga inicial se ejecuta en las instancias 1 y 2, solo al crear una base nueva;
reiniciar o reconstruir no vuelve a modificar datos existentes. Si falla durante
la primera carga, el arranque informa el error y la reintenta. Para cargarla
manualmente, ejecutar `python manage.py seed_demo_inicial` en el contenedor `web`
correspondiente.
El comando actualiza los parametros estandar y conserva las identidades existentes.
También agrega idempotentemente los cinco tipos de justificativo indicados arriba.
Los comandos anteriores `seed_demo_data` y `seed_keycloak_demo` siguen disponibles
para su escenario anterior; el primero **crea una eleccion**.

### Notificaciones en segundo plano

El servicio `notificaciones` de ambos Compose ejecuta un trabajador persistente.
La publicacion y el inicio guardan un lote durable en la misma transaccion del
cambio de estado; el trabajador crea las notificaciones por lotes. Las demas
operaciones conservan sus notificaciones internas pendientes en PostgreSQL.
Ninguna peticion web espera el envio SMTP.

El trabajador prioriza los correos del elector de demostracion reservado para
la consulta manual, incluidos los dirigidos a su usuario local vinculado. Los
fallos transitorios se reintentan hasta tres veces con espera creciente; los
correos sin direccion o con encabezados invalidos quedan con error. La pantalla
de notificaciones muestra lotes, estados y errores. Un error no elimina el aviso
interno. Un reinicio conserva la cola y no reenvia registros marcados enviados.
Si el proveedor acepta un correo y el proceso muere antes de guardar el resultado,
el reintento puede duplicarlo: SMTP no garantiza entrega exactamente una vez.

Para desarrollo sin Docker, mantener en otra terminal
`python manage.py procesar_notificaciones --continuo`; sin `--continuo`, procesa
una tanda. Para inspeccionar una instancia:

```powershell
docker compose -p voto-utn-2 --env-file .\.instancias\instancia-2.env -f .\docker-compose.instancias.yml logs --tail 30 notificaciones
```

Las claves Django, QR, PostgreSQL
y administrador de Keycloak se generan una vez por instancia y se conservan en
`.instancias\instancia-N.env`, excluido de Git. No borrar esos archivos: contienen
las credenciales y las claves necesarias para las sesiones y los QR emitidos.
El administrador de Keycloak es `admin`; su clave esta en el archivo de esa instancia.

Los archivos subidos, QR generados, estaticos, datos de Keycloak y CA de Caddy
no se comparten. Las sesiones Django y las cookies de Keycloak tambien estan
separadas, aunque las tres apps se abran en `localhost`. Se comparte solamente
la imagen de la aplicacion y se montan en solo lectura el realm y el tema.
No hay montaje del codigo local: despues de cambiarlo, repetir `up` para reconstruir
la imagen y actualizar las instancias. El stack anterior conserva sus valores
predeterminados de puertos y cookies.

Para el celular, reemplazar `localhost` por la IP de la PC en la misma red Wi-Fi.
Cada instancia tiene su propia CA local de Caddy. Al ejecutar `up` o `start`, el
script obtiene su certificado publico y lo instala, si hace falta, en las
autoridades raiz de confianza del usuario actual de Windows. Windows puede pedir
confirmacion para confiar en la CA. Esta confianza permite a esa CA emitir
certificados para otros sitios, por lo que debe utilizarse solo en un entorno de
desarrollo confiable. Los certificados instalados no se eliminan con `down`.
En el celular se debe confiar por separado el certificado de cada instancia para
utilizar HTTPS y la camara. Es un entorno de desarrollo, no una configuracion de
produccion; Keycloak utiliza HTTP y realm con usuarios de demo.

```powershell
.\scripts\instancias.ps1 ps
.\scripts\instancias.ps1 stop -Instancia 2
.\scripts\instancias.ps1 start -Instancia 2
.\scripts\instancias.ps1 down -Instancia 3
.\scripts\instancias.ps1 up -Instancia 3
```

`stop`, `start` y `down` no eliminan volumenes. Recordar que `up` restaura
siempre la foto en la instancia 3. Mailpit mantiene los mensajes
en el contenedor: se pierden al recrearlo. No usar `down --volumes` si se necesitan
conservar los datos. Para ejecutar comandos Django sobre una instancia:

```powershell
docker compose -p voto-utn-1 --env-file .\.instancias\instancia-1.env -f .\docker-compose.instancias.yml exec web python manage.py createsuperuser
docker compose -p voto-utn-1 --env-file .\.instancias\instancia-1.env -f .\docker-compose.instancias.yml exec web python manage.py check
```

---

*Proyecto de la Universidad Tecnológica Nacional - Facultad Regional Buenos Aires*
