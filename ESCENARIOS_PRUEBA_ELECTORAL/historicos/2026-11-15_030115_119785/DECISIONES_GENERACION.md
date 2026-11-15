# Decisiones de los escenarios electorales

## Uso

Este es el registro de acuerdos y la fuente de configuración del generador.
Editar exclusivamente el bloque `json` siguiente para cambiar cantidades y reglas.
Ejecutar `python generar_escenarios.py` después de editarlo. No cambia elecciones.
Los porcentajes describen datos sintéticos plausibles, no matrícula institucional.
Una misma semilla reproduce identidades; cambiarla produce otras identidades.

## Configuración activa

```json
{
  "version": 1,
  "semilla": 2026,
  "departamentos": {"K": 40, "I": 25, "R": 10, "S": 7, "O": 6, "V": 5, "Q": 3, "U": 2, "W": 2},
  "distribucion_por_claustro": {"estudiantes": {}, "docentes": {}, "graduados": {}},
  "porcentaje_medrano": {"estudiantes": 50, "docentes": 50, "no_docentes": 50},
  "secundarios": {"K": 50, "I": 30, "R": 20},
  "docentes_basicas_porcentaje": 20,
  "actividad_porcentaje": {"estudiantes": 60, "docentes": 70, "graduados": 0, "no_docentes": 100},
  "maximo_mesa": {"estudiantes": 60, "docentes": 200, "graduados": 200, "no_docentes": 200},
  "codigos_claustro": {"estudiantes": "EST", "docentes": "DOC", "graduados": "GRAD", "no_docentes": "ND"},
  "sedes": ["Campus", "Medrano"],
  "sede_unica_estudiantes": {"Q": "Campus"},
  "sede_electoral": {"docentes": "Medrano", "graduados": "Medrano"},
  "turnos": ["Mañana", "Tarde", "Noche"],
  "autoridades": {"minimo": 2, "maximo": 3, "manuales": 2, "nomina_pequena": 12},
  "segmentos": [
    {"carpeta": "segmento_1_500", "personas": {"estudiantes": 500, "docentes": 500, "graduados": 500, "no_docentes": 500}, "adicionales": {"estudiantes": 100, "docentes": 100}, "solicitudes": 10, "justificativos": 3},
    {"carpeta": "segmento_2_1000", "personas": {"estudiantes": 1000, "docentes": 1000, "graduados": 1000, "no_docentes": 1000}, "adicionales": {"estudiantes": 150, "docentes": 150}, "solicitudes": 20, "justificativos": 5},
    {"carpeta": "segmento_3_2000", "personas": {"estudiantes": 2000, "docentes": 1000, "graduados": 1000, "no_docentes": 1000}, "adicionales": {"estudiantes": 200, "docentes": 150}, "solicitudes": 40, "justificativos": 8}
  ]
}
```

## Acuerdos y criterios de generación

- `departamentos` es la distribución base de ingenierías. Para cambiar solo un claustro, completar su objeto en `distribucion_por_claustro` con los nueve códigos y porcentajes que sumen 100; un objeto vacío hereda la base. En docentes, esos porcentajes distribuyen el resto después de reservar Ciencias Básicas.
- `porcentaje_medrano` define el reparto inicial por sede (de actividad en docentes, de trabajo en no docentes); las sedes electorales fijas, los grupos pequeños y el ajuste de Sistemas tienen prioridad. Los porcentajes finales por sede pueden diferir debido a esas reglas.
- Cada segmento se prueba en una elección distinta, secuencialmente. Cada carpeta es autosuficiente.
- Las cantidades son personas únicas. Un secundario agrega una fila con la misma identidad y un departamento diferente. Graduados no tienen secundarios; no docentes tampoco tienen departamento.
- Nombres y apellidos habituales, incluyendo tildes y ñ. Nada de nombres numerados o cadenas aleatorias. DNI y legajo únicos; los nombres pueden repetirse.
- Carlos Gomez conserva DNI 38999222 y legajo 4444443. Es estudiante de Sistemas, nivel inicial, sin actividad ese día, inicialmente Campus. Se excluye de autoridades y de solicitudes automáticas. Se solicita manualmente Campus → Medrano; su futura ausencia electoral queda fuera de esta etapa.
- Estudiantes: la actividad determina sede; sin actividad, niveles 1–3 Campus y 4–5 Medrano. Una sede única tiene prioridad. Los registros secundarios comparten sede electoral con el principal.
- Docentes y graduados votan en la sede fija configurada. No docentes votan donde trabajan; todos informan sede y turno. Actividad no equivale a participación electoral.
- Se distribuyen sedes y turnos equilibradamente. Los grupos estudiantiles pequeños ocupan una sola sede para poder cubrir autoridades. En Sistemas se lleva el tamaño de Medrano a un múltiplo del máximo por mesa próximo a la mitad, para mostrar mesas nuevas con pocos cambios.
- Secundarios concentrados en tres departamentos, seleccionados entre personas sin actividad; no se obliga a ocupar todas las sedes habilitadas. Redondeo por mayor resto, conservando totales.
- Cada persona ocupa como máximo una plaza de autoridad en toda la elección. El control utiliza emparejamiento de personas y plazas, respetando actividad y mesas especiales.
- Dos autoridades manuales y una nómina estudiantil pequeña, distintas entre sí; luego sorteo conservando designaciones. Los otros claustros se sortean. No usar «Recalcular» si elimina las selecciones manuales.
- Solicitantes automáticos sin actividad, sin secundarios y sin designaciones. Carlos se agrega aparte: totales efectivos 11/21/41 con los valores iniciales.
- Las nuevas mesas se verifican con servicios reales y el estado actual: objetivo entre una y nueve. No basta estimar por división. Las autoridades de otras personas pueden verse afectadas por reordenamientos; revisar el impacto y completar vacantes antes de confirmar.
- Justificativos pendientes únicamente de autoridades estudiantiles: uno por grupo mesa/turno con tres titulares, manteniendo al menos dos tras aprobarlos. Si no hay suficientes casos seguros, el script se detiene sin crear un lote parcial.
- Los correos deben terminar en `@frba.utn.edu.ar` porque el importador actual rechaza otros dominios. Se usan direcciones sintéticas `escenario.*`; ejecutar la demostración con Mailpit o backend local, nunca procesar esos correos hacia un servidor institucional real.
- No se crean cuentas ni se modifica Keycloak. No se sobrescriben identidades existentes desde estos scripts. La importación de padrones y las configuraciones se confirman por interfaz.
- Nómina pequeña no garantiza una previsualización rápida: el servicio simula alternativas sobre el padrón completo. Medir tiempos; optimizarlo no forma parte de esta entrega.

## Históricos

Cada regeneración valida primero todos los archivos. Antes de reemplazarlos copia a
`historicos/FECHA_HORA/` la versión previa de CSV, scripts, decisiones y guion.
`DECISIONES_GENERACION.md` conserva el documento exacto usado para esa versión,
incluso si ya editaste el documento activo. No se archivan históricos dentro de históricos.
Cambiar el documento no actualiza CSV ni bases automáticamente. Los scripts rechazan
archivos alterados o desactualizados y no cambian configuraciones de la elección.

## Registro de acuerdos

- 2026-11-15: configuración central en Markdown, tres segmentos, nombres reales ficticios y archivo automático de versiones anteriores.
- 2026-11-15: límites estudiantiles de 60 y de 200 para los demás claustros; no docentes con actividad en todos los registros; docentes y graduados en Medrano.
