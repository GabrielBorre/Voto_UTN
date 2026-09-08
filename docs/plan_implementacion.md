# Plan de implementacion

## Estado actual

**Cierre de modularizacion completado**

El sistema conserva un unico proyecto Django y distribuye el dominio entre apps
propietarias. El detalle verificable de cada entrega se mantiene en
`docs/registro_de_cambios.md`.

## Etapas implementadas

### Etapa 0 - Auditoria y estabilizacion
**Estado:** completada

Dependencias compatibles con Python 3.12 y Django 5.2, PostgreSQL por entorno,
secretos fuera del repositorio y base de pruebas del QR.

### Etapa 1 - Unificacion de nomenclatura
**Estado:** completada

Dominio, contratos principales y migraciones utilizan nomenclatura en espanol.

### Etapa 2 - Modelo base definitivo
**Estado:** completada

Incluye parametros, relaciones electorales, mesas, electores y padron.

### Etapa 3 - Usuarios, roles y permisos
**Estado:** completada con autenticacion local de desarrollo

Incluye perfiles, asignaciones de rol, alcance por eleccion, sede y mesa, y
navegacion inicial por permisos. La integracion institucional con Keycloak queda
en el backlog externo.

### Etapa 4 - Integracion definitiva del QR
**Estado:** completada

El QR utiliza un identificador opaco de `RegistroPadron`, firma separada,
validacion de eleccion y mesa, registro atomico y prevencion de duplicados.

### Etapa 5 - Gestion de elecciones
**Estado:** completada

Incluye parametros, creacion, configuracion por alcance, ciclo de estados y
gestion de mesas.

### Etapa 6 - Padrones e importaciones
**Estado:** completada

Incluye CSV, previsualizacion, validacion, confirmacion, errores e historial.

### Etapa 7 - Autoridades de mesa
**Estado:** completada

Incluye candidaturas, asignaciones, preferencias, confirmaciones y permisos.

### Etapa 8 - Justificativos
**Estado:** completada

Incluye presentacion, documentacion, bandeja, resolucion y trazabilidad.

### Etapa 9 - Notificaciones
**Estado:** base operativa completada

Incluye plantillas, generacion de envios, procesamiento, historial y lectura
interna. La configuracion del proveedor de correo de produccion queda pendiente.

### Etapa 10 - Reportes y exportaciones
**Estado:** completada

Incluye exportaciones operativas de padron, mesas, participacion, autoridades,
justificativos y errores de importacion.

### Etapa complementaria - Partidos y candidatos
**Estado:** completada

Incluye partidos reutilizables, participacion por eleccion, listas por alcance y
candidatos vinculados opcionalmente con un elector.

### Cierre de modularizacion
**Estado:** completado

- Los modelos pertenecen a sus apps de dominio.
- Las vistas, formularios, servicios, URLs y administracion estan separados.
- Las plantillas funcionales utilizan namespaces de su app propietaria.
- Los comandos de padron y notificaciones pertenecen a sus apps.
- `elecciones` conserva el nucleo transversal y `seed_demo_data` como orquestador.
- La app inactiva `pagina_web` fue eliminada; sus maquetas se conservan.

## Backlog externo a la modularizacion

- Integrar Keycloak mediante OIDC y validar criptograficamente los JWT.
- Incorporar gestion web completa de usuarios y asignaciones de rol.
- Configurar y verificar el proveedor real de correo electronico.
- Ejecutar una auditoria visual integral de las pantallas y sus maquetas.
- Preparar configuracion, observabilidad y seguridad para produccion.
