import hashlib
from datetime import time, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, EleccionClaustroTurno
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import AsignacionSedePadron, Elector, ImportacionPadron, RegistroPadron, SolicitudCambioSede
from apps.padron.services import (
    _valor_condicion, calcular_mesas_automaticas_eleccion, confirmar_importacion,
    resolver_solicitud_cambio_sede, validar_csv_padron,
)
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.usuarios.models import AsignacionRol, PerfilUsuario


class DepartamentosMultiplesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.directorio = TemporaryDirectory()
        cls.configuracion_archivos = override_settings(MEDIA_ROOT=cls.directorio.name, CLAVE_FIRMA_QR="clave-prueba")
        cls.configuracion_archivos.enable()

    @classmethod
    def tearDownClass(cls):
        cls.configuracion_archivos.disable()
        cls.directorio.cleanup()
        super().tearDownClass()

    def setUp(self):
        inicio = timezone.now()
        self.eleccion = Eleccion.objects.create(nombre="Elección departamentos", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8))
        self.claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Estudiantes"), maximo_votantes_por_mesa=10,
        )
        self.k = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.claustro, departamento=Departamento.objects.create(codigo="K", nombre="Sistemas"),
        )
        self.i = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.claustro, departamento=Departamento.objects.create(codigo="I", nombre="Industrial"),
        )
        self.sede = Sede.objects.create(nombre="Campus")
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.k, sede=self.sede)
        self.usuario = get_user_model().objects.create_superuser(username="junta-departamentos")
        self.contenido = (
            "DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail,Departamento Principal\n"
            "40123456,1234,Ana,Perez,I,ana@frba.utn.edu.ar,K\n"
            "40123456,1234,Ana,Perez,K,ana@frba.utn.edu.ar,K\n"
        ).encode()

    def importar(self):
        resultado = validar_csv_padron(self.contenido, self.claustro, "padron.csv")
        self.assertFalse(resultado.errores, resultado.errores)
        self.assertEqual(resultado.cantidad_validas, 1)
        importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion, eleccion_claustro=self.claustro, usuario=self.usuario,
            archivo=SimpleUploadedFile("padron.csv", self.contenido), nombre_archivo="padron.csv",
            huella_archivo=hashlib.sha256(self.contenido).hexdigest(),
        )
        self.assertEqual(confirmar_importacion(importacion), 1)
        return list(RegistroPadron.objects.filter(elector__dni="40123456").order_by("-es_principal"))

    def test_importa_una_persona_y_genera_mesas_con_sede_compartida(self):
        principal, adicional = self.importar()
        self.assertEqual(Elector.objects.count(), 1)
        self.assertEqual((principal.eleccion_claustro_departamento_id, principal.es_principal), (self.k.pk, True))
        self.assertEqual((adicional.eleccion_claustro_departamento_id, adicional.es_principal), (self.i.pk, False))
        self.assertNotEqual(principal.identificador_qr, adicional.identificador_qr)
        calcular_mesas_automaticas_eleccion(self.eleccion)
        principal.refresh_from_db()
        adicional.refresh_from_db()
        self.assertEqual(principal.asignacion_mesa.mesa.sede_id, self.sede.pk)
        self.assertEqual(adicional.asignacion_mesa.mesa.sede_id, self.sede.pk)
        self.assertFalse(principal.asignacion_mesa.mesa.es_especial)
        self.assertTrue(adicional.asignacion_mesa.mesa.es_especial)
        self.assertNotEqual(principal.asignacion_mesa.mesa_id, adicional.asignacion_mesa.mesa_id)

    def test_reimportacion_conserva_identidad_registros_y_codigos_qr(self):
        registros = self.importar()
        anteriores = {registro.pk: registro.identificador_qr for registro in registros}
        importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion, eleccion_claustro=self.claustro, usuario=self.usuario,
            archivo=SimpleUploadedFile("padron.csv", self.contenido), nombre_archivo="padron.csv",
            huella_archivo=hashlib.sha256(self.contenido).hexdigest(),
        )
        self.assertEqual(confirmar_importacion(importacion), 0)
        self.assertEqual(importacion.cantidad_validas, 1)
        self.assertEqual(importacion.cantidad_existentes, 1)
        self.assertEqual(dict(RegistroPadron.objects.values_list("pk", "identificador_qr")), anteriores)
        self.assertEqual(Elector.objects.count(), 1)

    def test_permite_participacion_independiente_por_cada_mesa(self):
        registros = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        for registro in registros:
            registro.refresh_from_db()
            mesa = registro.asignacion_mesa.mesa
            ServicioRegistroParticipacion.iniciar_escaneo_mesa(mesa=mesa, usuario=self.usuario)
            mesa.refresh_from_db()
            codigo = ServicioRegistroParticipacion.generar_codigo_qr(
                eleccion_id=self.eleccion.pk, mesa_numero=mesa.numero, identificador_qr=registro.identificador_qr,
            )
            resultado = ServicioRegistroParticipacion.registrar_lote(
                eleccion=self.eleccion, mesa=mesa, codigos_qr=[codigo], usuario=self.usuario,
            )
            self.assertEqual(resultado.creados, [registro.identificador_qr])
            self.assertEqual(ServicioRegistroParticipacion.registrar_lote(
                eleccion=self.eleccion, mesa=mesa, codigos_qr=[codigo], usuario=self.usuario,
            ).ya_registrados, [registro.identificador_qr])
        self.assertEqual(RegistroParticipacion.objects.count(), 2)

    def test_departamento_principal_se_toma_del_registro_de_la_eleccion(self):
        principal, adicional = self.importar()
        Elector.objects.filter(pk=principal.elector_id).update(departamento_principal=self.i.departamento)
        self.assertEqual(_valor_condicion(principal, "departamento_principal"), "K")
        self.assertEqual(_valor_condicion(adicional, "departamento_principal"), "K")

    def test_nomina_incluye_ambos_registros_de_una_sola_persona(self):
        from apps.autoridades.nomina import identificar_nomina

        registros = self.importar()
        identificados = identificar_nomina(self.claustro, b"Documento\n40123456\n", "nomina.csv")
        self.assertEqual(set(identificados), {registro.pk for registro in registros})

    def test_pantallas_cuentan_una_persona_y_no_dos_registros(self):
        self.importar()
        self.client.force_login(self.usuario)
        resumen = self.client.get(reverse("configurar-eleccion", args=(self.eleccion.pk,)))
        self.assertEqual(resumen.context["cantidad_padrones"], 1)
        preparacion = self.client.get(reverse("preparar-eleccion", args=(self.eleccion.pk,)))
        self.assertEqual(list(preparacion.context["claustros"])[0].cantidad_electores, 1)

    def test_inicio_muestra_mesas_y_situacion_por_cada_registro(self):
        principal, adicional = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        adicional.refresh_from_db()
        RegistroParticipacion.objects.create(
            registro_padron=adicional, mesa=adicional.asignacion_mesa.mesa,
            registrada_por=self.usuario, metodo=RegistroParticipacion.Metodo.MANUAL,
        )
        Eleccion.objects.filter(pk=self.eleccion.pk).update(
            estado=Eleccion.Estado.EN_CURSO, notificaciones_ausentes_confirmadas_en=timezone.now(),
        )
        PerfilUsuario.objects.create(usuario=self.usuario, elector=principal.elector)
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ELECTOR, eleccion=self.eleccion)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("inicio-autenticado"))
        self.assertContains(respuesta, "Mesa principal")
        self.assertContains(respuesta, "Mesa especial")
        situaciones = {registro.pk: registro.situacion_electoral["estado"] for registro in respuesta.context["registros"]}
        self.assertEqual(situaciones[principal.pk], "Voto Emitido")
        self.assertEqual(situaciones[adicional.pk], "En Curso - Voto No Registrado")

    def test_nomina_asigna_a_la_persona_una_sola_vez(self):
        from apps.autoridades.models import AsignacionAutoridad
        from apps.autoridades.nomina import confirmar_nomina, identificar_nomina, previsualizar_nomina

        self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        turno = Turno.objects.create(nombre="Mañana", hora_inicio=time(8), hora_fin=time(12))
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.claustro, turno=turno, titulares_por_mesa=1)
        identificados = identificar_nomina(self.claustro, b"Documento\n40123456\n", "nomina.csv")
        datos = {"registros": identificados, "mesa": False, "votar_mesa": False, "sede": False}
        propuesta = previsualizar_nomina(self.claustro, self.usuario, datos)
        self.assertEqual(propuesta["resumen"]["total"], 1)
        confirmar_nomina(self.claustro, self.usuario, propuesta)
        self.assertEqual(AsignacionAutoridad.objects.filter(registro_padron__elector__dni="40123456").count(), 1)

    def test_justificativo_de_autoridad_usa_el_registro_de_su_designacion(self):
        principal, adicional = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        adicional.refresh_from_db()
        turno = Turno.objects.create(nombre="Turno especial", hora_inicio=time(8), hora_fin=time(12))
        AsignacionAutoridad.objects.create(
            registro_padron=adicional, mesa=adicional.asignacion_mesa.mesa,
            turno=turno, asignada_por=self.usuario,
        )
        Eleccion.objects.filter(pk=self.eleccion.pk).update(
            estado=Eleccion.Estado.PUBLICADA, autoridades_confirmadas_en=timezone.now(),
            fecha_limite_justificacion_autoridades=timezone.localdate() + timedelta(days=1),
        )
        PerfilUsuario.objects.create(usuario=self.usuario, elector=principal.elector)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("mis-justificativos") + "?ausencia=autoridad")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["formulario"].registro_padron.pk, adicional.pk)

    def test_solicitud_traslada_ambas_mesas_a_la_misma_sede(self):
        principal, adicional = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        destino = Sede.objects.create(nombre="Medrano")
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.k, sede=destino)
        self.eleccion.estado = Eleccion.Estado.PUBLICADA
        self.eleccion.save(update_fields=("estado",))
        solicitud = SolicitudCambioSede.objects.create(
            registro_padron=principal, sede_origen=self.sede, sede_destino=destino,
        )
        resolver_solicitud_cambio_sede(solicitud, SolicitudCambioSede.Estado.APROBADA, self.usuario)
        for registro in (principal, adicional):
            registro.refresh_from_db()
            self.assertEqual(registro.asignacion_sede_padron.sede_id, destino.pk)
            self.assertEqual(registro.asignacion_mesa.mesa.sede_id, destino.pk)
        self.assertFalse(principal.asignacion_mesa.mesa.es_especial)
        self.assertTrue(adicional.asignacion_mesa.mesa.es_especial)

    def test_retorno_de_autoridad_restituye_ambas_mesas_sin_desplazar(self):
        from apps.autoridades.retorno_votacion import intentar_restituir_mesa

        principal, adicional = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        mesa_original = AsignacionMesa.objects.get(registro_padron=principal).mesa
        mesa_especial_original = AsignacionMesa.objects.get(registro_padron=adicional).mesa
        destino = Sede.objects.create(nombre="Medrano")
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.k, sede=destino)
        mesa_destino = Mesa.objects.create(eleccion=self.eleccion, numero=20, eleccion_claustro_departamento=self.k, sede=destino)
        especial_destino = Mesa.objects.create(eleccion=self.eleccion, numero=21, eleccion_claustro_departamento=self.i, sede=destino, es_especial=True)
        for registro, mesa in ((principal, mesa_destino), (adicional, especial_destino)):
            AsignacionMesa.objects.filter(registro_padron=registro).update(mesa=mesa)
            AsignacionSedePadron.objects.filter(registro_padron=registro).update(sede=destino)
        turno = Turno.objects.create(nombre="Turno retorno", hora_inicio=time(8), hora_fin=time(12))
        autoridad = AsignacionAutoridad.objects.create(
            registro_padron=principal, mesa=mesa_destino, mesa_votacion_original=mesa_original,
            turno=turno, asignada_por=self.usuario, estado=AsignacionAutoridad.Estado.RECHAZADA,
        )
        self.assertTrue(intentar_restituir_mesa(autoridad, self.usuario))
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=principal).mesa_id, mesa_original.pk)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=adicional).mesa_id, mesa_especial_original.pk)
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=adicional).sede_id, self.sede.pk)

    def test_reacomodo_por_autoridad_traslada_ambos_departamentos(self):
        from apps.autoridades.reordenamiento_padron import aplicar_padrones, previsualizar_padrones

        principal, adicional = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        destino = Sede.objects.create(nombre="Medrano")
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.k, sede=destino)
        mesa_destino = Mesa.objects.create(
            eleccion=self.eleccion, numero=20, eleccion_claustro_departamento=self.k, sede=destino,
        )
        titulares = {principal.pk: mesa_destino.pk}
        propuesta = previsualizar_padrones(
            self.claustro, titulares=titulares, permitir_cambio_mesa=True, permitir_cambio_sede=True,
        )
        with transaction.atomic():
            aplicar_padrones(self.claustro, propuesta, titulares=titulares)
        for registro in (principal, adicional):
            self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=registro).sede_id, destino.pk)
            self.assertEqual(AsignacionMesa.objects.get(registro_padron=registro).mesa.sede_id, destino.pk)
        self.assertTrue(AsignacionMesa.objects.get(registro_padron=adicional).mesa.es_especial)

    def test_retorno_conjunto_se_previsualiza_y_confirma_con_registros_reales(self):
        from apps.justificativos.models import JustificativoAusencia, TipoJustificativo

        principal, adicional = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        originales = {r.pk: AsignacionMesa.objects.get(registro_padron=r).mesa for r in (principal, adicional)}
        destino = Sede.objects.create(nombre="Medrano retorno")
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.k, sede=destino)
        nuevas = {
            principal.pk: Mesa.objects.create(eleccion=self.eleccion, numero=20, eleccion_claustro_departamento=self.k, sede=destino),
            adicional.pk: Mesa.objects.create(eleccion=self.eleccion, numero=21, eleccion_claustro_departamento=self.i, sede=destino, es_especial=True),
        }
        for registro in (principal, adicional):
            AsignacionMesa.objects.filter(registro_padron=registro).update(mesa=nuevas[registro.pk])
            AsignacionSedePadron.objects.filter(registro_padron=registro).update(sede=destino)
        for indice, (nombre, sede, mesas) in enumerate((("Bob", self.sede, originales), ("Carol", destino, nuevas))):
            elector = Elector.objects.create(dni=str(40123457 + indice), legajo=str(1235 + indice), nombre=nombre)
            for referencia, alcance, es_principal in ((principal, self.k, True), (adicional, self.i, False)):
                registro = RegistroPadron.objects.create(elector=elector, eleccion=self.eleccion, eleccion_claustro_departamento=alcance, es_principal=es_principal)
                AsignacionMesa.objects.create(registro_padron=registro, mesa=mesas[referencia.pk])
                AsignacionSedePadron.objects.create(registro_padron=registro, sede=sede, estado="asignada")
        turno = Turno.objects.create(nombre="Turno retorno revisado", hora_inicio=time(8), hora_fin=time(12))
        autoridad = AsignacionAutoridad.objects.create(
            registro_padron=principal, mesa=nuevas[principal.pk], mesa_votacion_original=originales[principal.pk],
            turno=turno, asignada_por=self.usuario, estado="rechazada",
        )
        JustificativoAusencia.objects.create(
            registro_padron=principal, ausencia="autoridad", estado="aprobado",
            tipo=TipoJustificativo.objects.create(nombre="Ausencia de autoridad"), detalle="Justificado",
        )
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.PUBLICADA, autoridades_confirmadas_en=timezone.now())
        self.client.force_login(self.usuario)
        ruta = reverse("revisar-retorno-votacion", args=(autoridad.pk,))
        respuesta = self.client.get(ruta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["movimientos"]), 2)
        confirmacion = self.client.post(ruta, {"propuesta": respuesta.context["propuesta"]})
        self.assertEqual(confirmacion.status_code, 302)
        for registro in (principal, adicional):
            self.assertEqual(AsignacionMesa.objects.get(registro_padron=registro).mesa_id, originales[registro.pk].pk)
            self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=registro).sede_id, self.sede.pk)

    def test_traslado_sin_reordenar_mueve_ambos_departamentos(self):
        from apps.autoridades.reordenamiento_padron import aplicar_traslados_sin_reordenar

        principal, adicional = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        destino = Sede.objects.create(nombre="Medrano")
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.k, sede=destino)
        mesa_destino = Mesa.objects.create(eleccion=self.eleccion, numero=20, eleccion_claustro_departamento=self.k, sede=destino)
        Mesa.objects.create(eleccion=self.eleccion, numero=21, eleccion_claustro_departamento=self.i, sede=destino, es_especial=True)
        turno = Turno.objects.create(nombre="Turno traslado", hora_inicio=time(8), hora_fin=time(12))
        autoridad = AsignacionAutoridad(registro_padron=principal, mesa=mesa_destino, turno=turno, asignada_por=self.usuario)
        with transaction.atomic():
            movimientos = aplicar_traslados_sin_reordenar([autoridad])
        self.assertEqual(len(movimientos), 2)
        for registro in (principal, adicional):
            self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=registro).sede_id, destino.pk)
            self.assertEqual(AsignacionMesa.objects.get(registro_padron=registro).mesa.sede_id, destino.pk)

    def test_base_impide_dos_principales_y_repetir_departamento(self):
        principal, adicional = self.importar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistroPadron.objects.filter(pk=adicional.pk).update(es_principal=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistroPadron.objects.create(
                elector=principal.elector, eleccion=self.eleccion,
                eleccion_claustro_departamento=principal.eleccion_claustro_departamento, es_principal=False,
            )

    def preparar_avisos_de_ausencia(self):
        registros = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.EN_CURSO)
        for registro in registros:
            mesa = AsignacionMesa.objects.get(registro_padron=registro).mesa
            Mesa.objects.filter(pk=mesa.pk).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
            RegistroParticipacion.objects.create(registro_padron=registro, mesa=mesa, registrada_por=self.usuario, metodo="manual")
        return registros

    def test_un_aviso_de_ausencia_por_persona_con_todas_sus_mesas(self):
        from apps.notificaciones.models import EnvioNotificacion
        from apps.notificaciones.services import crear_notificaciones_ausentes_confirmadas

        registros = self.preparar_avisos_de_ausencia()
        fecha = timezone.localdate() + timedelta(days=5)
        envios = crear_notificaciones_ausentes_confirmadas(self.eleccion, fecha)
        self.assertEqual(len(envios), 1)
        self.assertEqual(EnvioNotificacion.objects.count(), 1)
        for registro in registros:
            self.assertIn(AsignacionMesa.objects.get(registro_padron=registro).mesa.codigo, envios[0].contenido)
        self.assertIn("especial", envios[0].contenido)
        with self.assertRaisesMessage(ValueError, "ya fueron confirmadas"):
            crear_notificaciones_ausentes_confirmadas(self.eleccion, fecha)
        self.assertEqual(EnvioNotificacion.objects.count(), 1)

    def test_aviso_de_ausencia_no_incluye_la_mesa_donde_voto(self):
        from apps.notificaciones.services import crear_notificaciones_ausentes_confirmadas

        principal, adicional = self.preparar_avisos_de_ausencia()
        RegistroParticipacion.objects.filter(registro_padron=principal).delete()
        envio, = crear_notificaciones_ausentes_confirmadas(self.eleccion, timezone.localdate() + timedelta(days=5))
        self.assertNotIn(AsignacionMesa.objects.get(registro_padron=principal).mesa.codigo, envio.contenido)
        self.assertIn(AsignacionMesa.objects.get(registro_padron=adicional).mesa.codigo, envio.contenido)

    def test_un_aviso_de_publicacion_y_un_aviso_de_inicio_con_todas_las_mesas(self):
        from apps.notificaciones.models import EnvioNotificacion
        from apps.notificaciones.services import notificar_eleccion_en_curso, notificar_eleccion_publicada

        registros = self.importar()
        calcular_mesas_automaticas_eleccion(self.eleccion)
        with patch("apps.notificaciones.services.enviar_notificacion", return_value=True) as enviar:
            notificar_eleccion_publicada(self.eleccion)
            notificar_eleccion_en_curso(self.eleccion)
        self.assertEqual(enviar.call_count, 2)
        self.assertEqual(EnvioNotificacion.objects.count(), 2)
        inicio = EnvioNotificacion.objects.get(plantilla__codigo="eleccion-en-curso-asignacion-mesa")
        for registro in registros:
            self.assertIn(AsignacionMesa.objects.get(registro_padron=registro).mesa.codigo, inicio.contenido)
        self.assertIn("Campus", inicio.contenido)
        self.assertIn("especial", inicio.contenido)

    def crear_padron_por_puesto(self, puesto, nombre):
        from apps.padron.models import (
            CondicionInclusionPadronVotacion, ConfiguracionSedePadronVotacion,
            GrupoInclusionPadronVotacion, PadronVotacion,
        )

        padron = PadronVotacion.objects.create(eleccion_claustro=self.claustro, nombre=nombre)
        padron.puestos.add(puesto)
        grupo = GrupoInclusionPadronVotacion.objects.create(padron_votacion=padron)
        CondicionInclusionPadronVotacion.objects.create(grupo=grupo, campo="departamento", operador="en", valor="K,I")
        for alcance in (self.k, self.i):
            sede, _ = EleccionClaustroDepartamentoSede.objects.get_or_create(eleccion_claustro_departamento=alcance, sede=self.sede)
            ConfiguracionSedePadronVotacion.objects.create(
                padron_votacion=padron, eleccion_claustro_departamento=alcance, sede_predeterminada=sede,
            )
        return padron

    def test_cargos_generales_solo_en_principal_y_departamentales_en_su_registro(self):
        from apps.padron.services import calcular_padrones_votacion, registro_habilitado_para_puesto
        from apps.partidos.models import CargoElectivo, OrganoElectivo, PuestoEleccion

        principal, adicional = self.importar()
        organo = OrganoElectivo.objects.create(nombre="Consejo")
        cargo = CargoElectivo.objects.create(organo=organo, nombre="Consejero", permite_filtrar_departamentos=True)
        padrones = []
        for alcance, nombre in ((None, "General"), (self.k, "Sistemas"), (self.i, "Industrial")):
            puesto = PuestoEleccion.objects.create(
                puesto=cargo, eleccion_claustro=self.claustro, eleccion_claustro_departamento=alcance, cantidad_titulares=1,
            )
            padrones.append(self.crear_padron_por_puesto(puesto, nombre))
            self.assertEqual(registro_habilitado_para_puesto(principal, puesto), alcance in (None, self.k))
            self.assertEqual(registro_habilitado_para_puesto(adicional, puesto), alcance == self.i)
        self.assertEqual(calcular_padrones_votacion(self.claustro), 3)
        self.assertEqual(padrones[0].asignaciones.get().registro_padron_id, principal.pk)
        self.assertEqual(padrones[1].asignaciones.get().registro_padron_id, principal.pk)
        self.assertEqual(padrones[2].asignaciones.get().registro_padron_id, adicional.pk)

    def test_cargo_general_duplicado_rechaza_el_calculo_y_conserva_asignaciones(self):
        from apps.padron.models import AsignacionPadronVotacion
        from apps.padron.services import calcular_padrones_votacion
        from apps.partidos.models import CargoElectivo, OrganoElectivo, PuestoEleccion

        self.importar()
        cargo = CargoElectivo.objects.create(organo=OrganoElectivo.objects.create(nombre="General"), nombre="Representante")
        puesto = PuestoEleccion.objects.create(puesto=cargo, eleccion_claustro=self.claustro, cantidad_titulares=1)
        self.crear_padron_por_puesto(puesto, "Primero")
        self.assertEqual(calcular_padrones_votacion(self.claustro), 1)
        anteriores = list(AsignacionPadronVotacion.objects.values_list("pk", "registro_padron_id"))
        self.crear_padron_por_puesto(puesto, "Segundo")
        with self.assertRaisesMessage(ValueError, "mismo cargo"):
            calcular_padrones_votacion(self.claustro)
        self.assertEqual(list(AsignacionPadronVotacion.objects.values_list("pk", "registro_padron_id")), anteriores)
