from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede
from apps.usuarios.models import AsignacionRol


@override_settings(CLAVE_FIRMA_QR="clave-de-prueba-qr")
class ProcesamientoManualDeMesaTests(TestCase):
    def setUp(self):
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=date(2026, 8, 3), fecha_fin=date(2026, 8, 3))
        Eleccion.objects.filter(pk=self.eleccion.pk).update(habilitada=True, estado=Eleccion.Estado.EN_CURSO)
        self.eleccion.refresh_from_db()
        sede = Sede.objects.create(nombre="Sede A")
        claustro = Claustro.objects.create(nombre="Estudiantes")
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="ISI")
        eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=eleccion_claustro, departamento=departamento)
        self.mesa = Mesa.objects.create(eleccion=self.eleccion, numero=1, eleccion_claustro_departamento=self.configuracion, sede=sede)
        self.padron = self._crear_padron(1, sede)
        self._crear_padron(2, sede)

        self.usuario = get_user_model().objects.create_user(username="administrativo", password="x")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=self.eleccion)
        self.client.force_login(self.usuario)

    def _crear_padron(self, indice, sede):
        elector = Elector.objects.create(legajo=f"L{indice}", nombre=f"Elector {indice}", dni=f"4000000{indice}")
        padron = RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion, eleccion_claustro_departamento=self.configuracion, sede=sede, activo=True
        )
        AsignacionMesa.objects.create(registro_padron=padron, mesa=self.mesa)
        return padron

    def _url_procesar(self, mesa=None):
        return reverse("procesar-mesa-manual", args=(self.eleccion.pk, (mesa or self.mesa).pk))

    def _estado(self):
        self.mesa.refresh_from_db()
        return self.mesa.estado_escaneo

    def test_carga_manual_de_inasistencia_pasa_la_mesa_a_en_proceso(self):
        resultado = ServicioRegistroParticipacion.registrar_manual(
            eleccion=self.eleccion, mesa_numero=self.mesa.numero, dni=self.padron.elector.dni, usuario=self.usuario
        )

        self.assertEqual(resultado.creados, [self.padron.identificador_qr])
        self.assertEqual(self._estado(), Mesa.EstadoEscaneo.EN_PROCESO)

    def test_carga_manual_rechazada_no_cambia_el_estado(self):
        ServicioRegistroParticipacion.registrar_manual(
            eleccion=self.eleccion, mesa_numero=self.mesa.numero, dni="99999999", usuario=self.usuario
        )

        self.assertEqual(self._estado(), Mesa.EstadoEscaneo.PENDIENTE)

    def test_carga_manual_rechaza_elector_de_otra_mesa(self):
        otra_mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=2,
            eleccion_claustro_departamento=self.configuracion, sede=self.mesa.sede,
        )
        resultado = ServicioRegistroParticipacion.registrar_manual(
            eleccion=self.eleccion, mesa_numero=otra_mesa.numero,
            dni=self.padron.elector.dni, usuario=self.usuario,
        )

        self.assertTrue(resultado.invalidos)
        self.assertFalse(RegistroParticipacion.objects.exists())
        otra_mesa.refresh_from_db()
        self.assertEqual(otra_mesa.estado_escaneo, Mesa.EstadoEscaneo.PENDIENTE)

    def test_carga_manual_desde_api_pasa_la_mesa_a_en_proceso(self):
        respuesta = self.client.post(
            reverse("api-asistencia-lote", args=(self.eleccion.pk,)),
            {"dni": self.padron.elector.dni, "mesa_codigo": "ISI-1"},
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self._estado(), Mesa.EstadoEscaneo.EN_PROCESO)

    def test_registrar_mesa_pendiente_sin_inasistencias_la_procesa(self):
        respuesta = self.client.post(self._url_procesar(), {"filtros": "escaneo=pendiente&pagina=2&otro=x"})

        self.assertEqual(self._estado(), Mesa.EstadoEscaneo.PROCESADA)
        self.assertIsNotNone(self.mesa.procesada_en)
        self.assertRedirects(
            respuesta,
            f"{reverse('lista-elecciones')}?eleccion={self.eleccion.pk}&escaneo=pendiente&pagina=2#mesas-pendientes",
            fetch_redirect_response=False,
        )

    def test_registrar_mesa_en_proceso_conserva_las_inasistencias(self):
        ServicioRegistroParticipacion.registrar_manual(
            eleccion=self.eleccion, mesa_numero=self.mesa.numero, dni=self.padron.elector.dni, usuario=self.usuario
        )

        self.client.post(self._url_procesar())

        self.assertEqual(self._estado(), Mesa.EstadoEscaneo.PROCESADA)
        self.assertEqual(RegistroParticipacion.objects.filter(mesa=self.mesa).count(), 1)

    def test_no_se_registra_dos_veces_una_mesa_procesada(self):
        self.client.post(self._url_procesar())
        procesada_en = Mesa.objects.get(pk=self.mesa.pk).procesada_en

        self.client.post(self._url_procesar())

        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.procesada_en, procesada_en)

    def test_requiere_post(self):
        self.assertEqual(self.client.get(self._url_procesar()).status_code, 404)
        self.assertEqual(self._estado(), Mesa.EstadoEscaneo.PENDIENTE)

    def test_usuario_sin_permiso_no_puede_registrar_la_mesa(self):
        elector = get_user_model().objects.create_user(username="sin-rol", password="x")
        self.client.force_login(elector)

        respuesta = self.client.post(self._url_procesar())

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self._estado(), Mesa.EstadoEscaneo.PENDIENTE)

    def test_no_se_registra_fuera_de_una_eleccion_en_curso(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.FINALIZADA)

        self.assertEqual(self.client.post(self._url_procesar()).status_code, 404)
        self.assertEqual(self._estado(), Mesa.EstadoEscaneo.PENDIENTE)

    def test_tablero_muestra_boton_registrar_con_cantidades(self):
        ServicioRegistroParticipacion.registrar_manual(
            eleccion=self.eleccion, mesa_numero=self.mesa.numero, dni=self.padron.elector.dni, usuario=self.usuario
        )

        respuesta = self.client.get(reverse("lista-elecciones"), {"eleccion": self.eleccion.pk})

        self.assertContains(respuesta, "dialogo-registrar-mesa")
        self.assertContains(respuesta, f'data-accion="{self._url_procesar()}"')
        self.assertContains(respuesta, 'data-electores="2"')
        self.assertContains(respuesta, 'data-inasistencias="1"')
        self.assertContains(respuesta, ">Registrar</button>")

    def test_tablero_no_muestra_boton_para_mesa_procesada(self):
        self.client.post(self._url_procesar())

        respuesta = self.client.get(reverse("lista-elecciones"), {"eleccion": self.eleccion.pk})

        self.assertNotContains(respuesta, ">Registrar</button>")
        self.assertContains(respuesta, "Registrada")
