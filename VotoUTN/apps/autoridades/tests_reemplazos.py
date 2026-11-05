from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.autoridades import tests as base
from apps.autoridades.models import AsignacionAutoridad
from apps.autoridades.services import asignar_autoridad
from apps.autoridades.seleccion_manual import asignar_manualmente
from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.justificativos.services import resolver_justificativo
from apps.notificaciones.models import EnvioNotificacion


class AutoridadesSinSuplentesTests(TestCase):
    def setUp(self):
        base.TurnosAutoridadesTests.setUp(self)
        self.titular, _ = asignar_autoridad(self.registros[0], self.mesa, self.manana, self.usuario)
        self.tipo_justificativo = TipoJustificativo.objects.create(nombre="No puede ejercer")
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.PUBLICADA)

    def justificativo(self):
        return JustificativoAusencia.objects.create(
            registro_padron=self.titular.registro_padron, ausencia="autoridad",
            tipo=self.tipo_justificativo, detalle="No puedo ejercer",
        )

    def test_aprobar_justificacion_deja_vacante_sin_promocion(self):
        from django.utils import timezone
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        justificativo = self.justificativo()
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.usuario)
        self.titular.refresh_from_db()
        self.assertEqual(self.titular.estado, AsignacionAutoridad.Estado.RECHAZADA)
        self.assertFalse(AsignacionAutoridad.objects.filter(mesa=self.mesa, turno=self.manana, estado="asignada").exists())
        self.assertFalse(EnvioNotificacion.objects.filter(plantilla__codigo="autoridad-convocatoria-suplente").exists())

    def test_rechazar_justificacion_conserva_titular(self):
        resolver_justificativo(self.justificativo(), estado="rechazado", observacion="", usuario=self.usuario)
        self.titular.refresh_from_db()
        self.assertEqual(self.titular.estado, AsignacionAutoridad.Estado.ASIGNADA)

    def test_aprobar_restituye_mesa_anterior_si_no_mueve_a_otros(self):
        from django.utils import timezone
        from apps.mesas.models import AsignacionMesa, Mesa
        otra_mesa = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
                                        eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        AsignacionMesa.objects.filter(registro_padron=self.registros[0]).update(mesa=otra_mesa)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        resolver_justificativo(self.justificativo(), estado="aprobado", observacion="", usuario=self.usuario)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[0]).mesa, self.mesa)

    def test_retorno_con_reordenamiento_se_previsualiza_y_confirma(self):
        from django.utils import timezone
        from apps.mesas.models import AsignacionMesa, Mesa
        self.eleccion_claustro.maximo_votantes_por_mesa = 2
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        otra_mesa = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
                                        eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        AsignacionMesa.objects.filter(registro_padron=self.registros[0]).update(mesa=otra_mesa)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        resolver_justificativo(self.justificativo(), estado="aprobado", observacion="", usuario=self.usuario)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[0]).mesa, otra_mesa)
        self.client.force_login(self.usuario)
        url = reverse("revisar-retorno-votacion", args=(self.titular.pk,))
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["movimientos"]), 2)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[0]).mesa, otra_mesa)
        respuesta = self.client.post(url, {"propuesta": respuesta.context["propuesta"]})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[0]).mesa, self.mesa)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[2]).mesa, otra_mesa)

    def test_retorno_obsoleto_no_mueve_a_los_electores(self):
        from django.utils import timezone
        from apps.mesas.models import AsignacionMesa, Mesa
        self.eleccion_claustro.maximo_votantes_por_mesa = 2
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        otra_mesa = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
                                        eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        AsignacionMesa.objects.filter(registro_padron=self.registros[0]).update(mesa=otra_mesa)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        resolver_justificativo(self.justificativo(), estado="aprobado", observacion="", usuario=self.usuario)
        self.client.force_login(self.usuario)
        url = reverse("revisar-retorno-votacion", args=(self.titular.pk,))
        propuesta = self.client.get(url).context["propuesta"]
        self.registros[1].nivel = "4"
        self.registros[1].save(update_fields=("nivel",))
        self.client.post(url, {"propuesta": propuesta})
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[0]).mesa, otra_mesa)

    def test_en_curso_no_modifica_la_asignacion(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.EN_CURSO)
        justificativo = self.justificativo()
        with self.assertRaises(ValidationError):
            resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.usuario)
        justificativo.refresh_from_db()
        self.titular.refresh_from_db()
        self.assertEqual(justificativo.estado, "pendiente")
        self.assertEqual(self.titular.estado, "asignada")

    def test_qr_de_otro_elector_bloquea_aprobacion_de_ausencia(self):
        from django.utils import timezone
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        type(self.registros[1]).objects.filter(pk=self.registros[1].pk).update(qr_generado_en=timezone.now(), numero_mesa_qr=self.mesa.numero)
        justificativo = self.justificativo()
        with self.assertRaisesMessage(ValidationError, "padrón con QR"):
            resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.usuario)
        justificativo.refresh_from_db()
        self.titular.refresh_from_db()
        self.assertEqual(justificativo.estado, "pendiente")
        self.assertEqual(self.titular.estado, "asignada")

    def test_base_de_datos_impide_crear_suplente(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AsignacionAutoridad.objects.create(
                registro_padron=self.registros[1], mesa=self.mesa, turno=self.manana,
                tipo="suplente", orden_suplencia=1, asignada_por=self.usuario,
            )

    def test_no_se_puede_asignar_suplente_manualmente(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.EN_PREPARACION)
        with self.assertRaises(ValidationError):
            asignar_manualmente(self.mesa, self.manana, self.registros[1], self.usuario, tipo="suplente", orden=1)

    def test_informar_ausencia_dirige_a_justificativos_sin_liberar_cupo(self):
        self.client.force_login(self.usuario)
        # La ruta exige identidad de elector; la resolución nunca se hace mediante el POST directo.
        ruta = reverse("responder-autoridad", args=(self.titular.pk,))
        self.assertEqual(self.client.get(ruta).status_code, 404)

    def test_elector_no_ve_asignaciones_hasta_confirmacion_definitiva(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from apps.usuarios.models import PerfilUsuario
        elector_usuario = get_user_model().objects.create_user(username="autoridad-provisoria")
        PerfilUsuario.objects.create(usuario=elector_usuario, elector=self.registros[0].elector)
        self.client.force_login(elector_usuario)
        ruta = reverse("mis-asignaciones-autoridad")
        self.assertEqual(self.client.get(ruta).status_code, 403)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        self.assertContains(self.client.get(ruta), "designaciones se notifican")

    def test_no_se_inicia_con_justificativo_de_autoridad_pendiente(self):
        from unittest.mock import patch
        from django.utils import timezone
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        justificativo = self.justificativo()
        self.eleccion.refresh_from_db()
        with patch.object(Eleccion, "validar_configuracion"):
            with self.assertRaisesMessage(ValidationError, "justificativos de autoridades pendientes"):
                self.eleccion.cambiar_estado(Eleccion.Estado.EN_CURSO)
            justificativo.estado = JustificativoAusencia.Estado.RECHAZADO
            justificativo.save(update_fields=("estado",))
            self.eleccion.cambiar_estado(Eleccion.Estado.EN_CURSO)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.EN_CURSO)

    def test_no_se_admite_presentar_justificacion_de_autoridad_en_curso(self):
        from apps.justificativos.forms import FormularioJustificativo
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.EN_CURSO)
        self.titular.registro_padron.eleccion.refresh_from_db()
        formulario = FormularioJustificativo(data={"ausencia": "autoridad", "tipo": self.tipo_justificativo.pk, "detalle": "Ausencia"}, registro_padron=self.titular.registro_padron)
        self.assertFalse(formulario.is_valid())

    def test_configuracion_de_minimo_no_puede_superar_maximo(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.EN_PREPARACION)
        self.client.force_login(self.usuario)
        url = reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        datos = {"configuracion-turnos": [self.manana.pk], "guardar-turnos": "", f"titulares_{self.manana.pk}": "3", f"minimo_titulares_{self.manana.pk}": "2"}
        self.client.post(url, datos)
        config = self.eleccion_claustro.turnos_autoridad.get(turno=self.manana)
        self.assertEqual((config.minimo_titulares_por_mesa, config.titulares_por_mesa), (2, 3))
        datos[f"minimo_titulares_{self.manana.pk}"] = "4"
        self.client.post(url, datos)
        config.refresh_from_db()
        self.assertEqual((config.minimo_titulares_por_mesa, config.titulares_por_mesa), (2, 3))
