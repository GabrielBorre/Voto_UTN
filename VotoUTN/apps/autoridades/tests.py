from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model, login
from django.core.exceptions import ValidationError
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.autoridades.forms import FormularioAsignacionAutoridad
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.autoridades.services import asignar_autoridad, validar_csv_autoridades
from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroTurno,
)
from apps.mesas.models import Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.usuarios.backend_auth import ElectorBackend, ElectorUser
from apps.usuarios.models import AsignacionRol


class AutoridadesViewsTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion)
        self.claustro = Claustro.objects.create(nombre="Estudiantes vistas")
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=self.claustro,
        )

    def test_gestionar_autoridades_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-autoridades", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "autoridades/gestion.html")
        self.assertContains(respuesta, reverse("configurar-eleccion", args=(self.eleccion.id,)))
        self.assertContains(respuesta, "Volver a configuración", count=1)
        self.assertNotContains(respuesta, 'class="card management-section"')
        self.assertContains(
            respuesta,
            reverse(
                "gestionar-autoridades-claustro",
                args=(self.eleccion.id, self.eleccion_claustro.id),
            ),
        )

    def test_gestionar_autoridades_de_un_claustro_usa_la_pantalla_filtrada(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(
            reverse(
                "gestionar-autoridades-claustro",
                args=(self.eleccion.id, self.eleccion_claustro.id),
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "autoridades/gestion_claustro.html")
        self.assertContains(respuesta, "Autoridades de Estudiantes vistas")
        self.assertContains(respuesta, 'class="card management-section"', count=4)
        self.assertContains(respuesta, reverse("gestionar-autoridades", args=(self.eleccion.id,)))

    def test_mis_asignaciones_autoridad_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("mis-asignaciones-autoridad"))

        self.assertEqual(respuesta.status_code, 403)

    def test_descargar_plantilla_autoridades_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("descargar-plantilla-autoridades", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")
        contenido = respuesta.content.decode("utf-8-sig")
        self.assertIn("DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail", contenido)
        self.assertIn("40123456,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar", contenido)


class AutoridadesImportTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.sede = Sede.objects.create(nombre="Campus")
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro)
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=self.eleccion_claustro, departamento=self.departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.elector = Elector.objects.create(legajo="2024001", nombre="Juan", dni="40123456", correo_electronico="juan@frba.utn.edu.ar")
        self.registro = RegistroPadron.objects.create(
            elector=self.elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )

    def test_validar_csv_autoridades_acepta_formato_nuevo(self):
        contenido = b"DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n40123456,2024001,Juan,Perez,K,juan@frba.utn.edu.ar\n"

        filas, errores = validar_csv_autoridades(contenido, self.eleccion_claustro)

        self.assertEqual(errores, [])
        self.assertEqual(filas[0]["dni"], "40123456")
        self.assertEqual(filas[0]["legajo"], "2024001")

    def test_validar_csv_autoridades_acepta_alias_mail_mayusculas(self):
        contenido = b"DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n40123456,2024001,Juan,Perez,K,juan@frba.utn.edu.ar\n"

        filas, errores = validar_csv_autoridades(contenido, self.eleccion_claustro)

        self.assertEqual(errores, [])
        self.assertEqual(len(filas), 1)

    def test_validar_csv_autoridades_rechaza_elector_de_otro_claustro(self):
        otro_claustro = Claustro.objects.create(nombre="Docentes importación")
        otra_eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=otro_claustro,
        )
        otro_departamento = Departamento.objects.create(nombre="Electrónica", codigo="R")
        otra_configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otra_eleccion_claustro,
            departamento=otro_departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=otra_configuracion,
            sede=self.sede,
        )
        otro_elector = Elector.objects.create(
            legajo="DOC-1",
            nombre="Docente",
            dni="40999888",
            correo_electronico="docente@frba.utn.edu.ar",
        )
        RegistroPadron.objects.create(
            elector=otro_elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=otra_configuracion,
            sede=self.sede,
        )
        contenido = b"DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n40999888,DOC-1,Docente,Prueba,R,docente@frba.utn.edu.ar\n"

        _, errores = validar_csv_autoridades(contenido, self.eleccion_claustro)

        self.assertTrue(errores)
        self.assertIn("no pertenece al padron activo", errores[0][1])

    def test_formulario_manual_solo_ofrece_candidatos_y_mesas_del_claustro(self):
        usuario = get_user_model().objects.create_user(username="cargador-autoridades")
        candidatura_propia = CandidaturaAutoridad.objects.create(
            registro_padron=self.registro,
            cargada_por=usuario,
        )
        mesa_propia = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )
        otro_claustro = Claustro.objects.create(nombre="Docentes formulario")
        otra_eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=otro_claustro,
        )
        otro_departamento = Departamento.objects.create(nombre="Otro departamento", codigo="O")
        otra_configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otra_eleccion_claustro,
            departamento=otro_departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=otra_configuracion,
            sede=self.sede,
        )
        otro_elector = Elector.objects.create(
            legajo="DOC-FORM",
            nombre="Docente formulario",
            dni="40999777",
            correo_electronico="docente.formulario@frba.utn.edu.ar",
        )
        otro_registro = RegistroPadron.objects.create(
            elector=otro_elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=otra_configuracion,
            sede=self.sede,
        )
        candidatura_ajena = CandidaturaAutoridad.objects.create(
            registro_padron=otro_registro,
            cargada_por=usuario,
        )
        mesa_ajena = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=2,
            eleccion_claustro_departamento=otra_configuracion,
            sede=self.sede,
        )

        formulario = FormularioAsignacionAutoridad(eleccion_claustro=self.eleccion_claustro)

        self.assertQuerySetEqual(formulario.fields["candidatura"].queryset, [candidatura_propia])
        self.assertNotIn(candidatura_ajena, formulario.fields["candidatura"].queryset)
        self.assertQuerySetEqual(formulario.fields["mesa"].queryset, [mesa_propia])
        self.assertNotIn(mesa_ajena, formulario.fields["mesa"].queryset)


    def test_candidatura_muestra_nombre_dni_y_legajo(self):
        usuario = get_user_model().objects.create_user(username="cargador-candidatura")
        candidatura = CandidaturaAutoridad.objects.create(
            registro_padron=self.registro,
            cargada_por=usuario,
        )

        elector = self.registro.elector
        self.assertEqual(
            str(candidatura),
            f"{elector.nombre_completo} · DNI {elector.dni} · Legajo {elector.legajo}",
        )


class TurnosAutoridadesTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Elección por turnos",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            maximo_autoridades_por_mesa=2,
        )
        self.usuario = get_user_model().objects.create_user(username="junta-turnos")
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.sede = Sede.objects.create(nombre="Campus turnos")
        claustro = Claustro.objects.create(nombre="Docentes turnos")
        departamento = Departamento.objects.create(nombre="Sistemas turnos", codigo="ST")
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=configuracion,
            sede=self.sede,
        )
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=configuracion,
            sede=self.sede,
        )
        self.manana = Turno.objects.create(nombre="Mañana autoridades", hora_inicio=time(8), hora_fin=time(13))
        self.tarde = Turno.objects.create(nombre="Tarde autoridades", hora_inicio=time(13), hora_fin=time(18))
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.manana)
        self.registros = []
        for indice in range(3):
            elector = Elector.objects.create(
                dni=f"4012300{indice}",
                legajo=f"AUT-{indice}",
                nombre=f"Autoridad {indice}",
                correo_electronico=f"autoridad{indice}@frba.utn.edu.ar",
            )
            self.registros.append(
                RegistroPadron.objects.create(
                    elector=elector,
                    eleccion=self.eleccion,
                    eleccion_claustro_departamento=configuracion,
                    sede=self.sede,
                )
            )

    def test_los_turnos_se_configuran_desde_autoridades(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("gestionar-autoridades-claustro", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "configuracion-turnos": [self.manana.id, self.tarde.id],
                "guardar-turnos": "",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("gestionar-autoridades-claustro", args=(self.eleccion.id, self.eleccion_claustro.id)),
            fetch_redirect_response=False,
        )
        self.assertSetEqual(
            set(self.eleccion_claustro.turnos_autoridad.values_list("turno_id", flat=True)),
            {self.manana.id, self.tarde.id},
        )

    def test_configurar_turnos_no_modifica_otro_claustro(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Estudiantes turnos"),
        )
        EleccionClaustroTurno.objects.create(eleccion_claustro=otro_claustro, turno=self.manana)
        self.client.force_login(self.usuario)

        self.client.post(
            reverse("gestionar-autoridades-claustro", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "configuracion-turnos": [self.tarde.id],
                "guardar-turnos": "",
            },
        )

        self.assertSetEqual(
            set(self.eleccion_claustro.turnos_autoridad.values_list("turno_id", flat=True)),
            {self.tarde.id},
        )
        self.assertSetEqual(
            set(otro_claustro.turnos_autoridad.values_list("turno_id", flat=True)),
            {self.manana.id},
        )

    def test_no_permite_turno_habilitado_solo_en_otro_claustro(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Graduados turnos"),
        )
        EleccionClaustroTurno.objects.create(eleccion_claustro=otro_claustro, turno=self.tarde)

        with self.assertRaisesMessage(ValidationError, "habilitado para este claustro"):
            asignar_autoridad(self.registros[0], self.mesa, self.tarde, self.usuario)

    def test_el_limite_se_aplica_por_mesa_y_turno(self):
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.tarde)

        primera, _ = asignar_autoridad(self.registros[0], self.mesa, self.manana, self.usuario)
        segunda, _ = asignar_autoridad(self.registros[1], self.mesa, self.manana, self.usuario)

        self.assertEqual(primera.turno, self.manana)
        self.assertEqual(segunda.turno, self.manana)
        with self.assertRaisesMessage(ValidationError, "máximo de autoridades"):
            asignar_autoridad(self.registros[2], self.mesa, self.manana, self.usuario)

        tercera, creada = asignar_autoridad(self.registros[2], self.mesa, self.tarde, self.usuario)
        self.assertTrue(creada)
        self.assertEqual(tercera.turno, self.tarde)

    def test_no_permite_quitar_un_turno_con_autoridades_asignadas(self):
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.tarde)
        asignar_autoridad(self.registros[0], self.mesa, self.manana, self.usuario)
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("gestionar-autoridades-claustro", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {
                "configuracion-turnos": [self.tarde.id],
                "guardar-turnos": "",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se puede quitar un turno que ya tiene autoridades asignadas")
        self.assertTrue(AsignacionAutoridad.objects.filter(turno=self.manana).exists())
        self.assertTrue(
            EleccionClaustroTurno.objects.filter(
                eleccion_claustro=self.eleccion_claustro,
                turno=self.manana,
            ).exists()
        )


class ElectorBackendTests(TestCase):
    def test_elector_virtual_no_se_guarda_en_auth_user(self):
        usuario = ElectorBackend().authenticate(None, dni="40111222", username="eva", first_name="Eva")

        self.assertIsInstance(usuario, ElectorUser)
        self.assertTrue(usuario.is_authenticated)
        self.assertEqual(usuario.username, "eva")
        self.assertFalse(get_user_model().objects.filter(username="40111222").exists())

    def test_login_elector_guarda_id_entero_en_sesion(self):
        usuario = ElectorBackend().authenticate(None, dni="28111333", username="alumnocg", first_name="Alumno")
        request = RequestFactory().get("/")
        request.session = SessionStore()

        login(request, usuario, backend="apps.usuarios.backend_auth.ElectorBackend")

        self.assertEqual(request.session["_auth_user_id"], "28111333")
        self.assertEqual(request.session["_auth_user_backend"], "apps.usuarios.backend_auth.ElectorBackend")

    def test_get_user_elector_virtual_reconstruye_sin_elector_en_bd(self):
        usuario = ElectorBackend().get_user("38999222")

        self.assertIsNotNone(usuario)
        self.assertTrue(getattr(usuario, "is_authenticated", False))
        self.assertTrue(getattr(usuario, "es_elector", False))
        self.assertEqual(usuario.dni, "38999222")

    def test_login_elector_virtual_se_rehidrata_en_la_siguiente_peticion(self):
        cliente = Client()
        usuario = ElectorBackend().authenticate(None, dni="28111333", first_name="Alumno")
        request = RequestFactory().get("/")
        request.session = SessionStore()
        login(request, usuario, backend="apps.usuarios.backend_auth.ElectorBackend")
        request.session["keycloak_user"] = {
            "dni": "28111333",
            "username": "alumnocg",
            "first_name": "Alumno",
            "last_name": "CG",
            "email": "alumno@example.com",
            "subject": "kc-sub",
        }
        request.session.save()
        cliente.cookies["sessionid"] = request.session.session_key

        respuesta = cliente.get(reverse("index"), HTTP_HOST="localhost")

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.wsgi_request.user.is_authenticated)
        self.assertEqual(respuesta.wsgi_request.user.dni, "28111333")
        self.assertEqual(respuesta.wsgi_request.user.username, "alumnocg")
        self.assertEqual(respuesta.wsgi_request.user.first_name, "Alumno")
        self.assertEqual(respuesta.wsgi_request.user.last_name, "CG")
        self.assertEqual(respuesta.wsgi_request.user.email, "alumno@example.com")
