# Demostración de autoridades y cambios de sede

Estos datos y comandos son para una elección de prueba. Los comandos se ejecutan
desde la carpeta del repositorio que contiene `docker-compose.yml`, con la app
levantada mediante `docker compose up -d`. El servicio Django se llama `web`.
Los comandos de generación de solicitudes y cierre de plazo se mantienen solo
en esta copia local y no están incluidos en el commit.

## Archivos

- `padron_estudiantes_500.csv`: padrón de 500 estudiantes ficticios.
- `autoridades_estudiantes_500.csv`: nómina de los mismos 500 estudiantes.
- `padron_alumno_keycloak_carlos.csv`: padrón adicional de Carlos Gómez,
  usuario de Keycloak `alumnocg`, DNI 38999222 y legajo 4444443.
- `autoridades_alumno_keycloak_carlos.csv`: nómina de Carlos Gómez, para
  incorporarlo como candidato después de importar su padrón.

Carlos Gómez no es Carlos González, que es otra persona del archivo de 500.
La nómina incorpora candidatos: no garantiza que una persona resulte elegida.
Si necesitás probar con Carlos, revisá su asignación y elegilo manualmente antes
de confirmar las autoridades definitivas.

## Preparar la elección

1. Finalizá la elección anterior antes de crear otra activa. Creá una elección
   de prueba y anotá su ID; reemplazá `ID` por ese número en los comandos.
2. Habilitá Estudiantes, los departamentos del archivo, Campus y Medrano, y
   los turnos de cursada que usa el padrón. Cargá el padrón de 500 y el de
   Carlos como importaciones separadas.
3. Configurá las reglas de sede y un máximo de **25 electores por mesa**.
   Verificá que se asignen sedes y mesas automáticamente; los resultados
   concretos dependen de las reglas y departamentos habilitados.
4. En Autoridades configurá los turnos de mañana y tarde. Para probar luego
   redistribuciones, usá como ejemplo **mínimo 1 y máximo 3 titulares por mesa
   y turno**. Ya no se configuran suplentes.
5. Probá sorteo, selección manual o nómina. Al cargar la nómina, revisá las
   cinco alternativas y confirmá la elegida. Para incluir a Carlos, cargá también
   su archivo de nómina y comprobá si fue asignado; podés elegirlo manualmente.
   Las asignaciones en preparación son provisorias.

## Solicitudes de cambio de sede

1. Publicá la elección, dejando una fecha de cierre futura para permitir
   solicitudes. El generador requiere sedes habilitadas, electores con mesa y
   un período de solicitudes abierto.
2. Simulá un lote concentrado. Sin `--cantidad`, busca suficientes solicitudes
   para superar la capacidad disponible en la sede de destino; es un escenario
   para intentar provocar cambios en las mesas, no una garantía del resultado:

   ```powershell
   docker compose exec web python manage.py generar_solicitudes_prueba --eleccion ID
   ```

3. Para crear el lote mostrado, repetí el comando agregando `--aplicar`. Si
   querés un tamaño específico, agregá `--cantidad 25` en ambos comandos.
   Se crean solicitudes pendientes, sin aprobar ni modificar mesas.
4. En la aplicación, revisá y aprobá o rechazá las solicitudes. La aprobación
   muestra una propuesta de movimientos y posibles autoridades afectadas;
   los cambios se aplican al confirmar. Después revisá y completá la cobertura
   de autoridades provisoria.

## Adelantar el cierre para la demostración

Una vez creadas las solicitudes y cuando quieras cerrar el período, simulá el
cambio de fecha. Por defecto usa el día anterior al actual:

```powershell
docker compose exec web python manage.py cerrar_plazo_cambio_sede_prueba --eleccion ID
```

Para guardar la fecha mostrada, repetí agregando `--aplicar`. Para elegir otra,
agregá `--fecha AAAA-MM-DD` a ambos comandos. La fecha no puede ser anterior al
inicio del proceso electoral; si se crea la elección el mismo día de la demo,
configurá su inicio al día anterior para poder cerrar el plazo por esta vía.
El comando no resuelve solicitudes pendientes: la Junta debe resolverlas antes
de confirmar autoridades.

## Confirmación y justificativos

1. Completá la cobertura, cerrá el plazo y resolvé todas las solicitudes de
   cambio de sede. Confirmá las autoridades y fijá el plazo para justificar.
2. Ingresá con `alumnocg`, si Carlos quedó asignado, y presentá un justificativo
   por imposibilidad de ser autoridad. Desde la Junta, aprobalo y revisá la mesa
   afectada en el listado de Autoridades.
3. Para cubrir una vacante por justificativo, el sistema propone titulares de
   otra mesa de la misma sede, departamento y turno, siempre que su mesa de
   origen conserve el mínimo. La Junta confirma cada traslado; la persona
   conserva su mesa de votación. Para poder ver propuestas conviene que alguna
   mesa tenga más titulares que el mínimo.
4. Resolvé los justificativos pendientes y revisá los mínimos antes de pasar
   a En curso. La validación del mínimo existe al iniciar la elección, pero
   actualmente **no bloquea la confirmación inicial de autoridades**.

El correo del entorno local necesita un servidor SMTP configurado; si no está
disponible, los envíos pueden fallar aunque las notificaciones se registren.
Los cambios realizados directamente en la base de datos de una elección anterior
no forman parte del repositorio ni se replican en la elección nueva.
