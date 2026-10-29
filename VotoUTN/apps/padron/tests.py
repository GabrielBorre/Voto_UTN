import io
from datetime import datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Count
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import make_aware
from PIL import Image

from openpyxl import Workbook

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionClaustroTurno,
    EleccionClaustroSede,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.forms import FormularioArchivoPadron, FormularioReglaSedeClaustro
from apps.padron.management.commands.seed_voters import Command as ComandoGenerarQr
from apps.padron.models import (
    AsignacionSedePadron,
    CondicionInclusionPadronVotacion,
    ConfiguracionSedesClaustro,
    ConfiguracionSedePadronVotacion,
    Elector,
    EmisionPadronImprimible,
    ErrorImportacionPadron,
    ImportacionPadron,
    GrupoInclusionPadronVotacion,
    PadronVotacion,
    RegistroPadron,
    ReglaAsignacionSede,
    ReglaSedeClaustro,
    SolicitudCambioSede,
)
from apps.padron.services import (
    calcular_asignaciones_sede_claustro,
    calcular_mesas_automaticas_eleccion,
    calcular_padrones_votacion,
    eliminar_padron_claustro,
    recalcular_sedes_y_mesas_claustro,
    resolver_solicitud_cambio_sede,
    resolver_solicitudes_pendientes,
)
from apps.partidos.models import CargoElectivo, OrganoElectivo, PuestoEleccion
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.usuarios.models import AsignacionRol, PerfilUsuario


class PadronViewsTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.sede = Sede.objects.create(nombre="Campus")
        self.turno = Turno.objects.create(nombre="Manana", hora_inicio=time(8), hora_fin=time(12))
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro, maximo_votantes_por_mesa=20)
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.turno)
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=self.eleccion_claustro, departamento=self.departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion)

    def test_previsualizar_padron_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "padron/cargar.html")
        self.assertContains(
            respuesta,
            '<a class="active" href="/gestion/elecciones/">Configurar elección</a>',
        )

    def test_exportar_padron_csv_y_pdf_desde_gestion_se_limita_al_claustro(self):
        otro_claustro = Claustro.objects.create(nombre="Docentes")
        otro_alcance = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=otro_claustro)
        otro_departamento = Departamento.objects.create(nombre="Industrial", codigo="I")
        otro_configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otro_alcance, departamento=otro_departamento,
        )
        for dni, alcance in (("40200000", self.configuracion), ("40100000", self.configuracion), ("40300000", otro_configuracion)):
            elector = Elector.objects.create(dni=dni, legajo=f"L{dni}", nombre="Nombre", apellido="Prueba")
            RegistroPadron.objects.create(
                elector=elector,
                eleccion=self.eleccion,
                eleccion_claustro_departamento=alcance,
            )
        self.client.force_login(self.usuario)
        ruta = reverse("exportar-padron-claustro", args=(self.eleccion.id, self.eleccion_claustro.id, "csv"))
        respuesta_csv = self.client.get(ruta)
        contenido_csv = respuesta_csv.content.decode("utf-8-sig")
        self.assertIn("40100000", contenido_csv)
        self.assertIn("40200000", contenido_csv)
        self.assertNotIn("40300000", contenido_csv)

        respuesta_pdf = self.client.get(ruta.replace("csv", "pdf"))
        self.assertEqual(respuesta_pdf.status_code, 200)
        self.assertEqual(respuesta_pdf["Content-Type"], "application/pdf")
        self.assertTrue(respuesta_pdf.content.startswith(b"%PDF"))
        self.assertIn("padron_estudiantes_".encode(), respuesta_pdf["Content-Disposition"].encode())

    def test_eleccion_cerrada_bloquea_pantalla_y_configuracion_del_padron(self):
        self.eleccion.estado = Eleccion.Estado.FINALIZADA
        self.eleccion.save(update_fields=("estado",))
        self.client.force_login(self.usuario)
        ruta = reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id))

        respuesta_consulta = self.client.get(ruta)
        respuesta_guardado = self.client.post(
            ruta,
            {
                "guardar-configuracion": "1",
                "configuracion-fecha_votacion": self.eleccion.fecha_inicio.isoformat(),
                "configuracion-maximo_votantes_por_mesa": "20",
            },
        )

        self.assertEqual(respuesta_consulta.status_code, 403)
        self.assertEqual(respuesta_guardado.status_code, 403)
        self.eleccion_claustro.refresh_from_db()
        self.assertIsNone(self.eleccion_claustro.fecha_votacion)

    def test_detalle_importacion_usa_presentacion_visual_unificada(self):
        importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.eleccion_claustro,
            archivo=SimpleUploadedFile(
                "estudiantes.csv",
                (
                    "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail,Sede donde asiste\n"
                    "40123456,DNI,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Campus\n"
                    "40123457,DNI,2024002,Ana,Gomez,K,ana.gomez@frba.utn.edu.ar,Campus\n"
                    "40123458,DNI,2024003,Carlos,,K,carlos.lopez@frba.utn.edu.ar,Campus\n"
                ).encode(),
            ),
            nombre_archivo="estudiantes.csv",
            huella_archivo="archivo-ejemplo",
            cantidad_filas=3,
            cantidad_validas=2,
            cantidad_existentes=1,
            cantidad_errores=1,
            estado=ImportacionPadron.Estado.RECHAZADA,
            usuario=self.usuario,
        )
        ErrorImportacionPadron.objects.create(
            importacion=importacion,
            fila=4,
            campo="mail",
            mensaje="Correo electrónico inválido.",
        )
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(
            reverse("detalle-importacion-padron", args=(self.eleccion.id, importacion.id))
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "padron/detalle_importacion.html")
        self.assertContains(respuesta, 'class="management-panel import-review-panel"')
        self.assertContains(respuesta, 'class="card management-section"', count=3)
        self.assertContains(respuesta, "Resultado de la validación")
        self.assertContains(respuesta, "Registros en el archivo")
        self.assertContains(respuesta, "Nuevos para incorporar")
        self.assertContains(respuesta, "Ya incluidos en este padrón")
        self.assertContains(respuesta, "Errores detectados")
        self.assertContains(respuesta, "si hay errores, no se incorpora ningún registro")
        self.assertEqual(respuesta.context["importacion"].cantidad_filas, 3)
        self.assertEqual(respuesta.context["importacion"].cantidad_validas, 2)
        self.assertEqual(respuesta.context["importacion"].cantidad_existentes, 1)
        self.assertEqual(respuesta.context["importacion"].cantidad_nuevos, 1)
        self.assertEqual(respuesta.context["importacion"].cantidad_errores, 1)
        self.assertNotContains(respuesta, "Cargada")
        self.assertContains(respuesta, "Columnas detectadas")
        self.assertNotContains(respuesta, "Confirmar importación")
        self.assertContains(respuesta, "Volver al padrón")

    def test_previsualizacion_guarda_y_muestra_registros_ya_existentes(self):
        elector = Elector.objects.create(
            dni="40123456",
            legajo="2024001",
            nombre="Juan",
            apellido="Perez",
            correo_electronico="juan.perez@frba.utn.edu.ar",
        )
        RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )
        contenido = (
            "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail,Sede donde asiste\n"
            "40123456,DNI,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Campus\n"
        ).encode("utf-8")
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "archivo": SimpleUploadedFile(
                    "padron-repetido.csv",
                    contenido,
                    content_type="text/csv",
                )
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        importacion = ImportacionPadron.objects.get(nombre_archivo="padron-repetido.csv")
        self.assertEqual(importacion.cantidad_existentes, 1)
        self.assertEqual(importacion.cantidad_validas, 1)
        self.assertEqual(importacion.cantidad_nuevos, 0)
        respuesta_detalle = self.client.get(
            reverse("detalle-importacion-padron", args=(self.eleccion.id, importacion.id))
        )
        self.assertContains(respuesta_detalle, "Ya incluidos en este padrón")
        self.assertContains(respuesta_detalle, "<span>1</span>")

    def test_previsualizacion_calcula_nuevos_y_existentes_aunque_haya_errores(self):
        elector_existente = Elector.objects.create(
            dni="40123456",
            legajo="2024001",
            nombre="Juan",
            apellido="Perez",
            correo_electronico="juan.perez@frba.utn.edu.ar",
        )
        RegistroPadron.objects.create(
            elector=elector_existente,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )
        contenido = (
            "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail,Sede donde asiste\n"
            "40123456,DNI,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Campus\n"
            "40123457,DNI,2024002,Ana,Gomez,K,ana.gomez@frba.utn.edu.ar,Campus\n"
            "40123458,DNI,2024003,Carlos,,K,carlos.lopez@frba.utn.edu.ar,Campus\n"
        ).encode("utf-8")
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "archivo": SimpleUploadedFile(
                    "padron-con-errores.csv",
                    contenido,
                    content_type="text/csv",
                )
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        importacion = ImportacionPadron.objects.get(nombre_archivo="padron-con-errores.csv")
        self.assertEqual(importacion.estado, ImportacionPadron.Estado.RECHAZADA)
        self.assertEqual(importacion.cantidad_filas, 3)
        self.assertEqual(importacion.cantidad_validas, 2)
        self.assertEqual(importacion.cantidad_existentes, 1)
        self.assertEqual(importacion.cantidad_nuevos, 1)
        self.assertEqual(importacion.cantidad_errores, 1)
        respuesta_detalle = self.client.get(
            reverse("detalle-importacion-padron", args=(self.eleccion.id, importacion.id))
        )
        self.assertContains(respuesta_detalle, "Nuevos para incorporar")
        self.assertContains(respuesta_detalle, "Ya incluidos en este padrón")
        self.assertContains(respuesta_detalle, "si hay errores, no se incorpora ningún registro")
        self.assertNotContains(respuesta_detalle, "Confirmar importación")

    @patch("apps.padron.views.confirmar_importacion", return_value=0)
    def test_confirmacion_explicita_que_los_electores_ya_estaban_en_el_padron(
        self, confirmar_importacion
    ):
        importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.eleccion_claustro,
            archivo=SimpleUploadedFile(
                "padron-repetido.csv",
                b"DNI,Legajo,Nombre,Apellido\n",
            ),
            nombre_archivo="padron-repetido.csv",
            huella_archivo="archivo-ejemplo",
            cantidad_filas=500,
            cantidad_validas=500,
            cantidad_existentes=500,
            usuario=self.usuario,
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse(
                "confirmar-importacion-padron",
                args=(self.eleccion.id, importacion.id),
            ),
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Padrón confirmado: 0 electores nuevos, 500 electores ya existentes.",
        )
        confirmar_importacion.assert_called_once_with(importacion)

    def test_gestion_de_padrones_presenta_tarjetas_por_claustro(self):
        elector_activo = Elector.objects.create(
            dni="40123456",
            legajo="2024001",
            nombre="Juan",
        )
        elector_inactivo = Elector.objects.create(
            dni="40123457",
            legajo="2024002",
            nombre="Ana",
        )
        RegistroPadron.objects.create(
            elector=elector_activo,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            activo=True,
        )
        RegistroPadron.objects.create(
            elector=elector_inactivo,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            activo=False,
        )
        administrador = get_user_model().objects.create_user(username="admin-padrones")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(administrador)

        respuesta = self.client.get(reverse("preparar-eleccion", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "elecciones/preparar_eleccion.html")
        self.assertContains(respuesta, 'class="toolbar configuration-grid padron-cloister-grid"')
        self.assertContains(respuesta, 'class="option"', count=1)
        self.assertContains(
            respuesta,
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)),
        )
        self.assertContains(respuesta, "1</strong> electores en padrón")
        self.assertContains(respuesta, "Gestionar padrón", count=1)

    def test_panel_general_informa_el_recalculo_automatico_de_mesas(self):
        administrador = get_user_model().objects.create_user(username="admin-mesas-panel")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(administrador)

        respuesta = self.client.get(reverse("preparar-eleccion", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Las mesas se recalculan automáticamente")

    def test_gestion_de_padron_integra_configuracion_carga_e_historial_del_claustro(self):
        administrador = get_user_model().objects.create_user(username="gestor-padron")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        otra_eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes padrón"),
        )
        ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.eleccion_claustro,
            archivo=SimpleUploadedFile("estudiantes.csv", b"contenido"),
            nombre_archivo="estudiantes.csv",
            huella_archivo="estudiantes",
            estado=ImportacionPadron.Estado.PREVISUALIZADA,
            usuario=administrador,
        )
        for indice, estado in enumerate((
            ImportacionPadron.Estado.CONFIRMADA,
            ImportacionPadron.Estado.RECHAZADA,
            ImportacionPadron.Estado.PADRON_ELIMINADO,
        )):
            ImportacionPadron.objects.create(
                eleccion=self.eleccion,
                eleccion_claustro=self.eleccion_claustro,
                archivo=SimpleUploadedFile(f"estado-{indice}.csv", b"contenido"),
                nombre_archivo=f"estado-{indice}.csv",
                huella_archivo=f"estado-{indice}",
                estado=estado,
                usuario=administrador,
            )
        elector = Elector.objects.create(
            dni="40765432",
            legajo="PAD001",
            nombre="Elector de prueba",
        )
        RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
        )
        ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=otra_eleccion_claustro,
            archivo=SimpleUploadedFile("docentes.csv", b"contenido"),
            nombre_archivo="docentes.csv",
            huella_archivo="docentes",
            usuario=administrador,
        )
        self.client.force_login(administrador)

        respuesta = self.client.get(
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id))
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'class="card management-section"', count=2)
        self.assertContains(respuesta, '<details class="historial-importaciones"')
        self.assertContains(respuesta, f'{reverse("gestionar-mesas", args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}')
        self.assertNotContains(respuesta, "Exportar padrón CSV")
        self.assertNotContains(respuesta, "Calcular asignaciones")
        self.assertContains(respuesta, 'class="card management-section padron-management-card"')
        self.assertContains(respuesta, "estudiantes.csv")
        self.assertNotContains(respuesta, "docentes.csv")
        self.assertContains(respuesta, 'name="configuracion-fecha_votacion"')
        self.assertContains(respuesta, 'name="configuracion-maximo_votantes_por_mesa"')
        self.assertContains(respuesta, "data-autoguardar-configuracion")
        self.assertContains(respuesta, "Los cambios se guardan automáticamente")
        self.assertNotContains(respuesta, 'name="configuracion-departamentos"')
        self.assertNotContains(respuesta, 'name="configuracion-sedes"')
        self.assertContains(respuesta, "Gestión del padrón")
        self.assertContains(respuesta, "Electores totales")
        self.assertContains(respuesta, 'class="button danger"')
        self.assertContains(respuesta, 'class="pill warn">Previsualizada</span>')
        self.assertContains(respuesta, 'class="pill ok">Confirmada</span>')
        self.assertContains(respuesta, 'class="pill gray">Rechazada</span>')
        self.assertContains(respuesta, 'class="pill danger">Padrón eliminado</span>')
        self.assertContains(respuesta, "Configurar asignación de sedes")

    def test_gestion_de_padron_guarda_fecha_y_maximo_sin_modificar_alcances(self):
        administrador = get_user_model().objects.create_user(username="configurador-padron")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(administrador)
        departamentos_anteriores = set(
            self.eleccion_claustro.departamentos.values_list("id", flat=True)
        )
        sedes_anteriores = set(
            self.eleccion_claustro.sedes_habilitadas.values_list("id", flat=True)
        )
        elector = Elector.objects.create(legajo="99001", dni="49990001", nombre="Elector de prueba")
        RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )

        respuesta = self.client.post(
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "configuracion-fecha_votacion": "2026-08-03",
                "configuracion-maximo_votantes_por_mesa": 35,
                "guardar-configuracion": "",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)),
            fetch_redirect_response=False,
        )
        self.eleccion_claustro.refresh_from_db()
        self.assertEqual(self.eleccion_claustro.maximo_votantes_por_mesa, 35)
        self.assertSetEqual(
            set(self.eleccion_claustro.departamentos.values_list("id", flat=True)),
            departamentos_anteriores,
        )
        self.assertSetEqual(
            set(self.eleccion_claustro.sedes_habilitadas.values_list("id", flat=True)),
            sedes_anteriores,
        )
        self.assertFalse(Mesa.objects.filter(eleccion=self.eleccion, generada_automaticamente=True).exists())

    def test_cambiar_maximo_recalcula_mesas_si_todas_las_sedes_estan_asignadas(self):
        administrador = get_user_model().objects.create_user(username="admin-maximo-mesas")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        elector = Elector.objects.create(legajo="99002", dni="49990002", nombre="Elector mesa")
        registro = RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
        )
        AsignacionSedePadron.objects.create(
            registro_padron=registro,
            sede=self.sede,
            estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "configuracion-fecha_votacion": "2026-08-03",
                "configuracion-maximo_votantes_por_mesa": 1,
                "guardar-configuracion": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(registro.asignacion_mesa.mesa.generada_automaticamente)

    def test_recalculo_automatico_asigna_sedes_y_mesas_de_toda_la_eleccion(self):
        elector = Elector.objects.create(legajo="99003", dni="49990003", nombre="Elector reglas")
        registro = RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
        )

        _resultado, mesas_ok, _detalle = recalcular_sedes_y_mesas_claustro(self.eleccion_claustro, usuario=self.usuario)

        self.assertTrue(mesas_ok)
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=registro).sede, self.sede)
        self.assertTrue(registro.asignacion_mesa.mesa.generada_automaticamente)

    def test_autoguardado_persiste_fecha_y_maximo_sin_pulsar_el_boton(self):
        administrador = get_user_model().objects.create_user(username="autoguardado-padron")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "configuracion-fecha_votacion": "2026-08-03",
                "configuracion-maximo_votantes_por_mesa": 42,
                "guardar-configuracion": "1",
                "autoguardado": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Mesas recalculadas automáticamente", respuesta.json()["mensaje"])
        self.eleccion_claustro.refresh_from_db()
        self.assertEqual(str(self.eleccion_claustro.fecha_votacion), "2026-08-03")
        self.assertEqual(self.eleccion_claustro.maximo_votantes_por_mesa, 42)

        respuesta = self.client.get(
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id))
        )
        self.assertContains(respuesta, 'name="configuracion-fecha_votacion" value="2026-08-03"')

    @patch(
        "apps.padron.views.calcular_mesas_automaticas_eleccion",
        side_effect=ValueError("detalle interno"),
    )
    def test_autoguardado_no_expone_detalle_del_error_al_recalcular_mesas(self, _):
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "configuracion-fecha_votacion": "2026-08-03",
                "configuracion-maximo_votantes_por_mesa": 42,
                "guardar-configuracion": "1",
                "autoguardado": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.json()["mensaje"],
            "Configuración guardada; las mesas no se pudieron recalcular.",
        )
        self.assertNotIn("detalle interno", respuesta.content.decode())

    def test_descargar_plantilla_padron_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("descargar-plantilla-padron", args=(self.eleccion.id, self.eleccion_claustro.id)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")

    def test_descargar_plantilla_padron_incluye_fila_de_ejemplo(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("descargar-plantilla-padron", args=(self.eleccion.id, self.eleccion_claustro.id)))

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode("utf-8-sig")
        lineas = contenido.splitlines()
        self.assertGreaterEqual(len(lineas), 2)
        self.assertEqual(lineas[0], "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde cursa,Nivel")
        self.assertEqual(lineas[1], "40123456,DNI,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Si,K,Campus,1")
        tipos = {fila.split(",")[1] for fila in lineas[1:]}
        self.assertTrue({"DNI", "CUIL", "CUIT", "PAS"}.issubset(tipos))

    def test_importacion_acepta_tipos_documento_definidos_y_rechaza_otros(self):
        from apps.padron.services import validar_csv_padron

        for tipo, documento in (("CUIL", "20301234567"), ("CUIT", "27301234569"), ("PAS", "A123456")):
            contenido = (
                "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n"
                f"{documento},{tipo},legajo-{tipo},Nombre,Prueba,K,{tipo.lower()}@frba.utn.edu.ar\n"
            ).encode()
            resultado = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")
            self.assertNotIn("tipo_documento", [campo for _, campo, _ in resultado.errores])

        contenido = b"DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n40123456,PASAPORTE,legajo-x,Nombre,Prueba,K,x@frba.utn.edu.ar\n"
        resultado = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")
        self.assertIn("tipo_documento", [campo for _, campo, _ in resultado.errores])

    def test_validar_csv_padron_mapea_departamento_principal_correctamente(self):
        contenido = (
            "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde asiste,Nivel\n"
            "40123456,DNI,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Si,K,Campus,1\n"
        ).encode("utf-8")

        from apps.padron.models import ImportacionPadron
        from apps.padron.services import confirmar_importacion, validar_csv_padron

        validacion = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")

        self.assertFalse(validacion.errores)
        self.assertEqual(validacion.filas[0]["departamento_principal"], "K")
        self.assertEqual(validacion.filas[0]["departamento"], "K")

        importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.eleccion_claustro,
            archivo=SimpleUploadedFile("padron.csv", contenido, content_type="text/csv"),
            nombre_archivo="padron.csv",
            huella_archivo="123",
            usuario=self.usuario,
        )
        importacion.huella_archivo = __import__("hashlib").sha256(contenido).hexdigest()
        importacion.save(update_fields=("huella_archivo",))

        cantidad = confirmar_importacion(importacion)

        self.assertEqual(cantidad, 1)
        elector = importacion.eleccion.registros_padron.get(elector__dni="40123456")
        self.assertEqual(elector.elector.nombre, "Juan")
        self.assertEqual(elector.elector.apellido, "Perez")
        self.assertEqual(elector.elector.departamento_principal, self.departamento)
        validacion_repeticion = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")
        self.assertFalse(validacion_repeticion.errores)
        self.assertEqual(validacion_repeticion.cantidad_existentes, 1)

    def test_validar_csv_padron_acepta_dni_numerico_de_excel(self):
        contenido = (
            "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde asiste,Nivel\n"
            "40123456.0,DNI,2024004,Lucia,Diaz,K,lucia.diaz@frba.utn.edu.ar,No,K,Campus,1\n"
        ).encode("utf-8")

        from apps.padron.services import validar_csv_padron

        validacion = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")

        self.assertFalse(validacion.errores)
        self.assertEqual(validacion.filas[0]["dni"], "40123456")

    def test_validar_csv_padron_indica_solo_el_legajo_incorrecto(self):
        from apps.padron.models import Elector
        from apps.padron.services import validar_csv_padron

        Elector.objects.create(dni="40123456", legajo="2024999", nombre="Juan", apellido="Perez")
        contenido = (
            "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail,Sede donde asiste\n"
            "40123456,DNI,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Campus\n"
        ).encode("utf-8")

        validacion = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")

        self.assertIn((2, "legajo", "El legajo no coincide con el elector existente."), validacion.errores)
        self.assertNotIn((2, "dni", "El DNI no coincide con el elector existente."), validacion.errores)

    def test_confirmar_importacion_no_requiere_maximo_por_mesa(self):
        self.eleccion_claustro.maximo_votantes_por_mesa = None
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        contenido = (
            "DNI,Tipo Documento,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde asiste,Nivel\n"
            "40123456,DNI,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Si,K,Campus,1\n"
        ).encode("utf-8")

        from apps.padron.models import ImportacionPadron
        from apps.padron.services import confirmar_importacion

        importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.eleccion_claustro,
            archivo=SimpleUploadedFile("padron.csv", contenido, content_type="text/csv"),
            nombre_archivo="padron.csv",
            huella_archivo="123",
            usuario=self.usuario,
        )
        importacion.huella_archivo = __import__("hashlib").sha256(contenido).hexdigest()
        importacion.save(update_fields=("huella_archivo",))

        cantidad = confirmar_importacion(importacion)

        self.assertEqual(cantidad, 1)
        self.assertEqual(importacion.estado, ImportacionPadron.Estado.CONFIRMADA)


class CalculoMesasAutomaticasEleccionTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion mesas",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        self.sede_electoral = Sede.objects.create(nombre="Medrano")
        self.sede_cursada = Sede.objects.create(nombre="Campus")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        self.claustro_a = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes mesas"),
            maximo_votantes_por_mesa=2,
        )
        self.alcance_a = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.claustro_a,
            departamento=self.departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=self.alcance_a,
            sede=self.sede_electoral,
        )
        self.claustro_b = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="No docentes mesas"),
            maximo_votantes_por_mesa=1,
        )
        self.alcance_b = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.claustro_b,
            departamento=None,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=self.alcance_b,
            sede=self.sede_electoral,
        )

    def crear_elector(self, legajo, alcance, asignar_sede=True):
        elector = Elector.objects.create(
            legajo=legajo,
            dni=f"{int(legajo) + 40000000}",
            nombre=f"Elector {legajo}",
        )
        registro = RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=alcance,
            sede=self.sede_cursada,
        )
        if asignar_sede:
            AsignacionSedePadron.objects.create(
                registro_padron=registro,
                sede=self.sede_electoral,
                estado=AsignacionSedePadron.Estado.ASIGNADA,
            )
        return registro

    def test_calcula_todos_los_claustros_por_sede_electoral_y_respeta_maximos(self):
        registros_a = [self.crear_elector(str(numero), self.alcance_a) for numero in range(1, 4)]
        registro_b = self.crear_elector("10", self.alcance_b)
        mesa_manual = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=7,
            eleccion_claustro_departamento=self.alcance_a,
            sede=self.sede_electoral,
            generada_automaticamente=False,
        )

        resultado = calcular_mesas_automaticas_eleccion(self.eleccion)

        self.assertEqual(resultado["electores"], 4)
        self.assertEqual(resultado["mesas"], 3)
        self.assertEqual(AsignacionMesa.objects.filter(mesa__generada_automaticamente=True).count(), 4)
        self.assertEqual(
            list(AsignacionMesa.objects.filter(mesa__generada_automaticamente=True, registro_padron__in=registros_a).values_list("mesa__eleccion_claustro_departamento__eleccion_claustro_id", flat=True).distinct()),
            [self.claustro_a.id],
        )
        self.assertEqual(registro_b.asignacion_mesa.mesa.eleccion_claustro_departamento.eleccion_claustro, self.claustro_b)
        self.assertTrue(all(registro.asignacion_mesa.mesa.sede == self.sede_electoral for registro in registros_a + [registro_b]))
        self.assertTrue(Mesa.objects.filter(pk=mesa_manual.pk).exists())
        self.assertLessEqual(
            max(mesa.asignaciones_padron.count() for mesa in Mesa.objects.filter(eleccion=self.eleccion, generada_automaticamente=True)),
            2,
        )

    def test_reparte_el_remanente_entre_las_dos_ultimas_mesas(self):
        self.claustro_a.maximo_votantes_por_mesa = 50
        self.claustro_a.save(update_fields=("maximo_votantes_por_mesa",))
        registros = [self.crear_elector(str(numero), self.alcance_a) for numero in range(100, 201)]

        calcular_mesas_automaticas_eleccion(self.eleccion)

        cantidades = list(
            AsignacionMesa.objects.filter(registro_padron__in=registros)
            .values("mesa__numero")
            .annotate(total=Count("id"))
            .order_by("mesa__numero")
            .values_list("total", flat=True)
        )
        self.assertEqual(cantidades, [50, 26, 25])

    def test_recalculo_reemplaza_solo_mesas_automaticas(self):
        registros = [self.crear_elector(str(numero), self.alcance_a) for numero in range(20, 23)]
        mesa_manual = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=5,
            eleccion_claustro_departamento=self.alcance_a,
            sede=self.sede_electoral,
        )
        calcular_mesas_automaticas_eleccion(self.eleccion)
        ids_anteriores = set(Mesa.objects.filter(eleccion=self.eleccion, generada_automaticamente=True).values_list("id", flat=True))
        self.claustro_a.maximo_votantes_por_mesa = 1
        self.claustro_a.save(update_fields=("maximo_votantes_por_mesa",))

        resultado = calcular_mesas_automaticas_eleccion(self.eleccion)

        self.assertEqual(resultado["mesas"], 3)
        self.assertTrue(Mesa.objects.filter(pk=mesa_manual.pk).exists())
        self.assertEqual(AsignacionMesa.objects.filter(registro_padron__in=registros).count(), 3)
        self.assertFalse(Mesa.objects.filter(pk__in=ids_anteriores).exists())
        self.assertTrue(all(registro.asignacion_mesa.mesa.generada_automaticamente for registro in registros))

    def test_error_en_un_claustro_no_borra_la_distribucion_anterior(self):
        self.crear_elector("40", self.alcance_b)
        mesa_anterior = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.alcance_a,
            sede=self.sede_electoral,
            generada_automaticamente=True,
        )
        self.claustro_b.maximo_votantes_por_mesa = None
        self.claustro_b.save(update_fields=("maximo_votantes_por_mesa",))

        with self.assertRaisesRegex(ValueError, "No se modific"):
            calcular_mesas_automaticas_eleccion(self.eleccion)

        self.assertTrue(Mesa.objects.filter(pk=mesa_anterior.pk).exists())

    def test_no_exige_maximo_en_claustro_sin_electores_activos(self):
        registros = [self.crear_elector(str(numero), self.alcance_a) for numero in range(50, 53)]
        self.claustro_b.maximo_votantes_por_mesa = None
        self.claustro_b.save(update_fields=("maximo_votantes_por_mesa",))

        resultado = calcular_mesas_automaticas_eleccion(self.eleccion)

        self.assertEqual(resultado["electores"], 3)
        self.assertEqual(resultado["mesas"], 2)
        self.assertEqual(AsignacionMesa.objects.filter(registro_padron__in=registros).count(), 3)

    def test_elector_sin_sede_asignada_impide_el_calculo_completo(self):
        self.crear_elector("30", self.alcance_a, asignar_sede=False)
        mesa_anterior = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.alcance_a,
            sede=self.sede_electoral,
            generada_automaticamente=True,
        )

        with self.assertRaisesMessage(ValueError, "sin sede electoral asignada"):
            calcular_mesas_automaticas_eleccion(self.eleccion)

        self.assertTrue(Mesa.objects.filter(pk=mesa_anterior.pk).exists())


