import re
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import (
    Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede,
    EleccionClaustroSede, EleccionClaustroTurno, EleccionSede,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import AsignacionSedePadron, Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.partidos.models import Candidato, CargoElectivo, ListaCandidatos, OrganoElectivo, ParticipacionPartido, PuestoEleccion


class ResumenPreparacionClaustrosTests(TestCase):
    def setUp(self):
        hoy = timezone.localdate()
        self.eleccion = Eleccion.objects.create(nombre="Cuatro claustros", fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=30))
        self.usuario = get_user_model().objects.create_superuser(username="junta-indicadores", email="junta@example.test")
        self.client.force_login(self.usuario)
        self.url = reverse("configurar-eleccion", args=(self.eleccion.pk,))
        self.sede = Sede.objects.create(nombre="Campus")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        self.turno = Turno.objects.create(nombre="Mañana", hora_inicio=time(8), hora_fin=time(12))
        self.claustros = []
        self.alcances = {}
        self.datos = {}
        organo = OrganoElectivo.objects.create(nombre="Consejo")
        self.cargo = CargoElectivo.objects.create(organo=organo, nombre="Representante")
        for indice, nombre in enumerate(("Estudiantes", "Docentes", "Graduados", "No docentes"), start=1):
            parametro = Claustro.objects.create(nombre=nombre)
            self.cargo.claustros_habilitados.add(parametro)
            claustro = EleccionClaustro.objects.create(
                eleccion=self.eleccion, claustro=parametro, fecha_votacion=hoy, maximo_votantes_por_mesa=60,
            )
            self.claustros.append(claustro)
            EleccionClaustroSede.objects.create(eleccion_claustro=claustro, sede=self.sede)
            alcance = EleccionClaustroDepartamento.objects.create(
                eleccion_claustro=claustro,
                departamento=Departamento.objects.create(codigo=f"D{indice}", nombre=f"Departamento {indice}"),
            )
            self.alcances[claustro.pk] = alcance
            EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=self.sede)

    def completar(self, claustro):
        numero = self.claustros.index(claustro) + 1
        alcance = self.alcances[claustro.pk]
        mesa = Mesa.objects.create(eleccion=self.eleccion, numero=numero, sede=self.sede, eleccion_claustro_departamento=alcance)
        EleccionClaustroTurno.objects.create(eleccion_claustro=claustro, turno=self.turno, minimo_titulares_por_mesa=1, titulares_por_mesa=3)
        registros = []
        for posicion in (1, 2):
            elector = Elector.objects.create(dni=f"40{numero:04d}{posicion:02d}", legajo=f"L{numero}{posicion}", nombre="Persona", apellido=f"{numero} {posicion}")
            registro = RegistroPadron.objects.create(eleccion=self.eleccion, elector=elector, eleccion_claustro_departamento=alcance)
            AsignacionSedePadron.objects.create(registro_padron=registro, sede=self.sede, estado="asignada")
            AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa)
            registros.append(registro)
        autoridad = AsignacionAutoridad.objects.create(registro_padron=registros[0], mesa=mesa, turno=self.turno, asignada_por=self.usuario)
        puesto = PuestoEleccion.objects.create(puesto=self.cargo, eleccion_claustro=claustro, cantidad_titulares=3, cantidad_suplentes=3)
        presentacion = ParticipacionPartido.objects.create(eleccion=self.eleccion, eleccion_claustro=claustro, numero_lista=str(numero), nombre_lista=f"Lista {numero}")
        lista = ListaCandidatos.objects.create(participacion=presentacion, eleccion_claustro=claustro, puesto_eleccion=puesto, nombre=f"Lista {numero}")
        candidato = Candidato.objects.create(lista=lista, elector=registros[1].elector, nombre="Persona candidata", dni=registros[1].elector.dni, cargo=self.cargo.nombre, tipo="titular", orden=1)
        self.datos[claustro.pk] = dict(mesa=mesa, registros=registros, autoridad=autoridad, puesto=puesto, presentacion=presentacion, lista=lista, candidato=candidato)

    def completar_todos(self):
        for claustro in self.claustros:
            self.completar(claustro)

    def comprobar(self, pendientes):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        tarjetas = dict(re.findall(r'<article class="option"><h2>(.*?)</h2>(.*?)</article>', respuesta.content.decode(), re.S))
        for nombre in ("Autoridades de mesa", "Mesas", "Puestos, listas y candidaturas"):
            with self.subTest(tarjeta=nombre):
                self.assertIn('class="pill warn"' if nombre in pendientes else 'class="pill ok"', tarjetas[nombre])
        return respuesta

    def test_un_claustro_completo_no_oculta_los_tres_vacios(self):
        self.completar(self.claustros[0])
        self.comprobar({"Autoridades de mesa", "Mesas", "Puestos, listas y candidaturas"})

    def test_todos_vacios_siguen_pendientes(self):
        self.comprobar({"Autoridades de mesa", "Mesas", "Puestos, listas y candidaturas"})

    def test_todos_listos_con_minimo_de_autoridades_y_listas_sin_completar_cupos(self):
        self.completar_todos()
        respuesta = self.comprobar(set())
        self.assertContains(respuesta, "4 de 4 claustros listos", count=3)

    def test_agregar_claustro_vacio_vuelve_a_pendiente(self):
        self.completar_todos()
        EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Nuevo claustro"))
        respuesta = self.comprobar({"Autoridades de mesa", "Mesas", "Puestos, listas y candidaturas"})
        self.assertContains(respuesta, "Nuevo claustro")

    def test_sin_mesas_en_un_claustro_autoridades_no_esta_lista(self):
        self.completar_todos()
        mesa = self.datos[self.claustros[1].pk]["mesa"]
        AsignacionMesa.objects.filter(mesa=mesa).delete()
        AsignacionAutoridad.objects.filter(mesa=mesa).delete()
        mesa.delete()
        respuesta = self.comprobar({"Autoridades de mesa", "Mesas"})
        self.assertContains(respuesta, "Falta generar las mesas")

    def test_mesa_existente_con_registro_sin_asignar_sigue_pendiente(self):
        self.completar_todos()
        registro = self.datos[self.claustros[1].pk]["registros"][1]
        AsignacionMesa.objects.filter(registro_padron=registro).delete()
        self.comprobar({"Autoridades de mesa", "Mesas"})

    def test_sede_electoral_sin_resolver_no_se_oculta_por_tener_mesa(self):
        self.completar_todos()
        registro = self.datos[self.claustros[1].pk]["registros"][1]
        AsignacionSedePadron.objects.filter(registro_padron=registro).update(sede=None, estado="pendiente")
        self.comprobar({"Autoridades de mesa", "Mesas"})

    def test_padron_inactivo_no_cuenta_como_cargado(self):
        self.completar_todos()
        RegistroPadron.objects.filter(eleccion_claustro_departamento=self.alcances[self.claustros[1].pk]).update(activo=False)
        self.comprobar({"Autoridades de mesa", "Mesas", "Puestos, listas y candidaturas"})

    def test_un_turno_sin_minimo_impide_autoridades_listas(self):
        self.completar_todos()
        tarde = Turno.objects.create(nombre="Tarde", hora_inicio=time(14), hora_fin=time(18))
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.claustros[1], turno=tarde)
        respuesta = self.comprobar({"Autoridades de mesa"})
        self.assertContains(respuesta, "Tarde: 1 mesa no alcanza el mínimo")

    def test_autoridad_rechazada_no_cubre_el_minimo(self):
        self.completar_todos()
        autoridad = self.datos[self.claustros[1].pk]["autoridad"]
        AsignacionAutoridad.objects.filter(pk=autoridad.pk).update(estado="rechazada")
        self.comprobar({"Autoridades de mesa"})

    def test_un_puesto_sin_candidatos_activos_no_completa_la_tarjeta(self):
        self.completar_todos()
        candidato = self.datos[self.claustros[1].pk]["candidato"]
        Candidato.objects.filter(pk=candidato.pk).update(activo=False)
        self.comprobar({"Puestos, listas y candidaturas"})

    def test_presentacion_sin_claustro_no_completa_otro_claustro(self):
        self.completar_todos()
        presentacion = self.datos[self.claustros[1].pk]["presentacion"]
        ParticipacionPartido.objects.filter(pk=presentacion.pk).update(eleccion_claustro=None)
        self.comprobar({"Puestos, listas y candidaturas"})

    def test_capacidad_y_tipo_de_mesa_se_validan(self):
        self.completar_todos()
        claustro = self.claustros[1]
        EleccionClaustro.objects.filter(pk=claustro.pk).update(maximo_votantes_por_mesa=1)
        self.comprobar({"Autoridades de mesa", "Mesas"})
        EleccionClaustro.objects.filter(pk=claustro.pk).update(maximo_votantes_por_mesa=60)
        Mesa.objects.filter(pk=self.datos[claustro.pk]["mesa"].pk).update(es_especial=True)
        self.comprobar({"Autoridades de mesa", "Mesas"})

    def test_sin_claustros_no_se_considera_todo_listo(self):
        from apps.elecciones.resumen_preparacion import construir_resumen_preparacion
        otra = Eleccion.objects.create(nombre="Histórica vacía", fecha_inicio=self.eleccion.fecha_inicio, fecha_fin=self.eleccion.fecha_fin, estado="finalizada")
        resumen = construir_resumen_preparacion(otra)
        for indicador in resumen.values():
            self.assertTrue(indicador["pendiente"])
            self.assertEqual(indicador["total"], 0)

    def test_mesa_especial_valida_no_se_confunde_con_mesa_ordinaria(self):
        self.completar_todos()
        claustro = self.claustros[0]
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro, departamento=Departamento.objects.create(codigo="ESP", nombre="Departamento adicional"),
        )
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=self.sede)
        adicional = RegistroPadron.objects.create(
            elector=self.datos[claustro.pk]["registros"][1].elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=alcance, es_principal=False,
        )
        especial = Mesa.objects.create(eleccion=self.eleccion, numero=10, sede=self.sede, eleccion_claustro_departamento=alcance, es_especial=True)
        AsignacionSedePadron.objects.create(registro_padron=adicional, sede=self.sede, estado="asignada")
        AsignacionMesa.objects.create(registro_padron=adicional, mesa=especial)
        self.comprobar({"Autoridades de mesa"})
