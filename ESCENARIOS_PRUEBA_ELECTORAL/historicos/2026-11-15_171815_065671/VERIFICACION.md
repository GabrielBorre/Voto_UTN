# Verificación de los escenarios

Fecha: 2026-11-15. Rama: `feat/padron-multidepartamento`.

Se agregan únicamente esta carpeta y sus archivos. No se modifican modelos,
migraciones, QR, manuales ni configuraciones de la aplicación.
No se cargaron estos escenarios en la elección activa de Docker.

## Pruebas de generación

Siete pruebas offline aprobadas: cantidades, nombres, semillas, archivos repetibles,
reservas, nómina pequeña, reutilización de otros claustros en el tercer segmento,
archivo de versiones, distribución independiente por claustro y rechazo de archivos
alterados o configuración inválida. Los 27 CSV finales coinciden byte a byte con
los utilizados en los tres flujos integrados.

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
- Suite general: 671 pruebas aprobadas en PostgreSQL 18.4 (365,6 segundos).

El primer intento de la suite general se ejecutó con aislamiento que impedía leer
la extensión local `zxingcpp`: el módulo aparecía sin `read_barcodes`. La prueba QR
afectada pasó al ejecutarse con acceso a esa biblioteca, sin cambiar la aplicación.
La repetición completa también aprobó las 671 pruebas, sin errores pendientes.

## Nómina alternativa con movilidad — 2026-11-15

Se agrega `segmento_1_500/nomina_estudiantes_movilidad.csv`, con 198 personas.
Ocho pruebas offline y una nueva prueba integrada aprobadas. Se conservaron
byte a byte los 27 CSV anteriores; el nuevo archivo sustituye cuatro candidatos
de Electrónica/Medrano por cuatro de Electrónica/Campus que no tienen actividad
ese día ni departamentos adicionales. Carlos y los solicitantes no participan.

| Alternativa | Autoridades cubiertas | Faltantes | Cambios de sede |
|---|---:|---:|---:|
| Vota y ejerce en su mesa | 194 | 4 | 0 |
| Vota y ejerce en mesas distintas | 194 | 4 | 0 |
| Vota y ejerce en otra mesa | 194 | 4 | 0 |
| Vota y ejerce en otra sede | 198 | 0 | 4 |
| Cambia de sede y reordena mesas | 198 | 0 | 4 |

Se verificó la previsualización sin persistencia y la confirmación real de las
dos alternativas que cambian sede, dentro de transacciones de prueba. Ambas
mantienen entre dos y tres autoridades por mesa y turno, una persona por plaza
y las exclusiones previstas. No se aplicó la nómina ni se borraron designaciones
en la elección del usuario. `check`, `makemigrations --check` y `migrate --plan`
siguen sin errores ni cambios pendientes. No hay cambios en código de la app.
