# Diagramas entidad-relacion

Estos archivos muestran la estructura persistida del dominio, no el comportamiento
de las clases. Las clases con atributos y metodos siguen en el directorio padre.

## Convenciones

- `<<PK>>`: clave primaria.
- `<<FK>>`: clave foranea. El sufijo `_id` conserva el nombre habitual de Django.
- `<<UQ>>`: unicidad simple o compuesta indicada en la entidad.
- `<<NULL>>`: columna nullable.
- `<<CK>>`: restriccion `CHECK`.
- Los conectores usan notacion pata de cuervo: `||` uno obligatorio, `o|` cero o uno,
  `o{` cero o muchos.
- Las entidades etiquetadas `referencia` corresponden a tablas definidas en otro
  diagrama; se muestran para hacer explicitas las FKs sin duplicar todos sus campos.
- Los nombres de entidad son nombres de dominio. Las tablas trasladadas entre apps
  conservan nombres fisicos historicos `elecciones_*` cuando asi lo define el modelo.

## Diagramas

- `01_elecciones_parametros.puml`: catalogos, configuracion y fechas de elecciones.
- `02_padron.puml`: identidad electoral, padron, importaciones y asignaciones/reglas.
- `03_jornada_electoral.puml`: mesas, autoridades y participacion.
- `04_candidaturas.puml`: puestos, presentaciones, listas y candidaturas.
- `05_gestion_y_soporte.puml`: roles, justificativos, notificaciones y auditoria.

Las claves y relaciones reflejan el modelo Django actual. Las etiquetas de tipo son
equivalencias legibles para PostgreSQL (`bigint`, `varchar`, `jsonb`, `timestamptz`, etc.);
no sustituyen una introspeccion del esquema desplegado.
