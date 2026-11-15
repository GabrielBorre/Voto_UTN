"""Verifica los CSV con los servicios reales en una base PostgreSQL de pruebas.

Ejecutar desde el contenedor web. Conserva el esquema de pruebas y revierte
todos los datos al finalizar; nunca importa en la base habitual.
"""
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[1]))

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections, transaction
from django.db.models import Count
from django.test import override_settings
from django.test.runner import DiscoverRunner
from django.utils import timezone

from apps.autoridades import nomina
from apps.autoridades.models import AsignacionAutoridad, ConfiguracionAutoridades
from apps.elecciones.models import (
    Eleccion, EleccionClaustro, EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede, EleccionClaustroSede, EleccionClaustroTurno, EleccionSede,
)
from apps.mesas.models import Mesa
from apps.padron.models import Elector, ImportacionPadron, RegistroPadron
from apps.padron.services import calcular_mesas_automaticas_eleccion, confirmar_importacion, validar_csv_padron
from apps.parametros.models import Claustro, Departamento, Sede, Turno


def main():
    conexiones = connections["default"]
    assert conexiones.vendor == "postgresql", "La prueba requiere PostgreSQL."
    nombre_pruebas = "test_archivos_padron_20000_20261108"
    conexiones.settings_dict["TEST"]["NAME"] = nombre_pruebas
    print(f"Preparando base aislada: {nombre_pruebas}", flush=True)
    DiscoverRunner(verbosity=0, interactive=False, keepdb=True).setup_databases()
    assert conexiones.settings_dict["NAME"] == nombre_pruebas
    tiempos, simulaciones = {}, []

    def medir(nombre, operacion):
        print(f"Inicio: {nombre}", flush=True)
        inicio = perf_counter()
        resultado = operacion()
        tiempos[nombre] = round(perf_counter() - inicio, 3)
        print(f"Fin: {nombre} ({tiempos[nombre]} s)", flush=True)
        return resultado

    with TemporaryDirectory() as archivos, override_settings(
        DEBUG=False, MEDIA_ROOT=archivos, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ), transaction.atomic():
        assert not Eleccion.objects.exclude(estado="finalizada").exists(), "La base de pruebas debe estar libre de elecciones abiertas."
        usuario = get_user_model().objects.create_superuser(username="verificacion-20000")
        hoy = timezone.localdate()
        eleccion = Eleccion.objects.create(nombre="Prueba aislada de 20000 filas", fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=10))
        claustro, _ = Claustro.objects.get_or_create(nombre="Estudiantes")
        configuracion = EleccionClaustro.objects.create(eleccion=eleccion, claustro=claustro, maximo_votantes_por_mesa=300, fecha_votacion=hoy)
        sede, _ = Sede.objects.get_or_create(nombre="Campus")
        EleccionSede.objects.create(eleccion=eleccion, sede=sede)
        EleccionClaustroSede.objects.create(eleccion_claustro=configuracion, sede=sede)
        for codigo, nombre in (
            ("K", "Ingeniería en Sistemas de Información"), ("I", "Ingeniería Industrial"),
            ("R", "Ingeniería Electrónica"), ("O", "Ingeniería Civil"), ("S", "Ingeniería Mecánica"),
        ):
            departamento, _ = Departamento.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre})
            alcance = EleccionClaustroDepartamento.objects.create(eleccion_claustro=configuracion, departamento=departamento)
            EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=sede)
        for nombre, inicio, fin in (("Mañana", 8, 13), ("Tarde", 13, 18), ("Noche", 18, 23)):
            turno, _ = Turno.objects.get_or_create(nombre=nombre, defaults={"hora_inicio": time(inicio), "hora_fin": time(fin)})
            EleccionClaustroTurno.objects.create(
                eleccion_claustro=configuracion, turno=turno, titulares_por_mesa=3, minimo_titulares_por_mesa=3,
            )
        ConfiguracionAutoridades.objects.create(eleccion_claustro=configuracion, modo="nomina")
        ruta = BASE / "padron_alumnos_20000_filas.csv"
        contenido = ruta.read_bytes()
        validacion = medir("validacion_padron", lambda: validar_csv_padron(contenido, configuracion, ruta.name))
        assert not validacion.errores, validacion.errores[:5]
        assert len(validacion.filas) == 20000 and validacion.cantidad_validas == 18500
        importacion = ImportacionPadron.objects.create(
            eleccion=eleccion, eleccion_claustro=configuracion, usuario=usuario,
            nombre_archivo=ruta.name, archivo=SimpleUploadedFile(ruta.name, contenido),
            huella_archivo=hashlib.sha256(contenido).hexdigest(),
        )
        creados = medir("confirmacion_padron", lambda: confirmar_importacion(importacion))
        assert creados == 18500
        assert RegistroPadron.objects.filter(eleccion=eleccion).count() == 20000
        assert RegistroPadron.objects.filter(eleccion=eleccion, es_principal=False).count() == 1500
        medir("calculo_mesas", lambda: calcular_mesas_automaticas_eleccion(eleccion))
        mesas = list(Mesa.objects.filter(eleccion=eleccion).annotate(cantidad=Count("asignaciones_padron")))
        assert len(mesas) == 70
        assert sum(mesa.es_especial for mesa in mesas) == 5
        assert Counter(mesa.cantidad for mesa in mesas) == {300: 60, 200: 10}
        archivo_nomina = BASE / "nomina_autoridades_630.csv"
        registros = medir("validacion_nomina", lambda: nomina.identificar_nomina(configuracion, archivo_nomina.read_bytes(), archivo_nomina.name))
        assert RegistroPadron.objects.filter(pk__in=registros).values("elector_id").distinct().count() == 630
        ejecutar = nomina._ejecutar_propuesta

        def simular(claustro_actual, actor, opciones):
            print(f"  Simulando: mesa={opciones['mesa']}, sede={opciones['sede']}, mesa_distinta={opciones.get('votar_mesa', False)}", flush=True)
            inicio = perf_counter()
            resultado = ejecutar(claustro_actual, actor, opciones)
            simulaciones.append({
                "reacomodar": opciones["mesa"], "cambio_sede": opciones["sede"],
                "mesa_distinta": opciones.get("votar_mesa", False), "segundos": round(perf_counter() - inicio, 3),
                "titulares": resultado[0]["titulares"], "faltantes": resultado[0]["titulares_faltantes"],
            })
            print(f"  Resultado: {simulaciones[-1]}", flush=True)
            return resultado

        datos = {"registros": registros, "mesa": False, "votar_mesa": False, "sede": False}
        with patch.object(nomina, "_ejecutar_propuesta", simular):
            propuesta = medir("previsualizacion_nomina_completa", lambda: nomina.previsualizar_nomina(configuracion, usuario, datos))
            assert propuesta["resumen"]["titulares"] == 630, propuesta["resumen"]
            assert propuesta["resumen"]["titulares_faltantes"] == 0, propuesta["resumen"]
            medir("confirmacion_nomina", lambda: nomina.confirmar_nomina(configuracion, usuario, propuesta, alternativa="mesa_actual"))
        asignaciones = list(AsignacionAutoridad.objects.filter(registro_padron__eleccion=eleccion).select_related(
            "registro_padron__elector", "mesa__eleccion_claustro_departamento__departamento", "turno",
        ).order_by("mesa__numero", "turno__hora_inicio", "registro_padron__elector__legajo"))
        assert len(asignaciones) == len({a.registro_padron.elector_id for a in asignaciones}) == 630
        cupos = Counter((a.mesa_id, a.turno_id) for a in asignaciones)
        assert len(cupos) == 210 and set(cupos.values()) == {3}
        with (BASE / "distribucion_nomina_verificada.csv").open("w", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(("Mesa", "Tipo", "Departamento", "Turno", "DNI", "Legajo"))
            for a in asignaciones:
                escritor.writerow((a.mesa.codigo, "Especial" if a.mesa.es_especial else "Principal", a.mesa.eleccion_claustro_departamento.departamento.codigo, a.turno.nombre, a.registro_padron.elector.dni, a.registro_padron.elector.legajo))
        resumen = {
            "estado": "verificado", "base_pruebas": nombre_pruebas, "personas": 18500,
            "registros": 20000, "registros_adicionales": 1500, "mesas": 70, "mesas_especiales": 5,
            "autoridades_distintas": 630, "cupos_por_mesa_y_turno": 3, "cupos_completos": 210,
            "tiempos_segundos": tiempos, "simulaciones": simulaciones,
            "entorno": "PostgreSQL aislado, DEBUG=False, servicios reales; sin carga en la base habitual",
        }
        (BASE / "validacion_aplicacion.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        transaction.set_rollback(True)
    print(json.dumps(resumen, ensure_ascii=True, indent=2), flush=True)
    print("Datos de prueba revertidos; archivos conservados. Base habitual intacta.", flush=True)


if __name__ == "__main__":
    main()
