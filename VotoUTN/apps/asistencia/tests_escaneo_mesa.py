from datetime import date

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede
from apps.usuarios.models import AsignacionRol

CLAVE_QR = "clave-de-prueba-qr"


@override_settings(CLAVE_FIRMA_QR=CLAVE_QR)
class QrDeMesaTests(SimpleTestCase):
    def test_codigo_de_mesa_se_valida_y_devuelve_eleccion_y_mesa(self):
        codigo = ServicioRegistroParticipacion.generar_codigo_qr_mesa(eleccion_id=7, mesa_numero=12)

        self.assertTrue(codigo.startswith("M1."))
        self.assertEqual(ServicioRegistroParticipacion.parsear_codigo_qr_mesa(codigo), (7, 12))

    def test_rechaza_firma_alterada_y_otra_clave(self):
        codigo = ServicioRegistroParticipacion.generar_codigo_qr_mesa(eleccion_id=7, mesa_numero=12)

        self.assertIsNone(ServicioRegistroParticipacion.parsear_codigo_qr_mesa(f"{codigo[:-1]}{'Z' if codigo[-1] != 'Z' else 'Y'}"))
        with override_settings(CLAVE_FIRMA_QR="otra-clave"):
            self.assertIsNone(ServicioRegistroParticipacion.parsear_codigo_qr_mesa(codigo))

    def test_qr_de_elector_y_qr_de_mesa_no_se_confunden(self):
        elector = ServicioRegistroParticipacion.generar_codigo_qr(eleccion_id=7, mesa_numero=12, identificador_qr="A1B2C3D4")
        mesa = ServicioRegistroParticipacion.generar_codigo_qr_mesa(eleccion_id=7, mesa_numero=12)

        self.assertIsNone(ServicioRegistroParticipacion.parsear_codigo_qr_mesa(elector))
        self.assertIsNone(ServicioRegistroParticipacion.parsear_codigo_qr(mesa))