class FormularioArchivoPadronTests(TestCase):
    def test_rechaza_archivo_no_csv_ni_xlsx(self):
        formulario = FormularioArchivoPadron(files={"archivo": SimpleUploadedFile("padron.txt", b"contenido")})

        self.assertFalse(formulario.is_valid())

    def test_acepta_archivo_xlsx(self):
        formulario = FormularioArchivoPadron(files={"archivo": SimpleUploadedFile("padron.xlsx", b"contenido", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

        self.assertTrue(formulario.is_valid())

    def test_validar_archivo_xlsx_acepta_formato_excel(self):
        libro = Workbook()
        hoja = libro.active
        hoja.append(["DNI", "Tipo Documento", "Legajo", "Nombre", "Apellido", "Depto/Carrera", "Mail", "Sede", "TieneDiscapacidad", "Departamento Principal", "Nivel"])
        hoja.append(["40123456", "DNI", "2024001", "Juan", "Perez", "Sistemas", "juan.perez@frba.utn.edu.ar", "Campus", "Si", "Ingenieria", "1"])

        archivo = io.BytesIO()
        libro.save(archivo)
        archivo.seek(0)

        respuesta = FormularioArchivoPadron(files={"archivo": SimpleUploadedFile("padron.xlsx", archivo.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        self.assertTrue(respuesta.is_valid())

    def test_confirmar_importacion_xlsx_conserva_el_archivo(self):
        from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, EleccionClaustroTurno, EleccionSede
        from apps.padron.models import ImportacionPadron
        from apps.padron.services import confirmar_importacion
        from apps.parametros.models import Claustro, Departamento, Sede, Turno
        from django.contrib.auth import get_user_model
        from django.utils.timezone import make_aware

        ahora = make_aware(datetime(2026, 8, 3, 8))
        eleccion = Eleccion.objects.create(nombre="Eleccion XLSX", fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=8))
        sede = Sede.objects.create(nombre="Campus XLSX")
        turno = Turno.objects.create(nombre="Manana XLSX", hora_inicio=time(8), hora_fin=time(12))
        claustro = Claustro.objects.create(nombre="Estudiantes XLSX")
        departamento = Departamento.objects.create(nombre="Sistemas XLSX", codigo="KX")
        EleccionSede.objects.create(eleccion=eleccion, sede=sede)
        eleccion_claustro = EleccionClaustro.objects.create(eleccion=eleccion, claustro=claustro, maximo_votantes_por_mesa=20)
        EleccionClaustroTurno.objects.create(eleccion_claustro=eleccion_claustro, turno=turno)
        configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=eleccion_claustro, departamento=departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=configuracion, sede=sede)

        libro = Workbook()
        hoja = libro.active
        hoja.append(["DNI", "Tipo Documento", "Legajo", "Nombre", "Apellido", "Depto/Carrera", "Mail", "Sede"])
        hoja.append(["40123457", "DNI", "2024007", "Ana", "Perez", "KX", "ana.perez@frba.utn.edu.ar", "Campus XLSX"])
        contenido = io.BytesIO()
        libro.save(contenido)
        contenido.seek(0)
        bytes_archivo = contenido.getvalue()
        usuario = get_user_model().objects.create_user(username="xlsx-confirm", password="clave")
        importacion = ImportacionPadron.objects.create(
            eleccion=eleccion,
            eleccion_claustro=eleccion_claustro,
            archivo=SimpleUploadedFile("padron.xlsx", bytes_archivo),
            nombre_archivo="padron.xlsx",
            huella_archivo=__import__("hashlib").sha256(bytes_archivo).hexdigest(),
            usuario=usuario,
        )

        self.assertEqual(confirmar_importacion(importacion), 1)

class ProteccionEmisionQrTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion QR", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8))
        self.sede = Sede.objects.create(nombre="Campus")
        self.turno = Turno.objects.create(nombre="Mañana", hora_inicio=time(8), hora_fin=time(13))
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Estudiantes"),
            maximo_votantes_por_mesa=100,
        )
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.turno)
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="K"),
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=1, eleccion_claustro_departamento=self.configuracion,
            sede=self.sede, generada_automaticamente=True,
        )
        elector = Elector.objects.create(legajo="1001", dni="12345678", nombre="Ana Pérez")
        self.registro = RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion, sede=self.sede,
        )
        AsignacionMesa.objects.create(registro_padron=self.registro, mesa=self.mesa)

    def test_generar_qr_marca_emision_y_numero_de_mesa(self):
        with TemporaryDirectory() as directorio, patch.object(
            ComandoGenerarQr,
            "generar_qr",
            return_value=Image.new("RGB", (350, 350), "white"),
        ):
            call_command(
                "seed_voters",
                election_id=self.eleccion.pk,
                configuracion_departamento_id=self.configuracion.pk,
                output=Path(directorio),
            )

        self.registro.refresh_from_db()
        self.assertIsNotNone(self.registro.qr_generado_en)
        self.assertEqual(self.registro.numero_mesa_qr, 1)

    def test_no_regenera_mesas_despues_de_emitir_qr(self):
        self.registro.qr_generado_en = make_aware(datetime(2026, 8, 1, 10))
        self.registro.numero_mesa_qr = 1
        self.registro.save(update_fields=("qr_generado_en", "numero_mesa_qr"))

        with self.assertRaisesRegex(ValueError, "emitieron QR"):
            calcular_mesas_automaticas_eleccion(self.eleccion)

        self.assertTrue(Mesa.objects.filter(pk=self.mesa.pk).exists())

    def test_bloquea_cambio_directo_de_mesa_despues_de_emitir_qr(self):
        self.registro.qr_generado_en = make_aware(datetime(2026, 8, 1, 10))
        self.registro.numero_mesa_qr = 1
        self.registro.save(update_fields=("qr_generado_en", "numero_mesa_qr"))
        otra_mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )
        asignacion = self.registro.asignacion_mesa
        asignacion.mesa = otra_mesa

        with self.assertRaises(ValidationError):
            asignacion.save()

        self.mesa.numero = 3
        with self.assertRaises(ValidationError):
            self.mesa.save()

    def test_falla_de_archivos_no_marca_qr_como_emitido(self):
        with TemporaryDirectory() as directorio, patch.object(
            ComandoGenerarQr,
            "generar_qr",
            return_value=Image.new("RGB", (350, 350), "white"),
        ), patch.object(ComandoGenerarQr, "crear_hojas", side_effect=OSError("sin espacio")):
            with self.assertRaises(OSError):
                call_command(
                    "seed_voters",
                    election_id=self.eleccion.pk,
                    configuracion_departamento_id=self.configuracion.pk,
                    output=Path(directorio),
                )

        self.registro.refresh_from_db()
        self.assertIsNone(self.registro.qr_generado_en)
        self.assertIsNone(self.registro.numero_mesa_qr)


class PadronesVotacionTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Elección de prueba", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8))
        self.sede_campus = Sede.objects.create(nombre="Campus")
        self.sede_medrano = Sede.objects.create(nombre="Medrano")
        self.claustro = Claustro.objects.create(nombre="Docentes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro),
            departamento=self.departamento,
        )
        self.habilitacion_campus = EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede_campus)
        self.habilitacion_medrano = EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede_medrano)
        organo = OrganoElectivo.objects.create(nombre="Consejo")
        cargo = CargoElectivo.objects.create(organo=organo, nombre="Consejero", permite_filtrar_departamentos=True)
        self.puesto = PuestoEleccion.objects.create(
            puesto=cargo,
            eleccion_claustro=self.configuracion.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            cantidad_titulares=1,
        )
        elector = Elector.objects.create(dni="40123456", legajo="D001", nombre="Ada", apellido="Lovelace")
        self.registro = RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede_medrano,
            nivel="2",
        )

    def crear_padron(self, nombre="Docentes Sistemas"):
        padron = PadronVotacion.objects.create(eleccion_claustro=self.configuracion.eleccion_claustro, nombre=nombre)
        padron.puestos.add(self.puesto)
        grupo = GrupoInclusionPadronVotacion.objects.create(padron_votacion=padron)
        CondicionInclusionPadronVotacion.objects.create(grupo=grupo, campo="departamento", operador="igual", valor="K")
        ConfiguracionSedePadronVotacion.objects.create(
            padron_votacion=padron,
            eleccion_claustro_departamento=self.configuracion,
            sede_predeterminada=self.habilitacion_campus,
        )
        return padron

    def test_calculo_aplica_regla_ordenada_y_no_genera_mesa(self):
        padron = self.crear_padron()
        configuracion = padron.configuraciones_sede.get()
        ReglaAsignacionSede.objects.create(
            configuracion=configuracion,
            orden=1,
            campo="sede_donde_cursa",
            operador="igual",
            valor="Medrano",
            sede_destino=self.habilitacion_medrano,
        )

        cantidad = calcular_padrones_votacion(self.configuracion.eleccion_claustro)

        self.assertEqual(cantidad, 1)
        asignacion = padron.asignaciones.get()
        self.assertEqual(asignacion.sede_asignada, self.habilitacion_medrano)
        self.assertFalse(Mesa.objects.filter(eleccion=self.eleccion).exists())

    def test_rechaza_cargo_repetido_para_el_mismo_elector(self):
        self.crear_padron("Primer padrón")
        self.crear_padron("Segundo padrón")

        with self.assertRaisesMessage(ValueError, "mismo cargo"):
            calcular_padrones_votacion(self.configuracion.eleccion_claustro)

    def test_padron_sin_grupos_no_incluye_electores(self):
        padron = PadronVotacion.objects.create(eleccion_claustro=self.configuracion.eleccion_claustro, nombre="Sin condiciones")
        padron.puestos.add(self.puesto)
        ConfiguracionSedePadronVotacion.objects.create(
            padron_votacion=padron,
            eleccion_claustro_departamento=self.configuracion,
            sede_predeterminada=self.habilitacion_campus,
        )

        self.assertEqual(calcular_padrones_votacion(self.configuracion.eleccion_claustro), 0)
        self.assertFalse(padron.asignaciones.exists())


class AsignacionSedesClaustroTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Elección de prueba",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        self.campus = Sede.objects.create(nombre="Campus")
        self.medrano = Sede.objects.create(nombre="Medrano")
        self.lugano = Sede.objects.create(nombre="Lugano")
        claustro = Claustro.objects.create(nombre="Docentes")
        self.claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        self.departamento_a = Departamento.objects.create(nombre="Sistemas", codigo="K")
        self.departamento_b = Departamento.objects.create(nombre="Electrónica", codigo="E")
        self.alcance_a = self.crear_alcance(self.departamento_a, (self.campus, self.medrano))
        self.alcance_b = self.crear_alcance(self.departamento_b, (self.campus, self.lugano))
        self.registro_a = self.crear_registro("40123456", self.alcance_a, self.medrano)
        self.registro_b = self.crear_registro("40234567", self.alcance_b, self.campus)
        self.configuracion, _ = ConfiguracionSedesClaustro.objects.get_or_create(eleccion_claustro=self.claustro)

    def test_pantalla_unica_muestra_la_regla_de_sede_por_departamento(self):
        usuario = get_user_model().objects.create_user(username="junta", password="clave")
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.login(username="junta", password="clave")

        respuesta = self.client.get(reverse(
            "configurar-sedes-claustro",
            args=(self.eleccion.id, self.claustro.id),
        ))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "padron/configurar_sedes_claustro.html")
        self.assertContains(respuesta, "se omite para sus electores")
        self.assertContains(respuesta, "Lugano")
        self.assertContains(respuesta, "Todos los departamentos disponibles")
        self.assertContains(respuesta, 'class="checkbox-list rule-department-picker"')
        self.assertContains(respuesta, 'name="aplicar_a_todos"')
        self.assertContains(respuesta, 'name="alcances_especificos"')
        self.assertContains(respuesta, 'class="gestion-form-grid rule-condition-grid"')
        self.assertContains(respuesta, 'type="hidden" name="orden"')
        self.assertEqual(
            respuesta.context["formulario"].fields["alcances_especificos"].widget.__class__.__name__,
            "CheckboxSelectMultiple",
        )

    def test_reglas_se_pueden_reordenar_hacia_arriba_y_abajo(self):
        usuario = get_user_model().objects.create_user(username="junta-reorden-reglas", password="clave")
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        regla_primera = self.crear_regla(1, "nivel", "1", self.medrano)
        regla_segunda = self.crear_regla(2, "nivel", "2", self.campus)
        self.client.force_login(usuario)
        url = reverse("configurar-sedes-claustro", args=(self.eleccion.id, self.claustro.id))
        pantalla = self.client.get(url)
        self.assertContains(pantalla, "↑ Subir")
        self.assertContains(pantalla, "↓ Bajar")
        self.assertContains(pantalla, "Eliminar")

        respuesta = self.client.post(url, {
            "accion": "mover-regla-subir",
            "regla_id": regla_segunda.id,
        })

        self.assertRedirects(respuesta, url)
        regla_primera.refresh_from_db()
        regla_segunda.refresh_from_db()
        self.assertEqual(regla_segunda.orden, 1)
        self.assertEqual(regla_primera.orden, 2)

        respuesta = self.client.post(url, {
            "accion": "mover-regla-bajar",
            "regla_id": regla_segunda.id,
        })

        self.assertRedirects(respuesta, url)
        regla_primera.refresh_from_db()
        regla_segunda.refresh_from_db()
        self.assertEqual(regla_primera.orden, 1)
        self.assertEqual(regla_segunda.orden, 2)

    def test_agregar_regla_recalcula_asignaciones_y_muestra_resumen(self):
        usuario = get_user_model().objects.create_user(username="junta-regla-automatica")
        AsignacionRol.objects.create(usuario=usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion)
        self.client.force_login(usuario)
        url = reverse("configurar-sedes-claustro", args=(self.eleccion.id, self.claustro.id))

        respuesta = self.client.post(url, {
            "orden": 1,
            "campo": "nivel",
            "operador": "igual",
            "valor": "2",
            "sede_destino": self.campus.pk,
            "aplicar_a_todos": "on",
        })

        self.assertRedirects(respuesta, url, fetch_redirect_response=False)
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=self.registro_a).sede, self.campus)
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=self.registro_b).sede, self.campus)
        pantalla = self.client.get(url)
        self.assertContains(pantalla, "<strong>2</strong> electores se asignaron a la sede <strong>Campus</strong>")
        self.assertNotContains(pantalla, 'value="calcular"')

    def test_resultado_de_asignaciones_se_pagina_de_a_10_sin_alterar_totales(self):
        usuario = get_user_model().objects.create_user(username="junta-paginacion", password="clave")
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        for indice in range(30):
            elector = Elector.objects.create(
                dni=f"41{indice:06d}",
                legajo=f"P{indice:05d}",
                nombre=f"Elector {indice}",
            )
            registro = RegistroPadron.objects.create(
                elector=elector,
                eleccion=self.eleccion,
                eleccion_claustro_departamento=self.alcance_a,
                sede=self.campus,
                nivel="2",
            )
            AsignacionSedePadron.objects.create(
                registro_padron=registro,
                sede=self.campus,
                estado=AsignacionSedePadron.Estado.ASIGNADA,
            )
        for indice in range(2):
            elector = Elector.objects.create(
                dni=f"42{indice:06d}",
                legajo=f"Q{indice:05d}",
                nombre=f"Pendiente {indice}",
            )
            registro = RegistroPadron.objects.create(
                elector=elector,
                eleccion=self.eleccion,
                eleccion_claustro_departamento=self.alcance_a,
                sede=self.campus,
                nivel="2",
            )
            AsignacionSedePadron.objects.create(
                registro_padron=registro,
                sede=None,
                estado=AsignacionSedePadron.Estado.PENDIENTE,
            )

        self.client.force_login(usuario)
        url = reverse("configurar-sedes-claustro", args=(self.eleccion.id, self.claustro.id))

        primera_pagina = self.client.get(url)
        segunda_pagina = self.client.get(url, {"pagina": 4})
        solo_pendientes = self.client.get(url, {"estado": "pendiente"})

        self.assertEqual(primera_pagina.context["asignaciones"].paginator.per_page, 10)
        self.assertEqual(len(primera_pagina.context["asignaciones"]), 10)
        self.assertEqual(len(segunda_pagina.context["asignaciones"]), 2)
        resumen = primera_pagina.context["resumen_asignaciones"]
        self.assertIn(30, [item["cantidad"] for item in resumen])
        self.assertContains(primera_pagina, "<strong>30</strong> electores se asignaron a la sede")
        self.assertContains(primera_pagina, "Campus")
        self.assertEqual(primera_pagina.context["cantidad_asignadas"], 30)
        self.assertEqual(primera_pagina.context["cantidad_pendientes"], 2)
        self.assertEqual(solo_pendientes.context["asignaciones"].paginator.count, 2)
        self.assertTrue(all(
            item.estado == AsignacionSedePadron.Estado.PENDIENTE
            for item in solo_pendientes.context["asignaciones"]
        ))
        self.assertContains(primera_pagina, "Ver pendientes")
        self.assertContains(primera_pagina, "32 registros · Página 1 de 4")
        self.assertContains(primera_pagina, 'aria-label="Ir a la página 2"')
        self.assertContains(segunda_pagina, "Página 4 de 4")

    def crear_alcance(self, departamento, sedes):
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.claustro,
            departamento=departamento,
        )
        for sede in sedes:
            EleccionClaustroDepartamentoSede.objects.create(
                eleccion_claustro_departamento=alcance,
                sede=sede,
            )
        return alcance

    def crear_registro(self, dni, alcance, sede_cursa):
        elector = Elector.objects.create(dni=dni, legajo=f"L{dni}", nombre="Ada", apellido="Lovelace")
        return RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=alcance,
            sede=sede_cursa,
            nivel="2",
        )

    def crear_regla(self, orden, campo, valor, destino, *, operador="igual", todos=True, alcances=()):
        regla = ReglaSedeClaustro.objects.create(
            configuracion=self.configuracion,
            orden=orden,
            campo=campo,
            operador=operador,
            valor=valor,
            sede_destino=destino,
            aplicar_a_todos=todos,
        )
        if alcances:
            regla.alcances_especificos.set(alcances)
        return regla

    def test_operadores_validos_se_ajustan_al_tipo_de_campo(self):
        datos_base = {
            "orden": 1,
            "valor": "3",
            "sede_destino": self.medrano.pk,
            "aplicar_a_todos": "on",
        }

        formulario_numerico = FormularioReglaSedeClaustro(
            data={**datos_base, "campo": "nivel", "operador": "menor_igual"},
            eleccion_claustro=self.claustro,
            configuracion=self.configuracion,
        )
        self.assertTrue(formulario_numerico.is_valid(), formulario_numerico.errors)

        formulario_texto = FormularioReglaSedeClaustro(
            data={**datos_base, "campo": "sede_donde_cursa", "operador": "en"},
            eleccion_claustro=self.claustro,
            configuracion=self.configuracion,
        )
        self.assertTrue(formulario_texto.is_valid(), formulario_texto.errors)

        formulario_numerico_con_pertenencia = FormularioReglaSedeClaustro(
            data={**datos_base, "campo": "nivel", "operador": "en"},
            eleccion_claustro=self.claustro,
            configuracion=self.configuracion,
        )
        self.assertFalse(formulario_numerico_con_pertenencia.is_valid())
        self.assertIn("operador", formulario_numerico_con_pertenencia.errors)

    def test_salta_destino_no_habilitado_y_continua_con_la_siguiente_regla(self):
        regla_medrano = self.crear_regla(1, "nivel", "2", self.medrano)
        regla_campus = self.crear_regla(2, "sede_donde_cursa", "Campus", self.campus)

        resultado = calcular_asignaciones_sede_claustro(self.claustro)

        self.assertEqual(resultado, {"asignadas": 2, "pendientes": 0})
        asignacion_a = AsignacionSedePadron.objects.get(registro_padron=self.registro_a)
        asignacion_b = AsignacionSedePadron.objects.get(registro_padron=self.registro_b)
        self.assertEqual(asignacion_a.sede, self.medrano)
        self.assertEqual(asignacion_a.regla_aplicada, regla_medrano)
        self.assertEqual(asignacion_b.sede, self.campus)
        self.assertEqual(asignacion_b.regla_aplicada, regla_campus)
        self.assertFalse(Mesa.objects.filter(eleccion=self.eleccion).exists())

    def test_una_sede_se_asigna_automaticamente_y_multi_sede_sin_regla_queda_pendiente(self):
        self.alcance_a.sedes_habilitadas.filter(sede=self.medrano).delete()
        resultado = calcular_asignaciones_sede_claustro(self.claustro)

        self.assertEqual(resultado, {"asignadas": 1, "pendientes": 1})
        automatica = AsignacionSedePadron.objects.get(registro_padron=self.registro_a)
        pendiente = AsignacionSedePadron.objects.get(registro_padron=self.registro_b)
        self.assertEqual(automatica.sede, self.campus)
        self.assertIsNone(automatica.regla_aplicada)
        self.assertEqual(pendiente.estado, AsignacionSedePadron.Estado.PENDIENTE)
        self.assertIsNone(pendiente.sede)

    def test_regla_limitada_se_omite_para_alcances_no_seleccionados(self):
        regla = self.crear_regla(1, "nivel", "2", self.medrano, todos=False, alcances=(self.alcance_a,))
        self.crear_regla(2, "sede_donde_cursa", "Campus", self.campus)

        calcular_asignaciones_sede_claustro(self.claustro)

        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=self.registro_a).regla_aplicada, regla)
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=self.registro_b).sede, self.campus)


class EliminarPadronClaustroTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Elección de prueba",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            estado=Eleccion.Estado.EN_PREPARACION,
        )
        self.sede = Sede.objects.create(nombre="Campus")
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        claustro = Claustro.objects.create(nombre="Docentes")
        self.claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        self.alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.claustro,
            departamento=departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=self.alcance,
            sede=self.sede,
        )
        self.elector = Elector.objects.create(
            dni="40123456",
            legajo="D001",
            nombre="Ada",
            apellido="Lovelace",
        )
        self.registro = RegistroPadron.objects.create(
            elector=self.elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.alcance,
        )
        self.usuario = get_user_model().objects.create_user(username="admin-padron", password="clave")
        self.mesa_automatica = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.alcance,
            sede=self.sede,
            generada_automaticamente=True,
        )
        self.asignacion_mesa = AsignacionMesa.objects.create(
            registro_padron=self.registro,
            mesa=self.mesa_automatica,
        )
        self.mesa_manual = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=2,
            eleccion_claustro_departamento=self.alcance,
            sede=self.sede,
            generada_automaticamente=False,
        )
        self.importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.claustro,
            archivo="padrones/historico.csv",
            nombre_archivo="historico.csv",
            huella_archivo="huella",
            estado=ImportacionPadron.Estado.CONFIRMADA,
            usuario=self.usuario,
        )

    def test_vacia_registros_libera_identidades_huerfanas_y_conserva_historial_y_mesas_manuales(self):
        importacion_previa = ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.claustro,
            archivo="padrones/previa.csv",
            nombre_archivo="previa.csv",
            huella_archivo="previa",
            estado=ImportacionPadron.Estado.PREVISUALIZADA,
            usuario=self.usuario,
        )

        resultado = eliminar_padron_claustro(self.claustro, self.usuario)

        self.assertEqual(resultado["cantidad_registros"], 1)
        self.assertFalse(RegistroPadron.objects.filter(pk=self.registro.pk).exists())
        self.assertFalse(Elector.objects.filter(pk=self.elector.pk).exists())
        elector_reimportado = Elector.objects.create(
            dni="40123456",
            legajo="D001",
            nombre="Ada",
            apellido="Lovelace",
        )
        self.assertEqual(elector_reimportado.dni, "40123456")
        self.importacion.refresh_from_db()
        importacion_previa.refresh_from_db()
        self.assertEqual(self.importacion.estado, ImportacionPadron.Estado.PADRON_ELIMINADO)
        self.assertEqual(self.importacion.archivo.name, "padrones/historico.csv")
        self.assertEqual(importacion_previa.estado, ImportacionPadron.Estado.PREVISUALIZADA)
        self.assertFalse(AsignacionMesa.objects.filter(pk=self.asignacion_mesa.pk).exists())
        self.assertFalse(Mesa.objects.filter(pk=self.mesa_automatica.pk).exists())
        self.assertTrue(Mesa.objects.filter(pk=self.mesa_manual.pk).exists())

    def test_conserva_elector_vinculado_a_un_padron_de_otra_eleccion(self):
        inicio_anterior = make_aware(datetime(2025, 8, 3, 8))
        eleccion_anterior = Eleccion.objects.create(
            nombre="Elección anterior",
            fecha_inicio=inicio_anterior,
            fecha_fin=inicio_anterior + timedelta(hours=8),
            estado=Eleccion.Estado.FINALIZADA,
        )
        claustro_anterior = EleccionClaustro.objects.create(
            eleccion=eleccion_anterior,
            claustro=self.claustro.claustro,
        )
        alcance_anterior = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_anterior,
            departamento=self.alcance.departamento,
        )
        RegistroPadron.objects.create(
            elector=self.elector,
            eleccion=eleccion_anterior,
            eleccion_claustro_departamento=alcance_anterior,
        )
        ImportacionPadron.objects.create(
            eleccion=eleccion_anterior,
            eleccion_claustro=claustro_anterior,
            archivo="padrones/anterior.csv",
            nombre_archivo="anterior.csv",
            huella_archivo="anterior",
            estado=ImportacionPadron.Estado.CONFIRMADA,
            usuario=self.usuario,
        )

        eliminar_padron_claustro(self.claustro, self.usuario)

        self.assertTrue(Elector.objects.filter(pk=self.elector.pk).exists())
        self.assertTrue(RegistroPadron.objects.filter(elector=self.elector, eleccion=eleccion_anterior).exists())

    def test_no_elimina_con_eleccion_publicada(self):
        self.eleccion.estado = Eleccion.Estado.PUBLICADA
        self.eleccion.save(update_fields=("estado",))

        with self.assertRaisesMessage(ValueError, "ya no está en preparación"):
            eliminar_padron_claustro(self.claustro, self.usuario)

        self.assertTrue(RegistroPadron.objects.filter(pk=self.registro.pk).exists())

    def test_no_elimina_si_hay_qr_emitido(self):
        self.registro.qr_generado_en = make_aware(datetime(2026, 8, 4, 12))
        self.registro.save(update_fields=("qr_generado_en",))
        EmisionPadronImprimible.objects.create(
            eleccion_claustro=self.claustro,
            estado=EmisionPadronImprimible.Estado.VIGENTE,
            emitida_por=self.usuario,
        )

        with self.assertRaisesMessage(ValueError, "QR emitidos"):
            eliminar_padron_claustro(self.claustro, self.usuario)

        self.assertTrue(RegistroPadron.objects.filter(pk=self.registro.pk).exists())
        self.assertTrue(AsignacionMesa.objects.filter(pk=self.asignacion_mesa.pk).exists())

    def test_no_elimina_si_hay_participacion_registrada(self):
        from apps.asistencia.models import RegistroParticipacion

        RegistroParticipacion.objects.create(
            registro_padron=self.registro,
            mesa=self.mesa_automatica,
            registrada_por=self.usuario,
            metodo=RegistroParticipacion.Metodo.MANUAL,
        )

        with self.assertRaisesMessage(ValueError, "participaciones registradas"):
            eliminar_padron_claustro(self.claustro, self.usuario)

        self.assertTrue(RegistroPadron.objects.filter(pk=self.registro.pk).exists())

    def test_pantalla_confirma_y_ejecuta_el_vaciado_con_permiso_de_administrador(self):
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(self.usuario)
        url = reverse("eliminar-padron-claustro", args=(self.eleccion.id, self.claustro.id))

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "¿Querés vaciar el padrón de este claustro?")
        self.assertContains(respuesta, "historial de importaciones")

        respuesta = self.client.post(url)

        self.assertRedirects(
            respuesta,
            reverse("previsualizar-padron", args=(self.eleccion.id, self.claustro.id)),
        )
        self.assertFalse(RegistroPadron.objects.filter(pk=self.registro.pk).exists())


class SolicitudCambioSedeTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Elección cambio de sede",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            estado=Eleccion.Estado.PUBLICADA,
            fecha_cierre_solicitudes_cambio_sede=inicio.date() + timedelta(days=2),
            habilitada=True,
        )
        self.sede_origen = Sede.objects.create(nombre="Campus")
        self.sede_destino = Sede.objects.create(nombre="Medrano")
        claustro = Claustro.objects.create(nombre="Estudiantes")
        turno = Turno.objects.create(nombre="Mañana", hora_inicio=time(8), hora_fin=time(12))
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede_origen)
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede_destino)
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=claustro,
            maximo_votantes_por_mesa=100,
        )
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=turno)
        EleccionClaustroSede.objects.create(eleccion_claustro=self.eleccion_claustro, sede=self.sede_origen)
        EleccionClaustroSede.objects.create(eleccion_claustro=self.eleccion_claustro, sede=self.sede_destino)
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=self.sede_origen)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=self.sede_destino)
        elector = Elector.objects.create(dni="40111222", legajo="L40111222", nombre="Ada", apellido="Lovelace")
        self.registro = RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=alcance,
            sede=self.sede_origen,
        )
        self.mesa_origen = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=alcance,
            sede=self.sede_origen,
        )
        AsignacionMesa.objects.create(registro_padron=self.registro, mesa=self.mesa_origen)
        self.usuario = get_user_model().objects.create_user(username="admin-cambio-sede")
        self.usuario_elector = get_user_model().objects.create_user(username="elector-cambio-sede")
        PerfilUsuario.objects.create(usuario=self.usuario_elector, elector=self.registro.elector)

    def test_aprobar_solicitud_cambia_sede_y_reasigna_mesa(self):
        solicitud = SolicitudCambioSede.objects.create(
            registro_padron=self.registro,
            sede_origen=self.sede_origen,
            sede_destino=self.sede_destino,
        )

        resolver_solicitud_cambio_sede(solicitud, SolicitudCambioSede.Estado.APROBADA, self.usuario)

        self.registro.refresh_from_db()
        solicitud.refresh_from_db()
        self.assertEqual(self.registro.sede, self.sede_destino)
        self.assertEqual(solicitud.estado, SolicitudCambioSede.Estado.APROBADA)
        self.assertEqual(self.registro.asignacion_mesa.mesa.sede, self.sede_destino)

    def test_elector_solo_puede_registrar_una_solicitud_por_eleccion(self):
        self.eleccion.fecha_cierre_solicitudes_cambio_sede = timezone.localdate() + timedelta(days=2)
        self.eleccion.save(update_fields=("fecha_cierre_solicitudes_cambio_sede",))
        self.client.force_login(self.usuario_elector)
        url = reverse("mis-solicitudes-cambio-sede")

        primera = self.client.post(
            url,
            {"sede_destino": self.sede_destino.id, "observacion": "Primera solicitud"},
            follow=True,
        )
        segunda = self.client.post(
            url,
            {"sede_destino": self.sede_destino.id, "observacion": "Segunda solicitud"},
            follow=True,
        )

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(
            SolicitudCambioSede.objects.filter(registro_padron=self.registro).count(),
            1,
        )
        self.assertContains(segunda, "Ya registraste una solicitud de cambio de sede para esta elección.")

    def test_mis_solicitudes_oculta_formulario_cuando_ya_existe_una_solicitud(self):
        self.eleccion.fecha_cierre_solicitudes_cambio_sede = timezone.localdate() + timedelta(days=2)
        self.eleccion.save(update_fields=("fecha_cierre_solicitudes_cambio_sede",))
        SolicitudCambioSede.objects.create(
            registro_padron=self.registro,
            sede_origen=self.sede_origen,
            sede_destino=self.sede_destino,
        )
        self.client.force_login(self.usuario_elector)

        respuesta = self.client.get(reverse("mis-solicitudes-cambio-sede"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya registraste una solicitud de cambio de sede para esta elección.")
        self.assertNotContains(respuesta, "Sede solicitada")

    def test_aprobar_sin_agregar_mesas_rechaza_si_no_hay_mesa_disponible(self):
        solicitud = SolicitudCambioSede.objects.create(
            registro_padron=self.registro,
            sede_origen=self.sede_origen,
            sede_destino=self.sede_destino,
        )
        Mesa.objects.filter(eleccion=self.eleccion, sede=self.sede_destino).delete()

        resultado = resolver_solicitudes_pendientes(
            self.eleccion,
            usuario=self.usuario,
            accion="aprobar_sin_agregar_mesas",
        )

        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudCambioSede.Estado.RECHAZADA)
        self.assertEqual(resultado["rechazadas"], 1)

    def test_aprobar_con_maximo_total_deja_pendientes_las_que_requieren_mesas_excedentes(self):
        self.eleccion_claustro.maximo_votantes_por_mesa = 1
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        segunda_persona = Elector.objects.create(
            dni="40111223",
            legajo="L40111223",
            nombre="Grace",
            apellido="Hopper",
        )
        segundo_registro = RegistroPadron.objects.create(
            elector=segunda_persona,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.registro.eleccion_claustro_departamento,
            sede=self.sede_origen,
        )
        solicitudes = [
            SolicitudCambioSede.objects.create(
                registro_padron=registro,
                sede_origen=self.sede_origen,
                sede_destino=self.sede_destino,
            )
            for registro in (self.registro, segundo_registro)
        ]

        resultado = resolver_solicitudes_pendientes(
            self.eleccion,
            usuario=self.usuario,
            accion="aprobar_con_maximo_mesas",
            maximo_mesas_nuevas=1,
        )

        solicitudes[0].refresh_from_db()
        solicitudes[1].refresh_from_db()
        self.assertEqual(solicitudes[0].estado, SolicitudCambioSede.Estado.APROBADA)
        self.assertEqual(solicitudes[1].estado, SolicitudCambioSede.Estado.PENDIENTE)
        self.assertEqual(resultado["aprobadas"], 1)
        self.assertEqual(resultado["pendientes"], 1)
        self.assertEqual(Mesa.objects.filter(eleccion=self.eleccion, sede=self.sede_destino).count(), 1)

    def test_maximo_total_de_mesas_rechaza_entrada_negativa(self):
        with self.assertRaisesMessage(ValueError, "no puede ser negativo"):
            resolver_solicitudes_pendientes(
                self.eleccion,
                usuario=self.usuario,
                accion="aprobar_con_maximo_mesas",
                maximo_mesas_nuevas=-1,
            )

    def test_gestion_muestra_cantidad_actual_de_mesas_por_sede(self):
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        SolicitudCambioSede.objects.create(
            registro_padron=self.registro,
            sede_origen=self.sede_origen,
            sede_destino=self.sede_destino,
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.id,))
        )

        self.assertEqual(respuesta.status_code, 200)
        resumen = {
            item["sede_nombre"]: item["mesas_actuales"]
            for item in respuesta.context["resumen_mesas_por_sede"]
        }
        self.assertEqual(resumen, {"Campus": 1, "Medrano": 0})
        self.assertEqual(respuesta.context["mesas_nuevas_si_aceptar_todas"], 1)
        self.assertContains(respuesta, "Aceptar con límite de mesas nuevas")
        self.assertNotContains(respuesta, "Aceptar con límite por sede")
        self.assertContains(respuesta, "id=\"dialogo-limite-mesas\"")
        self.assertContains(respuesta, "Mesas actuales por sede")
        self.assertContains(respuesta, "resolucion-masiva-layout")

    def test_boton_limite_de_mesas_se_muestra_deshabilitado_sin_solicitudes_pendientes(self):
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.id,))
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            '<button class="button secondary" type="button" id="abrir-dialogo-limite-mesas" '
            'aria-haspopup="dialog" aria-controls="dialogo-limite-mesas" '
            'disabled aria-describedby="sin-solicitudes-pendientes">Aceptar con límite de mesas nuevas</button>',
            html=True,
        )
        self.assertContains(respuesta, "No hay solicitudes pendientes para resolver.")

    def test_resolucion_con_maximo_no_acepta_un_valor_vacio(self):
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        solicitud = SolicitudCambioSede.objects.create(
            registro_padron=self.registro,
            sede_origen=self.sede_origen,
            sede_destino=self.sede_destino,
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.id,)),
            {"accion": "aprobar_con_maximo_mesas", "maximo_mesas_nuevas": ""},
        )

        solicitud.refresh_from_db()
        self.assertRedirects(
            respuesta,
            reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.id,)),
            fetch_redirect_response=False,
        )
        self.assertEqual(solicitud.estado, SolicitudCambioSede.Estado.PENDIENTE)
        self.assertFalse(Mesa.objects.filter(eleccion=self.eleccion, sede=self.sede_destino).exists())
