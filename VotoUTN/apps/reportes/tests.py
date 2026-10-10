import re
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware
from reportlab.lib.styles import getSampleStyleSheet

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionClaustroTurno,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    ListaCandidatos,
    OrganoElectivo,
    ParticipacionPartido,
    PuestoEleccion,
)
from apps.reportes.services import valor_csv
from apps.reportes.services_boletas_pdf import (
    MARGEN_SUPERIOR_CONTENIDO,
    POSICION_LINEA_ENCABEZADO,
    _construir_contenido_boleta,
    _obtener_boletas,
    generar_boletas_pdf,
    validar_boletas_pdf,
)
from apps.reportes.services_pdf import (
    ELECTORES_POR_PAGINA,
    _agrupar_padrones_por_mesa,
    _construir_tabla,
    _construir_troquel,
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
        self.assertContains(respuesta, 'class="toolbar reports-grid"')
        self.assertContains(respuesta, 'class="option report-option"', count=4)
        self.assertContains(respuesta, 'class="report-actions"', count=4)
        self.assertContains(respuesta, "Padrón imprimible no disponible")
        self.assertContains(respuesta, "Boletas no disponibles")
        self.assertContains(respuesta, "Generar padrón imprimible")
        self.assertContains(respuesta, "disabled")
        self.assertContains(
            respuesta,
            '<a class="active" href="/gestion/elecciones/">Gestionar elecciones</a>',
        )
        self.assertContains(respuesta, reverse("configurar-eleccion", args=(self.eleccion.id,)))
        self.assertContains(respuesta, "Volver a configuración", count=1)

    def test_exportar_reporte_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("exportar-reporte", args=(self.eleccion.id, "padron")))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="padron_', respuesta["Content-Disposition"])

    def test_generar_boletas_pdf_sin_candidatos_redirige_con_mensaje(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("generar-boletas-pdf", args=(self.eleccion.id,)),
            follow=True,
        )

        self.assertRedirects(
            respuesta,
            reverse("gestionar-reportes", args=(self.eleccion.id,)),
        )
        mensajes = [str(mensaje) for mensaje in respuesta.context["messages"]]
        self.assertTrue(any("no tiene listas activas con candidatos" in mensaje for mensaje in mensajes))


class PadronPDFTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion Oficio", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8))
        self.sede = Sede.objects.create(nombre="Campus Central")
        self.turno = Turno.objects.create(nombre="Manana", hora_inicio=time(8), hora_fin=time(12))
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro)
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.turno)
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=self.eleccion_claustro, departamento=self.departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
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

    def test_columna_apellido_y_nombre_usa_apellido_primero(self):
        registro = self.crear_electores(1)[0]
        registro.elector.apellido = "Gomez"
        registro.elector.nombre = "Maria Elena"

        with (
            patch("apps.reportes.services_pdf._construir_espacio_firma", return_value="firma"),
            patch("apps.reportes.services_pdf._construir_troquel", return_value="troquel"),
        ):
            tabla = _construir_tabla(self.eleccion, self.mesa, [registro], 1, 20)

        self.assertEqual(tabla._cellvalues[1][2].text, "Gomez, Maria Elena")

    def test_troquel_usa_apellido_y_nombre(self):
        registro = self.crear_electores(1)[0]
        registro.elector.apellido = "Gomez"
        registro.elector.nombre = "Maria Elena"

        with (
            patch("apps.reportes.services_pdf._generar_imagen_qr", return_value=b"qr"),
            patch("apps.reportes.services_pdf.ImagenPDF", return_value="qr-image"),
            patch("apps.reportes.services_pdf._construir_espacio_firma", return_value="firma"),
        ):
            troquel = _construir_troquel(self.eleccion, self.mesa, registro, 20)

        texto_troquel = troquel._cellvalues[0][1]
        self.assertEqual(texto_troquel._cellvalues[0][0].text, "Gomez, Maria Elena")

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


class BoletasPDFTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Elección de boletas",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        self.claustro = Claustro.objects.create(nombre="Estudiantes boletas")
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=self.claustro,
        )
        self.departamento = Departamento.objects.create(
            nombre="Sistemas boletas",
            codigo="SB",
        )
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=self.departamento,
        )
        self.organo = OrganoElectivo.objects.create(nombre="Consejo de boletas")
        self.cargo = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Consejero/a",
            permite_filtrar_departamentos=True,
        )
        self.puesto = PuestoEleccion.objects.create(
            puesto=self.cargo,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            cantidad_titulares=2,
            cantidad_suplentes=1,
        )
        self.usuario = get_user_model().objects.create_user(username="admin-boletas")
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )

    def crear_presentacion(self, *, codigo, numero, nombre, elector, activa=True):
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            codigo_presentacion=codigo,
            eleccion_claustro=self.eleccion_claustro,
            numero_lista=numero,
            nombre_lista=nombre,
        )
        lista = ListaCandidatos.objects.create(
            participacion=participacion,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            nombre="Consejo Departamental",
            puesto_eleccion=self.puesto,
            activa=activa,
        )
        Candidato.objects.create(
            lista=lista,
            elector=elector,
            cargo=self.cargo.nombre,
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
            activo=True,
        )
        return participacion

    def crear_elector(self, indice, nombre):
        elector = Elector.objects.create(
            legajo=f"B{indice:05d}",
            nombre=nombre,
            apellido="Candidata",
            dni=f"4{indice:07d}",
        )
        RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
        )
        return elector

    def test_validacion_indica_cuando_no_hay_candidaturas_activas(self):
        validacion = validar_boletas_pdf(self.eleccion)

        self.assertFalse(validacion.apto)
        self.assertEqual(validacion.cantidad_boletas, 0)
        self.assertTrue(validacion.motivos)

    def test_titulo_comienza_debajo_de_la_linea_del_encabezado(self):
        self.assertGreater(
            MARGEN_SUPERIOR_CONTENIDO,
            POSICION_LINEA_ENCABEZADO,
        )

    def test_genera_una_boleta_por_presentacion_y_alcance(self):
        self.crear_presentacion(
            codigo="A",
            numero="10",
            nombre="Lista Azul",
            elector=self.crear_elector(1, "Ana"),
        )
        self.crear_presentacion(
            codigo="B",
            numero="20",
            nombre="Lista Verde",
            elector=self.crear_elector(2, "Bruno"),
        )

        validacion = validar_boletas_pdf(self.eleccion)
        contenido = generar_boletas_pdf(self.eleccion)

        self.assertTrue(validacion.apto)
        self.assertEqual(validacion.cantidad_boletas, 2)
        self.assertTrue(contenido.startswith(b"%PDF"))
        self.assertEqual(contar_paginas_pdf(contenido), 2)

    def test_boleta_imprime_departamento_configurado_en_el_puesto(self):
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            codigo_presentacion="DEPARTAMENTO",
            eleccion_claustro=self.eleccion_claustro,
            numero_lista="30",
            nombre_lista="Lista Departamental",
        )
        lista = ListaCandidatos.objects.create(
            participacion=participacion,
            eleccion_claustro=self.eleccion_claustro,
            nombre="Consejo Departamental",
            puesto_eleccion=self.puesto,
        )
        Candidato.objects.create(
            lista=lista,
            elector=self.crear_elector(3, "Carla"),
            cargo=self.cargo.nombre,
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        boleta = _obtener_boletas(self.eleccion)[0]
        contenido = _construir_contenido_boleta(
            boleta,
            {
                "boleta_titulo": getSampleStyleSheet()["Title"],
                "presentacion": getSampleStyleSheet()["Normal"],
                "puesto": getSampleStyleSheet()["Heading2"],
                "candidato": getSampleStyleSheet()["Normal"],
            },
            500,
        )

        self.assertEqual(str(boleta["departamento"]), "Sistemas boletas")
        self.assertIn(
            "Departamento: Sistemas boletas",
            contenido[2]._cellvalues[0][0].text,
        )

    def test_vista_genera_pdf_descargable_con_permiso_de_eleccion(self):
        self.crear_presentacion(
            codigo="A",
            numero="10",
            nombre="Lista Azul",
            elector=self.crear_elector(1, "Ana"),
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("generar-boletas-pdf", args=(self.eleccion.id,)),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn('filename="boletas_', respuesta["Content-Disposition"])
        self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_vista_bloquea_generacion_sin_permiso_sobre_la_eleccion(self):
        self.crear_presentacion(
            codigo="A",
            numero="10",
            nombre="Lista Azul",
            elector=self.crear_elector(1, "Ana"),
        )
        usuario = get_user_model().objects.create_user(username="sin-permiso-boletas")
        self.client.force_login(usuario)

        respuesta = self.client.get(
            reverse("generar-boletas-pdf", args=(self.eleccion.id,)),
        )

        self.assertEqual(respuesta.status_code, 403)
