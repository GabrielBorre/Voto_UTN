from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase
from django.urls import reverse

from apps.autoridades import tests as casos_base
from apps.autoridades.distribucion import distribuir
from apps.autoridades.models import AsignacionAutoridad, ConfiguracionAutoridades
from apps.elecciones.models import EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede
from apps.mesas.models import Mesa
from apps.parametros.models import Claustro, Departamento, Sede


class ElementosListado(HTMLParser):
    def __init__(self, contenido):
        super().__init__()
        self.detalles = []
        self.mesas = []
        self.siguiente = None
        self.feed(contenido)

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "tr" and "data-mesa" in atributos:
            self.mesas.append(atributos)
        if tag == "tr" and atributos.get("class") == "mesa-fila-detalle":
            self.detalles.append(atributos)
        if tag == "a" and atributos.get("rel") == "next":
            self.siguiente = atributos["href"]


class VistaMesasAutoridadesTests(TestCase):
    def setUp(self):
        casos_base.TurnosAutoridadesTests.setUp(self)
        ConfiguracionAutoridades.objects.create(eleccion_claustro=self.eleccion_claustro, modo="aleatorio")
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=2, suplentes_por_mesa=0)
        self.departamento = self.mesa.eleccion_claustro_departamento.departamento
        self.otro_departamento = Departamento.objects.create(nombre="Otro departamento", codigo="OD")
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro, departamento=self.otro_departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=self.sede_votacion)
        self.mesa_otro_departamento = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion, eleccion_claustro_departamento=alcance)
        self.otra_sede = Sede.objects.create(nombre="Otra sede del listado")
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento, sede=self.otra_sede)
        self.mesa_otra_sede = Mesa.objects.create(eleccion=self.eleccion, numero=3, sede=self.otra_sede, eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        distribuir(self.eleccion_claustro, self.usuario)
        self.ruta = reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        self.client.force_login(self.usuario)

    def mesas_mostradas(self, respuesta):
        return {m.pk for m in respuesta.context["pagina_mesas"]}

    def test_muestra_asignacion_provisoria_y_minimos_pendientes(self):
        self.eleccion_claustro.turnos_autoridad.update(minimo_titulares_por_mesa=2)
        respuesta = self.client.get(self.ruta)
        self.assertContains(respuesta, "Asignación provisoria")
        self.assertContains(respuesta, "Mínimo pendiente: 2")

    def test_listado_compacto_agrupa_por_mesa_y_abre_detalle_a_pedido(self):
        respuesta = self.client.get(self.ruta)
        elementos = ElementosListado(respuesta.content.decode())
        self.assertEqual({int(d["data-mesa"]) for d in elementos.mesas}, {self.mesa.pk, self.mesa_otro_departamento.pk, self.mesa_otra_sede.pk})
        self.assertEqual(len(elementos.detalles), 3)
        self.assertTrue(all("hidden" in d for d in elementos.detalles))
        self.assertContains(respuesta, '<table class="mesas-asignaciones-tabla">', html=False)
        for titulo in ("Mesa", "Departamento", "Sede", "Turno", "Titulares", "Autoridades"):
            self.assertContains(respuesta, f'<th scope="col">{titulo}</th>', html=True)
        self.assertContains(respuesta, "2 de 2")
        mesa = next(m for m in respuesta.context["pagina_mesas"] if m.pk == self.mesa.pk)
        self.assertEqual([a.tipo for a in mesa.autoridades_pagina], ["titular", "titular"])
        self.assertContains(respuesta, "Ver autoridades")
        for asignacion in mesa.autoridades_pagina:
            self.assertContains(respuesta, asignacion.registro_padron.elector.nombre_completo)

    def test_filtros_por_departamento_y_sede_se_combinan_sin_modificar_asignaciones(self):
        anteriores = list(AsignacionAutoridad.objects.order_by("pk").values())
        respuesta = self.client.get(self.ruta, {"departamento": self.departamento.pk})
        self.assertEqual(self.mesas_mostradas(respuesta), {self.mesa.pk, self.mesa_otra_sede.pk})
        respuesta = self.client.get(self.ruta, {"departamento": self.departamento.pk, "sede": self.sede_votacion.pk})
        self.assertEqual(self.mesas_mostradas(respuesta), {self.mesa.pk})
        self.assertEqual(respuesta.context["cantidad_autoridades_listado"], 2)
        self.assertEqual(list(AsignacionAutoridad.objects.order_by("pk").values()), anteriores)

    def test_filtrar_cobertura_completa_o_cupos_faltantes(self):
        respuesta = self.client.get(self.ruta, {"cobertura": "completa"})
        self.assertEqual(self.mesas_mostradas(respuesta), {self.mesa.pk})
        for cobertura in ("titulares",):
            with self.subTest(cobertura=cobertura):
                respuesta = self.client.get(self.ruta, {"cobertura": cobertura})
                self.assertEqual(self.mesas_mostradas(respuesta), {self.mesa_otro_departamento.pk, self.mesa_otra_sede.pk})
        respuesta = self.client.get(self.ruta, {"departamento": self.departamento.pk, "sede": self.sede_votacion.pk, "cobertura": "titulares"})
        self.assertContains(respuesta, "No hay mesas que coincidan con los filtros")
        self.assertEqual(respuesta.context["cantidad_autoridades_listado"], 0)

    def test_paginacion_de_25_mesas_conserva_filtros_y_posicion(self):
        for numero in range(10, 36):
            Mesa.objects.create(eleccion=self.eleccion, numero=numero, sede=self.sede_votacion, eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        filtros = {"departamento": self.departamento.pk, "sede": self.sede_votacion.pk}
        respuesta = self.client.get(self.ruta, filtros)
        self.assertEqual(len(respuesta.context["pagina_mesas"]), 25)
        self.assertEqual(respuesta.context["pagina_mesas"].paginator.count, 27)
        enlace = urlsplit(ElementosListado(respuesta.content.decode()).siguiente)
        parametros = parse_qs(enlace.query)
        self.assertEqual(parametros["departamento"], [str(self.departamento.pk)])
        self.assertEqual(parametros["sede"], [str(self.sede_votacion.pk)])
        self.assertEqual(parametros["pagina_mesas"], ["2"])
        self.assertEqual(enlace.fragment, "asignaciones")
        siguiente = self.client.get(self.ruta, {**filtros, "pagina_mesas": 2})
        self.assertEqual(len(siguiente.context["pagina_mesas"]), 2)
        self.assertFalse(self.mesas_mostradas(respuesta) & self.mesas_mostradas(siguiente))

    def test_filtros_invalidos_o_ajenos_al_claustro_no_amplian_el_listado(self):
        otro_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Claustro ajeno al listado"))
        ajeno = Departamento.objects.create(nombre="Departamento ajeno", codigo="DA")
        alcance = EleccionClaustroDepartamento.objects.create(eleccion_claustro=otro_claustro, departamento=ajeno)
        Mesa.objects.create(eleccion=self.eleccion, numero=4, sede=self.sede_votacion, eleccion_claustro_departamento=alcance)
        for datos in ({"departamento": ajeno.pk}, {"departamento": "no-numero"}, {"sede": 999999}, {"cobertura": "invalida"}):
            with self.subTest(datos=datos):
                respuesta = self.client.get(self.ruta, datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["formulario_filtros"].errors)
                self.assertFalse(self.mesas_mostradas(respuesta))
                self.assertNotIn(ajeno, respuesta.context["formulario_filtros"].fields["departamento"].queryset)

    def test_detalle_no_ofrece_promover_suplentes(self):
        asignacion = AsignacionAutoridad.objects.filter(tipo="titular").first()
        asignacion.estado = "rechazada"
        asignacion.save()
        respuesta = self.client.get(self.ruta)
        self.assertNotContains(respuesta, reverse("confirmar-reemplazo-autoridad", args=(asignacion.pk,)))
        self.assertNotContains(respuesta, "Confirmar reemplazo")
