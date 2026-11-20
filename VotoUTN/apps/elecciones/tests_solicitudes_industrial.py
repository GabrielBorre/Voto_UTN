from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.demo_generadores import generar_solicitudes_demo
from apps.elecciones.models import EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede
from apps.elecciones import tests_solicitudes_publicacion as casos_publicacion
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import AsignacionSedePadron, Elector, RegistroPadron, SolicitudCambioSede
from apps.padron.services import estimar_impacto_mesas_por_sede, resolver_solicitud_cambio_sede
from apps.parametros.models import Departamento


@override_settings(INSTANCIA_DEMO="2", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SolicitudesIndustrialTests(TestCase):
    crear_registro = casos_publicacion.SolicitudesPublicacionTests.crear_registro

    def setUp(self):
        casos_publicacion.SolicitudesPublicacionTests.setUp(self)
        self.industrial = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.alcance.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Industrial", codigo="I"),
        )
        for sede in self.sedes.values():
            EleccionClaustroDepartamentoSede.objects.create(
                eleccion_claustro_departamento=self.industrial, sede=sede,
            )
        self.mesa_industrial = Mesa.objects.create(
            eleccion=self.eleccion, eleccion_claustro_departamento=self.industrial,
            sede=self.sedes["Campus"], numero=2,
        )
        Mesa.objects.create(
            eleccion=self.eleccion, eleccion_claustro_departamento=self.industrial,
            sede=self.sedes["Medrano"], numero=3,
        )
        self.registros_industrial = []
        for indice in range(25):
            documento = str(37000000 + indice)
            registro = RegistroPadron.objects.create(
                elector=Elector.objects.create(dni=documento, legajo=documento, nombre="Industrial"),
                eleccion=self.eleccion, eleccion_claustro_departamento=self.industrial,
            )
            AsignacionSedePadron.objects.create(
                registro_padron=registro, sede=self.sedes["Campus"], estado="asignada",
            )
            AsignacionMesa.objects.create(registro_padron=registro, mesa=self.mesa_industrial)
            self.registros_industrial.append(registro)

    def solicitudes_industrial(self):
        return SolicitudCambioSede.objects.filter(
            registro_padron__eleccion_claustro_departamento=self.industrial,
        )

    def test_publicacion_agrega_20_industriales_sin_cambiar_padron_mesas_o_autoridades(self):
        modelos = (Elector, RegistroPadron, Mesa, AsignacionMesa, AsignacionAutoridad)
        anteriores = {modelo: list(modelo.objects.order_by("pk").values()) for modelo in modelos}
        self.eleccion.cambiar_estado("publicada")
        self.assertEqual(SolicitudCambioSede.objects.count(), 50)
        industriales = self.solicitudes_industrial()
        self.assertEqual(industriales.count(), 20)
        self.assertEqual(industriales.filter(
            sede_origen=self.sedes["Campus"], sede_destino=self.sedes["Medrano"],
        ).count(), 20)
        self.assertEqual(SolicitudCambioSede.objects.filter(registro_padron__in=self.registros).count(), 30)
        self.assertFalse(SolicitudCambioSede.objects.filter(registro_padron=self.carlos).exists())
        for modelo in modelos:
            self.assertEqual(list(modelo.objects.order_by("pk").values()), anteriores[modelo])

    def test_repetir_comando_conserva_resueltas_y_no_supera_los_cupos(self):
        self.eleccion.cambiar_estado("publicada")
        industrial = self.solicitudes_industrial().first()
        resolver_solicitud_cambio_sede(industrial, "aprobada", self.usuario)
        rechazada = self.solicitudes_industrial().exclude(pk=industrial.pk).first()
        rechazada.estado = "rechazada"
        rechazada.save(update_fields=["estado"])
        anteriores = list(SolicitudCambioSede.objects.order_by("pk").values())
        call_command("generar_solicitudes_cambio_sede_demo", stdout=StringIO())
        self.assertEqual(generar_solicitudes_demo(self.eleccion), 0)
        self.assertEqual(list(SolicitudCambioSede.objects.order_by("pk").values()), anteriores)
        self.assertEqual(self.solicitudes_industrial().count(), 20)

    def test_excluye_autoridades_qr_actividad_e_inactivos_del_lote_industrial(self):
        registros = self.registros_industrial
        turno = self.registros[10].asignacion_autoridad.turno
        AsignacionAutoridad.objects.create(
            registro_padron=registros[0], mesa=self.mesa_industrial,
            turno=turno, asignada_por=self.usuario,
        )
        RegistroPadron.objects.filter(pk=registros[1].pk).update(qr_generado_en=timezone.now())
        RegistroPadron.objects.filter(pk=registros[2].pk).update(sede=self.sedes["Campus"])
        RegistroPadron.objects.filter(pk=registros[3].pk).update(activo=False)
        self.eleccion.cambiar_estado("publicada")
        self.assertEqual(self.solicitudes_industrial().count(), 20)
        self.assertFalse(self.solicitudes_industrial().filter(registro_padron__in=registros[:4]).exists())

    def test_si_faltan_industriales_no_los_reemplaza_por_mas_sistemas(self):
        RegistroPadron.objects.filter(pk__in=[r.pk for r in self.registros_industrial[7:]]).update(activo=False)
        self.eleccion.cambiar_estado("publicada")
        self.assertEqual(self.solicitudes_industrial().count(), 7)
        self.assertEqual(SolicitudCambioSede.objects.filter(registro_padron__in=self.registros).count(), 30)
        self.assertEqual(SolicitudCambioSede.objects.count(), 37)

    def test_no_agrega_solicitudes_en_sentido_inverso(self):
        AsignacionSedePadron.objects.filter(registro_padron__in=self.registros_industrial).update(
            sede=self.sedes["Medrano"],
        )
        self.eleccion.cambiar_estado("publicada")
        self.assertFalse(self.solicitudes_industrial().exists())

    def test_no_descarta_departamentos_adicionales_incompatibles(self):
        principal = self.registros_industrial[0]
        adicional = RegistroPadron.objects.create(
            elector=principal.elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=self.alcance, es_principal=False,
            sede=self.sedes["Campus"],
        )
        AsignacionSedePadron.objects.create(
            registro_padron=adicional, sede=self.sedes["Campus"], estado="asignada",
        )
        self.eleccion.cambiar_estado("publicada")
        self.assertEqual(self.solicitudes_industrial().count(), 20)
        self.assertFalse(self.solicitudes_industrial().filter(registro_padron=principal).exists())

    def test_completa_solo_las_faltantes_de_una_eleccion_ya_publicada(self):
        self.eleccion.cambiar_estado("publicada")
        solicitudes = self.solicitudes_industrial().order_by("pk")
        conservadas = list(solicitudes.values_list("pk", flat=True)[:6])
        solicitudes.exclude(pk__in=conservadas).delete()
        self.assertEqual(generar_solicitudes_demo(self.eleccion), 14)
        self.assertEqual(self.solicitudes_industrial().count(), 20)
        self.assertEqual(self.solicitudes_industrial().filter(pk__in=conservadas).count(), 6)

    def test_otras_instancias_conservan_el_lote_original(self):
        for instancia in ("1", "3", ""):
            with self.subTest(instancia=instancia), override_settings(INSTANCIA_DEMO=instancia):
                from apps.padron.solicitudes_escenario import seleccionar_solicitudes_publicacion
                planes = seleccionar_solicitudes_publicacion(self.eleccion)
                self.assertEqual(len(planes), 30)
                self.assertFalse({p["dni"] for p in planes} & {r.elector.dni for r in self.registros_industrial})

    def test_error_en_industrial_revierte_tambien_el_lote_de_sistemas(self):
        guardar = SolicitudCambioSede.save

        def guardar_o_fallar(solicitud, *args, **kwargs):
            if solicitud.registro_padron.eleccion_claustro_departamento_id == self.industrial.pk:
                raise IntegrityError("Fallo industrial de prueba")
            return guardar(solicitud, *args, **kwargs)

        with patch.object(SolicitudCambioSede, "save", guardar_o_fallar), self.assertRaises(IntegrityError):
            self.eleccion.cambiar_estado("publicada")
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, "en_preparacion")
        self.assertFalse(SolicitudCambioSede.objects.exists())

    def crear_escenario_naval(self):
        naval = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.alcance.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Naval", codigo="U"),
        )
        for sede in self.sedes.values():
            EleccionClaustroDepartamentoSede.objects.create(
                eleccion_claustro_departamento=naval, sede=sede,
            )
        mesa = Mesa.objects.create(
            eleccion=self.eleccion, eleccion_claustro_departamento=naval,
            sede=self.sedes["Campus"], numero=4,
        )
        registros = []
        turno = self.registros[10].asignacion_autoridad.turno
        for indice in range(10):
            documento = str(38000000 + indice)
            registro = RegistroPadron.objects.create(
                elector=Elector.objects.create(dni=documento, legajo=documento, nombre="Naval"),
                eleccion=self.eleccion, eleccion_claustro_departamento=naval,
                sede=self.sedes["Campus"] if indice >= 4 else None,
                turno_cursada=turno if indice >= 4 else None,
            )
            AsignacionSedePadron.objects.create(
                registro_padron=registro, sede=self.sedes["Campus"], estado="asignada",
            )
            AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa)
            registros.append(registro)
        claustro = self.alcance.eleccion_claustro
        claustro.maximo_votantes_por_mesa = 60
        claustro.save(update_fields=["maximo_votantes_por_mesa"])
        return naval, registros

    def test_naval_lleva_el_lote_a_54_y_preve_dos_mesas_sin_modificar_padron(self):
        naval, _ = self.crear_escenario_naval()
        anteriores = {modelo: list(modelo.objects.order_by("pk").values()) for modelo in (
            Elector, RegistroPadron, AsignacionMesa, Mesa, AsignacionAutoridad,
        )}
        self.eleccion.cambiar_estado("publicada")
        self.assertEqual(SolicitudCambioSede.objects.count(), 54)
        self.assertEqual(SolicitudCambioSede.objects.filter(
            registro_padron__eleccion_claustro_departamento=naval,
            sede_origen=self.sedes["Campus"], sede_destino=self.sedes["Medrano"],
        ).count(), 4)
        impacto = estimar_impacto_mesas_por_sede(self.eleccion, SolicitudCambioSede.objects.all())
        self.assertEqual(impacto, {"agregadas": {self.sedes["Medrano"].pk: 2}, "quitadas": {}})
        for modelo, filas in anteriores.items():
            self.assertEqual(list(modelo.objects.order_by("pk").values()), filas)

    def test_aprobar_las_54_crea_solo_dos_mesas_y_conserva_autoridades(self):
        naval, _ = self.crear_escenario_naval()
        autoridades = list(AsignacionAutoridad.objects.order_by("pk").values())
        electores = Elector.objects.count()
        self.eleccion.cambiar_estado("publicada")
        for solicitud in SolicitudCambioSede.objects.order_by("pk"):
            resolver_solicitud_cambio_sede(solicitud, "aprobada", self.usuario)
        self.assertEqual(Mesa.objects.count(), 6)
        for alcance in (self.alcance, self.industrial, naval):
            self.assertEqual(Mesa.objects.filter(
                eleccion_claustro_departamento=alcance, sede=self.sedes["Medrano"],
            ).count(), 1)
        self.assertEqual(AsignacionMesa.objects.filter(
            mesa__eleccion_claustro_departamento=naval, mesa__sede=self.sedes["Medrano"],
        ).count(), 4)
        self.assertEqual(AsignacionMesa.objects.filter(
            mesa__eleccion_claustro_departamento=naval, mesa__sede=self.sedes["Campus"],
        ).count(), 6)
        self.assertEqual(Elector.objects.count(), electores)
        self.assertEqual(list(AsignacionAutoridad.objects.order_by("pk").values()), autoridades)

    def test_naval_resuelta_no_se_reemplaza_con_otro_solicitante(self):
        naval, _ = self.crear_escenario_naval()
        self.eleccion.cambiar_estado("publicada")
        solicitud = SolicitudCambioSede.objects.filter(
            registro_padron__eleccion_claustro_departamento=naval,
        ).first()
        resolver_solicitud_cambio_sede(solicitud, "aprobada", self.usuario)
        anteriores = list(SolicitudCambioSede.objects.order_by("pk").values())
        self.assertEqual(generar_solicitudes_demo(self.eleccion), 0)
        self.assertEqual(list(SolicitudCambioSede.objects.order_by("pk").values()), anteriores)

    def test_naval_no_inventa_personas_si_los_cuatro_estan_protegidos(self):
        naval, registros = self.crear_escenario_naval()
        AsignacionAutoridad.objects.create(
            registro_padron=registros[0], mesa=registros[0].asignacion_mesa.mesa,
            turno=self.registros[10].asignacion_autoridad.turno, asignada_por=self.usuario,
        )
        RegistroPadron.objects.filter(pk=registros[1].pk).update(qr_generado_en=timezone.now())
        RegistroPadron.objects.filter(pk=registros[2].pk).update(sede=self.sedes["Campus"])
        RegistroPadron.objects.filter(pk=registros[3].pk).update(activo=False)
        electores = Elector.objects.count()
        self.eleccion.cambiar_estado("publicada")
        self.assertFalse(SolicitudCambioSede.objects.filter(
            registro_padron__eleccion_claustro_departamento=naval,
        ).exists())
        self.assertEqual(SolicitudCambioSede.objects.count(), 50)
        self.assertEqual(Elector.objects.count(), electores)