@override_settings(CLAVE_FIRMA_QR=CLAVE_QR)
class EscaneoDeMesaTests(TestCase):
    def setUp(self):
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=date(2026, 8, 3), fecha_fin=date(2026, 8, 3))
        Eleccion.objects.filter(pk=self.eleccion.pk).update(habilitada=True)
        self.eleccion.refresh_from_db()
        sede = Sede.objects.create(nombre="Sede A")
        claustro = Claustro.objects.create(nombre="Estudiantes")
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="ISI")
        eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=eleccion_claustro, departamento=departamento)
        self.mesa = Mesa.objects.create(eleccion=self.eleccion, numero=1, eleccion_claustro_departamento=self.configuracion, sede=sede)
        self.otra_mesa = Mesa.objects.create(eleccion=self.eleccion, numero=2, eleccion_claustro_departamento=self.configuracion, sede=sede)
        self.padron = self.crear_padron(1, self.mesa, sede)
        self.padron_otra_mesa = self.crear_padron(2, self.otra_mesa, sede)

        self.usuario = get_user_model().objects.create_user(username="administrativo", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=self.eleccion)
        self.client.force_login(self.usuario)

    def crear_padron(self, indice, mesa, sede):
        elector = Elector.objects.create(legajo=f"L{indice}", nombre=f"Elector {indice}", dni=f"4000000{indice}")
        padron = RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion, eleccion_claustro_departamento=self.configuracion, sede=sede, activo=True
        )
        AsignacionMesa.objects.create(registro_padron=padron, mesa=mesa)
        return padron

    def qr_elector(self, padron, mesa):
        return ServicioRegistroParticipacion.generar_codigo_qr(
            eleccion_id=self.eleccion.id, mesa_numero=mesa.numero, identificador_qr=padron.identificador_qr
        )

    def qr_mesa(self, mesa):
        return ServicioRegistroParticipacion.generar_codigo_qr_mesa(eleccion_id=self.eleccion.id, mesa_numero=mesa.numero)

    def post_mesa(self, cuerpo):
        return self.client.post(reverse("api-asistencia-mesa", args=(self.eleccion.pk,)), cuerpo, content_type="application/json")

    def post_lote(self, codigos, mesa_codigo):
        return self.client.post(
            reverse("api-asistencia-lote", args=(self.eleccion.pk,)),
            {"codigos_qr": codigos, "mesa_codigo": mesa_codigo},
            content_type="application/json",
        )

    def estado(self, mesa):
        mesa.refresh_from_db()
        return mesa.estado_escaneo

    def test_el_codigo_de_mesa_combina_departamento_y_numero(self):
        self.assertEqual(self.mesa.codigo, "ISI-001")
        self.assertEqual(Mesa(eleccion=self.eleccion, numero=5).codigo, "005")

    def test_una_mesa_nueva_esta_pendiente(self):
        self.assertEqual(self.estado(self.mesa), Mesa.EstadoEscaneo.PENDIENTE)

    def test_consultar_por_qr_o_codigo_manual_no_cambia_el_estado(self):
        por_qr = self.post_mesa({"accion": "consultar", "codigo_qr": self.qr_mesa(self.mesa)})
        manual = self.post_mesa({"accion": "consultar", "codigo_mesa": "isi-1"})

        self.assertEqual(por_qr.status_code, 200)
        self.assertEqual(por_qr.json()["mesa"]["codigo"], "ISI-001")
        self.assertEqual(manual.json()["mesa"]["estado"], "pendiente")
        self.assertEqual(self.estado(self.mesa), Mesa.EstadoEscaneo.PENDIENTE)

    def test_rechaza_codigos_de_mesa_invalidos(self):
        self.assertEqual(self.post_mesa({"accion": "consultar", "codigo_mesa": "ISI-99"}).status_code, 404)
        self.assertEqual(self.post_mesa({"accion": "consultar", "codigo_mesa": "XXX-1"}).status_code, 404)
        self.assertEqual(self.post_mesa({"accion": "consultar", "codigo_mesa": "ISI"}).status_code, 400)
        self.assertEqual(self.post_mesa({"accion": "consultar", "codigo_qr": self.qr_elector(self.padron, self.mesa)}).status_code, 400)

    def test_no_se_registran_electores_antes_de_iniciar_la_mesa(self):
        respuesta = self.post_lote([self.qr_elector(self.padron, self.mesa)], "ISI-1")

        self.assertEqual(respuesta.status_code, 409)
        self.assertFalse(RegistroParticipacion.objects.exists())

    def test_iniciar_pasa_a_en_proceso_y_permite_registrar_electores(self):
        self.post_mesa({"accion": "iniciar", "codigo_qr": self.qr_mesa(self.mesa)})
        respuesta = self.post_lote([self.qr_elector(self.padron, self.mesa)], "ISI-1")

        self.assertEqual(self.estado(self.mesa), Mesa.EstadoEscaneo.EN_PROCESO)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["creados"], [self.padron.identificador_qr])

    def test_qr_de_elector_de_otra_mesa_se_rechaza(self):
        self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"})

        respuesta = self.post_lote([self.qr_elector(self.padron_otra_mesa, self.otra_mesa)], "ISI-1")

        self.assertEqual(respuesta.json()["invalidos_otra_mesa"], [self.qr_elector(self.padron_otra_mesa, self.otra_mesa)])
        self.assertEqual(respuesta.json()["creados"], [])
        self.assertFalse(RegistroParticipacion.objects.exists())

    def test_qr_de_otra_mesa_con_numero_adulterado_se_rechaza_en_el_servidor(self):
        # El QR dice mesa 1 pero el elector pertenece a la mesa 2: la firma lo detecta o la asignacion no coincide.
        self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"})

        respuesta = self.post_lote([self.qr_elector(self.padron_otra_mesa, self.mesa)], "ISI-1")

        self.assertEqual(respuesta.json()["creados"], [])
        self.assertFalse(RegistroParticipacion.objects.exists())

    def test_finalizar_requiere_escaneo_en_proceso(self):
        respuesta = self.post_mesa({"accion": "finalizar", "codigo_mesa": "ISI-1"})

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(self.estado(self.mesa), Mesa.EstadoEscaneo.PENDIENTE)

    def test_finalizar_con_registros_deja_la_mesa_procesada(self):
        self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"})
        self.post_lote([self.qr_elector(self.padron, self.mesa)], "ISI-1")

        respuesta = self.post_mesa({"accion": "finalizar", "codigo_mesa": "ISI-1"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.estado(self.mesa), Mesa.EstadoEscaneo.PROCESADA)
        self.assertIsNotNone(Mesa.objects.get(pk=self.mesa.pk).procesada_en)

    def test_finalizar_sin_registros_exige_confirmar_que_no_hubo_inasistencias(self):
        self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"})

        sin_confirmar = self.post_mesa({"accion": "finalizar", "codigo_mesa": "ISI-1"})
        confirmada = self.post_mesa({"accion": "finalizar", "codigo_mesa": "ISI-1", "confirmar_sin_inasistencias": True})

        self.assertEqual(sin_confirmar.status_code, 422)
        self.assertEqual(confirmada.status_code, 200)
        self.assertEqual(self.estado(self.mesa), Mesa.EstadoEscaneo.PROCESADA)

    def test_una_mesa_procesada_no_puede_volver_a_iniciarse_ni_recibir_lotes(self):
        self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"})
        self.post_mesa({"accion": "finalizar", "codigo_mesa": "ISI-1", "confirmar_sin_inasistencias": True})

        self.assertEqual(self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"}).status_code, 409)
        self.assertEqual(self.post_lote([self.qr_elector(self.padron, self.mesa)], "ISI-1").status_code, 409)

    def test_reiniciar_una_mesa_en_proceso_la_retoma(self):
        self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"})

        respuesta = self.post_mesa({"accion": "iniciar", "codigo_qr": self.qr_mesa(self.mesa)})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.estado(self.mesa), Mesa.EstadoEscaneo.EN_PROCESO)

    def test_mesas_en_proceso_distintas_no_se_bloquean_entre_si_en_el_servidor(self):
        # El bloqueo intermesa vive en el escaner (una mesa a la vez por sesion), no en el estado global.
        self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"})

        respuesta = self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-2"})

        self.assertEqual(respuesta.status_code, 200)

    def test_usuario_sin_alcance_sobre_la_mesa_no_puede_operarla(self):
        limitado = get_user_model().objects.create_user(username="limitado", password="clave")
        otra_sede = Sede.objects.create(nombre="Sede B")
        AsignacionRol.objects.create(
            usuario=limitado, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion, sede=otra_sede
        )
        self.client.force_login(limitado)

        respuesta = self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"})

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.estado(self.mesa), Mesa.EstadoEscaneo.PENDIENTE)

    def test_autoridad_de_mesa_no_puede_operar_el_escaneo(self):
        autoridad = get_user_model().objects.create_user(username="autoridad", password="clave")
        AsignacionRol.objects.create(usuario=autoridad, rol=AsignacionRol.Rol.AUTORIDAD_MESA, eleccion=self.eleccion)
        self.client.force_login(autoridad)

        self.assertEqual(self.post_mesa({"accion": "iniciar", "codigo_mesa": "ISI-1"}).status_code, 403)

    def test_carga_manual_usa_el_codigo_de_mesa(self):
        url = reverse("api-asistencia-lote", args=(self.eleccion.pk,))
        dni = self.padron.elector.dni

        correcta = self.client.post(url, {"mesa_codigo": "ISI-001", "dni": dni}, content_type="application/json")
        inexistente = self.client.post(url, {"mesa_codigo": "ISI-099", "dni": dni}, content_type="application/json")
        sin_codigo = self.client.post(url, {"mesa_numero": 1, "dni": dni}, content_type="application/json")

        self.assertEqual(correcta.json()["creados"], [self.padron.identificador_qr])
        self.assertEqual(inexistente.status_code, 404)
        self.assertEqual(sin_codigo.status_code, 400)

    def test_la_vista_del_escaner_expone_la_api_de_mesa_y_el_ingreso_manual_de_codigo(self):
        self.eleccion.estado = Eleccion.Estado.ABIERTA
        self.eleccion.save(update_fields=("estado",))
        respuesta = self.client.get(reverse("escanear", args=(self.eleccion.pk,)))

        self.assertContains(respuesta, 'id="mesa-code-form"')
        self.assertContains(respuesta, 'data-mesa-api-url="')
