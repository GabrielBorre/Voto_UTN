from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import (
    Eleccion, EleccionClaustro, EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede, EleccionClaustroSede, EleccionClaustroTurno, EleccionSede,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import (
    AsignacionSedePadron, ConfiguracionSedesClaustro, Elector, RegistroPadron, ReglaSedeClaustro,
)
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.usuarios.models import AsignacionRol


class ReglasSedeAtomicidadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        hoy = timezone.localdate()
        cls.eleccion = Eleccion.objects.create(
            nombre="Reglas protegidas", fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=30),
        )
        cls.usuario = get_user_model().objects.create_user(username="junta-reglas-protegidas")
        AsignacionRol.objects.create(
            usuario=cls.usuario, eleccion=cls.eleccion, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        )
        cls.claustro = EleccionClaustro.objects.create(
            eleccion=cls.eleccion, claustro=Claustro.objects.create(nombre="Estudiantes"),
            maximo_votantes_por_mesa=60,
        )
        cls.campus = Sede.objects.create(nombre="Campus")
        cls.medrano = Sede.objects.create(nombre="Medrano")
        for sede in (cls.campus, cls.medrano):
            EleccionSede.objects.create(eleccion=cls.eleccion, sede=sede)
            EleccionClaustroSede.objects.create(eleccion_claustro=cls.claustro, sede=sede)
        turno = Turno.objects.create(nombre="Mañana", hora_inicio=time(8), hora_fin=time(12))
        EleccionClaustroTurno.objects.create(eleccion_claustro=cls.claustro, turno=turno)
        alcances = [EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=cls.claustro,
            departamento=Departamento.objects.create(codigo=codigo, nombre=f"Departamento {codigo}"),
        ) for codigo in ("K", "I")]
        for alcance in alcances:
            for sede in (cls.campus, cls.medrano):
                EleccionClaustroDepartamentoSede.objects.create(
                    eleccion_claustro_departamento=alcance, sede=sede,
                )
        cls.configuracion = ConfiguracionSedesClaustro.objects.create(eleccion_claustro=cls.claustro)
        cls.regla_campus = ReglaSedeClaustro.objects.create(
            configuracion=cls.configuracion, orden=1, campo="nivel", operador="mayor_igual",
            valor="1", sede_destino=cls.campus, aplicar_a_todos=True,
        )
        cls.regla_medrano = ReglaSedeClaustro.objects.create(
            configuracion=cls.configuracion, orden=2, campo="nivel", operador="mayor_igual",
            valor="1", sede_destino=cls.medrano, aplicar_a_todos=True,
        )
        elector = Elector.objects.create(dni="40333333", legajo="L300", nombre="Persona protegida")
        for numero, alcance in enumerate(alcances, start=1):
            registro = RegistroPadron.objects.create(
                eleccion=cls.eleccion, elector=elector, eleccion_claustro_departamento=alcance,
                es_principal=numero == 1, nivel="2",
            )
            AsignacionSedePadron.objects.create(
                registro_padron=registro, sede=cls.campus, estado=AsignacionSedePadron.Estado.ASIGNADA,
                regla_aplicada=cls.regla_campus,
            )
            mesa = Mesa.objects.create(
                eleccion=cls.eleccion, numero=numero, eleccion_claustro_departamento=alcance,
                sede=cls.campus, es_especial=numero == 2,
            )
            AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa)
            if numero == 2:
                AsignacionAutoridad.objects.create(
                    registro_padron=registro, mesa=mesa, turno=turno, asignada_por=cls.usuario,
                )

    def setUp(self):
        self.client.force_login(self.usuario)
        self.client.raise_request_exception = False
        self.url = reverse("configurar-sedes-claustro", args=(self.eleccion.pk, self.claustro.pk))

    def estado(self):
        return {
            "reglas": list(ReglaSedeClaustro.objects.filter(configuracion=self.configuracion).order_by("pk").values()),
            "sedes": list(AsignacionSedePadron.objects.order_by("pk").values()),
            "mesas": list(Mesa.objects.order_by("pk").values()),
            "asignaciones": list(AsignacionMesa.objects.order_by("pk").values()),
            "autoridades": list(AsignacionAutoridad.objects.order_by("pk").values()),
        }

    def comprobar_rechazo_sin_cambios(self, datos):
        anterior = self.estado()
        respuesta = self.client.post(self.url, datos)
        self.assertRedirects(respuesta, self.url, fetch_redirect_response=False)
        self.assertEqual(self.estado(), anterior)
        pantalla = self.client.get(self.url)
        self.assertContains(pantalla, "No se aplicó el cambio de regla.")
        self.assertContains(pantalla, "Una sede protegida del registro adicional no coincide con la sede principal.")
        self.assertNotContains(pantalla, "La regla se eliminó.")

    def test_eliminar_regla_protegida_conserva_regla_y_referencias(self):
        self.comprobar_rechazo_sin_cambios({"accion": "eliminar-regla", "regla_id": self.regla_campus.pk})

    def test_reordenar_regla_protegida_conserva_las_prioridades(self):
        self.comprobar_rechazo_sin_cambios({"accion": "mover-regla-subir", "regla_id": self.regla_medrano.pk})

    def test_agregar_regla_incompatible_no_deja_una_regla_guardada(self):
        self.configuracion.reglas.all().delete()
        self.comprobar_rechazo_sin_cambios({
            "orden": 1, "campo": "nivel", "operador": "mayor_igual", "valor": "1",
            "sede_destino": self.medrano.pk, "aplicar_a_todos": "on",
        })
