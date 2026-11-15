# Verificación de los escenarios

## Unificación de cambios de sede — 2026-11-15

- `cambios` reúne las diez solicitudes originales y las nueve adicionales del primer caso. `ampliar_cambios` se conserva como alias del mismo lote.
- Tres solicitantes compartidos por la nómina pequeña y las dos nóminas de 198: Santiago Gómez, Pablo Benítez y Andrés González. El CSV pequeño conserva doce personas y no se cambian padrones ni nóminas completas.
- La carga conserva autoridades, omite solicitudes existentes en cualquier estado y completa las faltantes. Si parte del lote ya fue aprobada, no exige crear nuevamente dos mesas adicionales.
- Doce pruebas offline aprobadas: cantidades, reproducibilidad, tres solicitantes compartidos, conservación de CSV, configuración inválida y archivo de históricos.
- Cuatro flujos integrados aprobados en PostgreSQL separado de la demo: tres segmentos y nómina con movilidad. En el primero se verifican diecinueve solicitudes, dos mesas nuevas, tres solicitantes designados en el aviso real de revisión, simulación sin persistencia, alias sin duplicados y conservación de una aprobación previa al completar las nueve faltantes.
- Simulación en la elección 4: diecinueve solicitudes existentes, cero nuevas, ocho solicitantes con designación, incluidos los tres de la nómina pequeña; dos mesas adicionales estimadas. No se modificaron solicitudes ni designaciones de la elección activa.
- `check`, `makemigrations --check` y `migrate --plan`: correctos, sin cambios ni migraciones pendientes.
- Suite general: 671 pruebas aprobadas (270,2 segundos). El primer intento detectó la expectativa obsoleta del aviso de autoguardado; se actualizó la prueba al comportamiento solicitado y la repetición completa pasó.

Archivos modificados:

- `ejecutar_escenario.py`, `motor_django.py` y `generar_escenarios.py`.
- `test_generador.py` y `test_integracion.py`.
- `DECISIONES.md`, `GUION.md` y este registro.
- `segmento_1_500/nomina_estudiantes_pequena.csv`; `control.json` de los tres segmentos; metadatos `DECISIONES_GENERACION.md` y `VERSION_GENERADA.json`.
- `VotoUTN/apps/padron/tests.py`: se actualiza la expectativa de la prueba existente al aviso de autoguardado retirado anteriormente y se verifica que el botón de guardar permanezca.

La regeneración archiva la versión anterior en `historicos/`. No se eliminan archivos ni se cambian modelos o migraciones.

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
