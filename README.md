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
`voto-utn-2` y `voto-utn-3`. Cada proyecto tiene sus propios cinco contenedores
(PostgreSQL, Keycloak, Mailpit, Django y Caddy), red y volumenes. No modifica
el despliegue existente de `docker-compose.yml`, que puede seguir funcionando.

| Instancia | App HTTPS | HTTP (redirige) | Keycloak | Mailpit | PostgreSQL | SMTP |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | https://localhost:8444 | 8001 | http://localhost:8081/instancia-1/ | http://localhost:8026 | 5433 | 1026 |
| 2 | https://localhost:8445 | 8002 | http://localhost:8082/instancia-2/ | http://localhost:8027 | 5434 | 1027 |
| 3 | https://localhost:8446 | 8003 | http://localhost:8083/instancia-3/ | http://localhost:8028 | 5435 | 1028 |

En una base nueva, la instancia 1 carga automaticamente los parametros y las
identidades locales de `juanb` y `administrativojunta`, sin crear ninguna eleccion
ni padron. Los electores de Keycloak se vinculan al importar el padron; no se
asignan autoridades antes de crear la eleccion. Las instancias 2 y 3 solo aplican
las migraciones. Keycloak importa el realm de demostracion por separado en cada
instancia.

La carga inicial se ejecuta solo al crear una base nueva; reiniciar o reconstruir
no vuelve a modificar datos existentes. Si falla durante la primera carga, el
arranque informa el error y la reintenta. Para cargarla manualmente en otra
instancia, ejecutar `python manage.py seed_demo_inicial` en su contenedor `web`.
El comando actualiza los parametros estandar y conserva las identidades existentes.
Los comandos anteriores `seed_demo_data` y `seed_keycloak_demo` siguen disponibles
para su escenario anterior; el primero **crea una eleccion**.

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

`stop`, `start` y `down` no eliminan volumenes. Mailpit mantiene los mensajes
en el contenedor: se pierden al recrearlo. No usar `down --volumes` si se necesitan
conservar los datos. Para ejecutar comandos Django sobre una instancia:

```powershell
docker compose -p voto-utn-1 --env-file .\.instancias\instancia-1.env -f .\docker-compose.instancias.yml exec web python manage.py createsuperuser
docker compose -p voto-utn-1 --env-file .\.instancias\instancia-1.env -f .\docker-compose.instancias.yml exec web python manage.py check
```

---

*Proyecto de la Universidad Tecnológica Nacional - Facultad Regional Buenos Aires*
