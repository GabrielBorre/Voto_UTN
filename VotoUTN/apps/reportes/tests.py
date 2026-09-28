import re
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionTurno,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.reportes.services import valor_csv
from apps.reportes.services_pdf import (
    ELECTORES_POR_PAGINA,
    _agrupar_padrones_por_mesa,
    generar_padron_pdf,
    validar_padron_para_pdf,
)
from apps.usuarios.models import AsignacionRol


def contar_paginas_pdf(contenido: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", contenido))


class ReportesCSVTests(TestCase):
    def test_valor_csv_sanitiza_formulas(self):
        self.assertEqual(valor_csv("=1+1"), "'=1+1")
        self.assertEqual(valor_csv("+SUM(A1:A2)"), "'+SUM(A1:A2)")
        self.assertEqual(valor_csv("-10"), "'-10")
        self.assertEqual(valor_csv("@cmd"), "'@cmd")
        self.assertEqual(valor_csv("Ana Perez"), "Ana Perez")
        self.assertEqual(valor_csv(None), "")


class ReportesViewsTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            habilitada=False,
        )
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )

    def test_gestionar_reportes_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-reportes", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "reportes/gestion.html")

    def test_exportar_reporte_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("exportar-reporte", args=(self.eleccion.id, "padron")))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="padron_', respuesta["Content-Disposition"])


class PadronPDFTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion Oficio", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8))
        self.sede = Sede.objects.create(nombre="Campus Central")
        self.turno = Turno.objects.create(nombre="Manana", hora_inicio=time(8), hora_fin=time(12))
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        EleccionTurno.objects.create(eleccion=self.eleccion, turno=self.turno)
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro)
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=self.eleccion_claustro, departamento=self.departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            turno=self.turno,
        )
        self.usuario = get_user_model().objects.create_user(username="admin-reportes", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion)

    def crear_electores(self, cantidad, mesa="usar_default", sede="usar_default", numero_inicial=1):
        mesa_asignada = self.mesa if mesa == "usar_default" else mesa
        sede_asignada = self.sede if sede == "usar_default" else sede
        registros = []
        for indice in range(numero_inicial, numero_inicial + cantidad):
            elector = Elector.objects.create(
                legajo=f"E{indice:05d}",
                nombre=f"Elector {indice:03d}",
                dni=f"3{indice:07d}",
            )
            registro = RegistroPadron.objects.create(
                elector=elector,
                eleccion=self.eleccion,
                eleccion_claustro_departamento=self.configuracion,
                sede=sede_asignada,
            )
            if mesa_asignada is not None:
                AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa_asignada)
            registros.append(registro)
        return registros

    def test_genera_pdf_con_menos_de_15_electores(self):
        self.crear_electores(5)

        contenido = generar_padron_pdf(self.eleccion)

        self.assertTrue(contenido.startswith(b"%PDF"))
        self.assertEqual(contar_paginas_pdf(contenido), 1)

    def test_genera_pdf_con_exactamente_15_electores(self):
        self.crear_electores(ELECTORES_POR_PAGINA)

        contenido = generar_padron_pdf(self.eleccion)

        self.assertEqual(contar_paginas_pdf(contenido), 1)

    def test_genera_pdf_con_mas_de_15_electores_crea_multiples_paginas(self):
        self.crear_electores(ELECTORES_POR_PAGINA + 1)

        contenido = generar_padron_pdf(self.eleccion)

        self.assertEqual(contar_paginas_pdf(contenido), 2)

    def test_ultima_pagina_contiene_el_resto_de_electores(self):
        self.crear_electores(ELECTORES_POR_PAGINA + 2)

        grupos = _agrupar_padrones_por_mesa(self.eleccion)
        electores_mesa = grupos[0]["padrones"]
        lotes = [
            electores_mesa[inicio: inicio + ELECTORES_POR_PAGINA]
            for inicio in range(0, len(electores_mesa), ELECTORES_POR_PAGINA)
        ]

        self.assertEqual([len(lote) for lote in lotes], [ELECTORES_POR_PAGINA, 2])

    def test_bloquea_generacion_sin_mesa_asignada(self):
        self.crear_electores(3)
        self.crear_electores(1, mesa=None, numero_inicial=100)

        validacion = validar_padron_para_pdf(self.eleccion)

        self.assertFalse(validacion.apto)
        self.assertTrue(any("mesa" in motivo for motivo in validacion.motivos))
        with self.assertRaises(ValueError):
            generar_padron_pdf(self.eleccion)

    def test_bloquea_generacion_sin_sede_asignada(self):
        self.crear_electores(3)
        self.crear_electores(1, sede=None, numero_inicial=200)

        validacion = validar_padron_para_pdf(self.eleccion)

        self.assertFalse(validacion.apto)
        self.assertTrue(any("sede" in motivo for motivo in validacion.motivos))
        with self.assertRaises(ValueError):
            generar_padron_pdf(self.eleccion)

    def test_vista_genera_pdf_descargable(self):
        self.crear_electores(3)
        self.client.login(username="admin-reportes", password="clave")

        respuesta = self.client.get(reverse("generar-padron-pdf", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn('filename="padron_', respuesta["Content-Disposition"])

    def test_vista_bloquea_y_redirige_cuando_falta_informacion(self):
        self.crear_electores(1, mesa=None)
        self.client.login(username="admin-reportes", password="clave")

        respuesta = self.client.get(reverse("generar-padron-pdf", args=(self.eleccion.id,)), follow=True)

        self.assertRedirects(respuesta, reverse("gestionar-reportes", args=(self.eleccion.id,)))
        mensajes = [str(mensaje) for mensaje in respuesta.context["messages"]]
        self.assertTrue(any("mesa" in mensaje for mensaje in mensajes))
