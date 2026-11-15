# Verificación de los escenarios

Fecha: 2026-11-15. Rama: `feat/padron-multidepartamento`.

Se agregan únicamente esta carpeta y sus archivos. No se modifican modelos,
migraciones, QR, manuales ni configuraciones de la aplicación.
No se cargaron estos escenarios en la elección activa de Docker.

## Pruebas de generación

Seis pruebas offline aprobadas: cantidades, nombres, semillas, archivos repetibles,
reservas, nómina pequeña, reutilización de otros claustros en el tercer segmento,
archivo de versiones y rechazo de archivos alterados o configuración inválida.

## Flujo con servicios reales

Tres pruebas integradas aprobadas en una base de pruebas PostgreSQL 18.4 separada.
Cada prueba crea su elección con los cuatro claustros e importa los cuatro CSV
mediante los servicios reales. Ejecuta designaciones manuales, previsualización y
confirmación de nómina, sorteo, solicitudes, aprobación, recálculo, confirmación
definitiva y presentación/resolución de justificativos.

| Estudiantes | Solicitudes automáticas + Carlos | Mesas nuevas al aprobar | Justificativos | Previsualización y confirmación de nómina |
|---|---:|---:|---:|---:|
| 500 | 10 + 1 | 1 | 3 | 15,4 s |
| 1000 | 20 + 1 | 1 | 5 | 24,4 s |
| 2000 | 40 + 1 | 1 | 8 | 50,2 s |

Los tiempos corresponden al entorno local y a la nómina de doce personas,
incluyendo identificación, simulación de alternativas y confirmación. No son
una garantía de tiempo para otra instancia.

Se verifica además la previsualización sin persistencia, repetición sin duplicados,
preservación de designaciones previas, una autoridad por persona, exclusión de
Carlos y los solicitantes, y mínimos/máximos por mesa y turno antes y después de
aprobar los justificativos.

## Comprobaciones generales

- `manage.py check`: correcto.
- `manage.py makemigrations --check`: sin cambios.
- `manage.py migrate --plan`: sin operaciones pendientes en la base aislada de verificación.
- Suite general: ejecución final en curso al preparar este registro.

El primer intento de la suite general se ejecutó con aislamiento que impedía leer
la extensión local `zxingcpp`: el módulo aparecía sin `read_barcodes`. La prueba QR
afectada pasó al ejecutarse con acceso a esa biblioteca, sin cambiar la aplicación.
