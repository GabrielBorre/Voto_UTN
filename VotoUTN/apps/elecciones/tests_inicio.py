from datetime import date, time, timedelta
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.formats import date_format
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Turno
from apps.usuarios.backend_auth import ElectorUser
from apps.usuarios.models import AsignacionRol, PerfilUsuario


class InicioAutenticadoTests(TestCase):
    def test_login_redirige_al_flujo_oidc_de_keycloak(self):
        respuesta = self.client.get(reverse("keycloak_login"), HTTP_HOST="localhost:8000")

        self.assertEqual(respuesta.status_code, 302)
        destino = urlparse(respuesta.url)
        parametros = parse_qs(destino.query)
        self.assertEqual(destino.path, "/realms/FRBA/protocol/openid-connect/auth")
        self.assertEqual(parametros["client_id"], ["VOTOUTN"])
        self.assertEqual(parametros["response_type"], ["code"])
        self.assertEqual(parametros["redirect_uri"], ["http://localhost:8000/callback"])

    def test_seccion_protegida_redirige_al_login_configurado(self):
        destino = reverse("gestionar-partidos", args=(4,))

        respuesta = self.client.get(destino)

        self.assertRedirects(
            respuesta,
            f"{reverse('keycloak_login')}?next={destino}",
            fetch_redirect_response=False,
        )

    def test_superusuario_ingresa_al_panel_de_gestion(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin-prueba",
            password="clave-prueba",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertRedirects(
            respuesta,
            reverse("inicio-administrador-junta"),
            fetch_redirect_response=False,
        )

    def test_usuario_operativo_ingresa_a_la_seleccion_de_eleccion(self):
        usuario = get_user_model().objects.create_user(
            username="operador-prueba",
            password="clave-prueba",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertRedirects(
            respuesta,
            reverse("lista-elecciones"),
            fetch_redirect_response=False,
        )

    def test_usuario_autenticado_ve_menu_compartido_con_enlace_a_inicio(self):
        usuario = get_user_model().objects.create_user(
            username="usuario-menu",
            password="clave-prueba",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("lista-elecciones"))

        self.assertContains(respuesta, 'aria-label="Navegación de Junta Electoral"')
        self.assertContains(respuesta, f'href="{reverse("inicio-autenticado")}"')

    def test_lista_muestra_aviso_si_no_hay_eleccion_en_curso(self):
        usuario = get_user_model().objects.create_user(
            username="operador-sin-eleccion",
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
        )
        Eleccion.objects.create(
            nombre="Elección cerrada",
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 2),
            estado=Eleccion.Estado.FINALIZADA,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("lista-elecciones"))

        self.assertContains(
            respuesta,
            "Debe haber una elección en curso para poder registrar participación.",
        )
        self.assertContains(respuesta, "Registro de participación")
        self.assertContains(
            respuesta,
            'class="gestion-nav__disabled" role="link" aria-disabled="true" tabindex="0" title="Debe haber una elección en curso para poder registrar participación."',
        )
        self.assertNotContains(
            respuesta,
            f'href="{reverse("lista-elecciones")}"',
        )

    def test_lista_muestra_aviso_sin_titulo_seleccion_si_hay_eleccion_en_curso_pero_no_hay_opciones(self):
        usuario = get_user_model().objects.create_user(
            username="operador-sin-opciones",
        )
        self.client.force_login(usuario)
        Eleccion.objects.create(
            nombre="Elección abierta",
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 2),
            estado=Eleccion.Estado.EN_CURSO,
        )

        respuesta = self.client.get(reverse("lista-elecciones"))

        self.assertContains(
            respuesta,
            "La elección todavía no está abierta para poder registrar participación.",
        )
        self.assertNotContains(respuesta, "Seleccioná una elección")
        self.assertNotContains(respuesta, 'href="/escanear/')

    def test_inicio_administrador_junta_muestra_eleccion_en_curso_y_su_estado(self):
        usuario = get_user_model().objects.create_user(
            username="admin-junta-curso",
        )
        eleccion_en_curso = Eleccion.objects.create(
            nombre="Elección preparatoria",
            fecha_inicio=date(2026, 9, 1),
            fecha_fin=date(2026, 9, 10),
            estado=Eleccion.Estado.PUBLICADA,
        )
        eleccion_cerrada = Eleccion.objects.create(
            nombre="Elección cerrada anterior",
            fecha_inicio=date(2026, 7, 1),
            fecha_fin=date(2026, 7, 5),
            estado=Eleccion.Estado.FINALIZADA,
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            eleccion=eleccion_en_curso,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            eleccion=eleccion_cerrada,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("inicio-administrador-junta"))

        self.assertContains(respuesta, eleccion_en_curso.nombre)
        self.assertContains(respuesta, "Publicada")
        self.assertNotContains(respuesta, eleccion_cerrada.nombre)

    def test_inicio_administrador_junta_ofrece_crear_si_no_hay_eleccion_actual(self):
        usuario = get_user_model().objects.create_user(
            username="admin-junta-cerrada",
        )
        eleccion_cerrada = Eleccion.objects.create(
            nombre="Elección cerrada más reciente",
            fecha_inicio=date(2026, 8, 1),
            fecha_fin=date(2026, 8, 10),
            estado=Eleccion.Estado.FINALIZADA,
        )
        otra_eleccion_cerrada = Eleccion.objects.create(
            nombre="Elección cerrada anterior",
            fecha_inicio=date(2026, 7, 1),
            fecha_fin=date(2026, 7, 5),
            estado=Eleccion.Estado.FINALIZADA,
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            eleccion=eleccion_cerrada,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            eleccion=otra_eleccion_cerrada,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("inicio-administrador-junta"))

        self.assertContains(respuesta, "Crear elección")
        self.assertNotContains(respuesta, eleccion_cerrada.nombre)
        self.assertNotContains(respuesta, otra_eleccion_cerrada.nombre)
        self.assertContains(
            respuesta,
            'class="gestion-nav__disabled" role="link" aria-disabled="true" tabindex="0" '
            'title="No hay una elección actual para configurar. Creala desde Inicio.">Configurar elección</span>',
        )
        self.assertNotContains(respuesta, f'href="{reverse("gestionar-elecciones")}"')

    def test_pestana_configurar_eleccion_habilitada_con_eleccion_actual(self):
        usuario = get_user_model().objects.create_user(username="admin-junta-actual")
        eleccion = Eleccion.objects.create(
            nombre="Elección actual",
            fecha_inicio=date(2026, 9, 1),
            fecha_fin=date(2026, 9, 10),
        )
        AsignacionRol.objects.create(
            usuario=usuario, eleccion=eleccion, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("inicio-administrador-junta"))

        self.assertContains(respuesta, f'href="{reverse("gestionar-elecciones")}">Configurar elección</a>')
        self.assertNotContains(respuesta, "No hay una elección actual para configurar.")

    def test_lista_solo_considera_en_curso_estado_abierta(self):
        usuario = get_user_model().objects.create_user(
            username="operador-con-eleccion",
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
        )
        self.client.force_login(usuario)

        for estado in (Eleccion.Estado.EN_PREPARACION, Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO):
            with self.subTest(estado=estado):
                eleccion = None
                try:
                    eleccion = Eleccion.objects.create(
                        nombre=f"Elección {estado}",
                        fecha_inicio=date(2026, 10, 1),
                        fecha_fin=date(2026, 10, 2),
                        estado=estado,
                    )
                    respuesta = self.client.get(reverse("lista-elecciones"))
                    if estado == Eleccion.Estado.EN_CURSO:
                        self.assertNotContains(
                            respuesta,
                            "Debe haber una elección en curso para poder registrar participación.",
                        )
                        self.assertContains(respuesta, f'href="{reverse("lista-elecciones")}"')
                        self.assertNotContains(respuesta, 'class="gestion-nav__disabled"')
                    else:
                        self.assertContains(
                            respuesta,
                            "Debe haber una elección en curso para poder registrar participación.",
                        )
                        self.assertContains(respuesta, 'class="gestion-nav__disabled"')
                finally:
                    if eleccion is not None:
                        eleccion.delete()

    def test_elector_keycloak_puede_abrir_su_inicio(self):
        elector = ElectorUser("9876543210")
        self.client.force_login(elector, backend="apps.usuarios.backend_auth.ElectorBackend")

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Mi información electoral")


class InicioElectorTests(TestCase):
    def setUp(self):
        self.elector = Elector.objects.create(
            legajo="inicio-elector-1",
            nombre="Elector",
            apellido="Prueba",
            dni="9876543210",
        )
        self.claustro = Claustro.objects.create(nombre="Claustro inicio")
        self.departamento = Departamento.objects.create(nombre="Departamento inicio", codigo="INI")
        self.eleccion_en_curso = self.crear_eleccion(
            "Elección en curso",
            Eleccion.Estado.EN_CURSO,
        )
        self.registro_en_curso = self.crear_registro(self.eleccion_en_curso)
        self.client.force_login(
            ElectorUser(self.elector.dni),
            backend="apps.usuarios.backend_auth.ElectorBackend",
        )

    def crear_eleccion(self, nombre, estado):
        return Eleccion.objects.create(
            nombre=nombre,
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 2),
            estado=estado,
        )

    def crear_registro(self, eleccion):
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=eleccion,
            claustro=self.claustro,
        )
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=self.departamento,
        )
        return RegistroPadron.objects.create(
            elector=self.elector,
            eleccion=eleccion,
            eleccion_claustro_departamento=alcance,
        )

    def crear_asignacion_autoridad(self, registro):
        mesa = Mesa.objects.create(eleccion=registro.eleccion, numero=1)
        turno = Turno.objects.create(
            nombre=f"Turno autoridad {registro.eleccion_id}",
            hora_inicio=time(8),
            hora_fin=time(12),
        )
        asignador = get_user_model().objects.create_user(
            username=f"asignador-autoridad-{registro.eleccion_id}",
        )
        return AsignacionAutoridad.objects.create(
            registro_padron=registro,
            mesa=mesa,
            turno=turno,
            asignada_por=asignador,
        )

    def iniciar_sesion_local_con_rol_autoridad(self, eleccion):
        usuario = get_user_model().objects.create_user(username=f"autoridad-{eleccion.pk}")
        PerfilUsuario.objects.create(usuario=usuario, elector=self.elector)
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.AUTORIDAD_MESA,
            eleccion=eleccion,
        )
        self.client.force_login(usuario)

    def test_muestra_rol_autoridad_para_asignacion_de_eleccion_en_curso(self):
        self.crear_asignacion_autoridad(self.registro_en_curso)
        self.iniciar_sesion_local_con_rol_autoridad(self.eleccion_en_curso)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Rol: <b>Autoridad de Mesa</b>")
        self.assertTrue(respuesta.context["nav_es_autoridad"])

    def test_muestra_rol_autoridad_para_asignacion_de_eleccion_publicada(self):
        self.eleccion_en_curso.estado = Eleccion.Estado.PUBLICADA
        self.eleccion_en_curso.autoridades_confirmadas_en = timezone.now()
        self.eleccion_en_curso.save(update_fields=("estado", "autoridades_confirmadas_en"))
        asignacion = self.crear_asignacion_autoridad(self.registro_en_curso)
        self.iniciar_sesion_local_con_rol_autoridad(self.eleccion_en_curso)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Rol: <b>Autoridad de Mesa</b>")
        self.assertContains(respuesta, "Se informará cuando la elección esté en curso")
        self.assertNotContains(respuesta, asignacion.mesa.codigo)
        self.assertTrue(respuesta.context["nav_es_autoridad"])

    def test_oculta_turno_de_autoridad_provisoria_en_publicada(self):
        self.eleccion_en_curso.estado = Eleccion.Estado.PUBLICADA
        self.eleccion_en_curso.save(update_fields=("estado",))
        asignacion = self.crear_asignacion_autoridad(self.registro_en_curso)
        self.iniciar_sesion_local_con_rol_autoridad(self.eleccion_en_curso)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertNotContains(respuesta, str(asignacion.turno))
        self.assertNotContains(respuesta, "Desempeño como Autoridad de Mesa")

    def test_muestra_rol_elector_para_asignacion_de_eleccion_en_preparacion(self):
        self.eleccion_en_curso.estado = Eleccion.Estado.FINALIZADA
        self.eleccion_en_curso.save(update_fields=("estado",))
        eleccion_en_preparacion = self.crear_eleccion(
            "Elección en preparación",
            Eleccion.Estado.EN_PREPARACION,
        )
        registro = self.crear_registro(eleccion_en_preparacion)
        self.crear_asignacion_autoridad(registro)
        self.iniciar_sesion_local_con_rol_autoridad(eleccion_en_preparacion)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Rol: <b>Elector</b>")
        self.assertNotContains(respuesta, "Rol: <b>Autoridad de Mesa</b>")
        self.assertFalse(respuesta.context["nav_es_autoridad"])

    def test_asignacion_rechazada_no_muestra_rol_autoridad(self):
        asignacion = self.crear_asignacion_autoridad(self.registro_en_curso)
        asignacion.estado = AsignacionAutoridad.Estado.RECHAZADA
        asignacion.save(update_fields=("estado",))
        self.iniciar_sesion_local_con_rol_autoridad(self.eleccion_en_curso)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Rol: <b>Elector</b>")
        self.assertNotContains(respuesta, "Rol: <b>Autoridad de Mesa</b>")
        self.assertFalse(respuesta.context["nav_es_autoridad"])

    def test_muestra_rol_elector_cuando_solo_tiene_asignaciones_historicas(self):
        self.eleccion_en_curso.estado = Eleccion.Estado.FINALIZADA
        self.eleccion_en_curso.save(update_fields=("estado",))
        registro = self.eleccion_en_curso.registros_padron.get(elector=self.elector)
        self.crear_asignacion_autoridad(registro)
        self.iniciar_sesion_local_con_rol_autoridad(self.eleccion_en_curso)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Rol: <b>Elector</b>")
        self.assertNotContains(respuesta, "Rol: <b>Autoridad de Mesa</b>")
        self.assertFalse(respuesta.context["nav_es_autoridad"])
        self.assertIsNone(respuesta.context["eleccion_en_curso"])

    def test_asignacion_de_eleccion_anterior_no_muestra_rol_autoridad_en_la_actual(self):
        eleccion_anterior = self.crear_eleccion(
            "Elección anterior",
            Eleccion.Estado.FINALIZADA,
        )
        registro_anterior = self.crear_registro(eleccion_anterior)
        self.crear_asignacion_autoridad(registro_anterior)
        self.iniciar_sesion_local_con_rol_autoridad(eleccion_anterior)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Rol: <b>Elector</b>")
        self.assertNotContains(respuesta, "Rol: <b>Autoridad de Mesa</b>")
        self.assertContains(respuesta, self.eleccion_en_curso.nombre)
        self.assertFalse(respuesta.context["nav_es_autoridad"])

    def test_muestra_solo_el_registro_de_la_eleccion_en_curso(self):
        eleccion_cerrada = self.crear_eleccion(
            "Elección cerrada anterior",
            Eleccion.Estado.FINALIZADA,
        )
        self.crear_registro(eleccion_cerrada)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.eleccion_en_curso.nombre)
        self.assertNotContains(respuesta, eleccion_cerrada.nombre)
        self.assertEqual(
            [registro.eleccion_id for registro in respuesta.context["registros"]],
            [self.eleccion_en_curso.pk],
        )

    def test_muestra_sin_padron_si_no_esta_cargado_en_la_eleccion_en_curso(self):
        self.eleccion_en_curso.registros_padron.all().delete()
        eleccion_cerrada = self.crear_eleccion(
            "Elección cerrada anterior",
            Eleccion.Estado.FINALIZADA,
        )
        self.crear_registro(eleccion_cerrada)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertContains(respuesta, "Sin información disponible")
        self.assertContains(
            respuesta,
            "No encontramos un registro de padrón asociado a tu identidad.",
        )
        self.assertNotContains(respuesta, "Sin elecciones en curso")

    def test_no_muestra_eleccion_en_preparacion_en_inicio_del_elector(self):
        self.eleccion_en_curso.estado = Eleccion.Estado.EN_PREPARACION
        self.eleccion_en_curso.save(update_fields=("estado",))

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, self.eleccion_en_curso.nombre)
        self.assertContains(respuesta, "Sin elecciones en curso")
        self.assertIsNone(respuesta.context["eleccion_en_curso"])
        self.assertFalse(respuesta.context["registros"].exists())

    def test_muestra_eleccion_publicada_en_inicio_del_elector(self):
        self.eleccion_en_curso.estado = Eleccion.Estado.PUBLICADA
        self.eleccion_en_curso.save(update_fields=("estado",))
        mesa = Mesa.objects.create(eleccion=self.eleccion_en_curso, numero=23)
        AsignacionMesa.objects.create(registro_padron=self.registro_en_curso, mesa=mesa)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.eleccion_en_curso.nombre)
        self.assertContains(respuesta, "Se informará cuando la elección esté en curso")
        self.assertNotContains(respuesta, mesa.codigo)
        self.assertEqual(
            [registro.eleccion_id for registro in respuesta.context["registros"]],
            [self.eleccion_en_curso.pk],
        )

    def test_muestra_mesa_asignada_cuando_la_eleccion_esta_en_curso(self):
        mesa = Mesa.objects.create(eleccion=self.eleccion_en_curso, numero=23)
        AsignacionMesa.objects.create(registro_padron=self.registro_en_curso, mesa=mesa)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, mesa.codigo)
        self.assertNotContains(respuesta, "Será asignada próximamente")

    def test_oculta_tarjetas_de_periodos_sin_fecha_limite(self):
        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertNotContains(respuesta, "Eximición de autoridades de mesa")
        self.assertNotContains(respuesta, "Justificación de inasistencia electoral")
        self.assertNotContains(respuesta, "Solicitud de cambio de sede")
        self.assertNotContains(respuesta, "A confirmar")

    def test_muestra_titulo_y_fecha_limite_solo_de_periodos_iniciados(self):
        fecha_inicio = timezone.now()
        limite_eximicion = timezone.localdate() + timedelta(days=4)
        limite_justificativo = timezone.localdate() + timedelta(days=5)
        limite_cambio_sede = timezone.localdate() + timedelta(days=2)
        self.eleccion_en_curso.autoridades_confirmadas_en = fecha_inicio
        self.eleccion_en_curso.estado = Eleccion.Estado.PUBLICADA
        self.eleccion_en_curso.fecha_limite_justificacion_autoridades = limite_eximicion
        self.eleccion_en_curso.justificacion_electores_habilitada_en = fecha_inicio
        self.eleccion_en_curso.fecha_limite_justificacion_electores = limite_justificativo
        self.eleccion_en_curso.solicitudes_cambio_sede_habilitadas_en = fecha_inicio
        self.eleccion_en_curso.fecha_cierre_solicitudes_cambio_sede = limite_cambio_sede
        self.eleccion_en_curso.notificaciones_ausentes_confirmadas_en = fecha_inicio
        self.eleccion_en_curso.save(update_fields=(
            "autoridades_confirmadas_en",
            "estado",
            "fecha_limite_justificacion_autoridades",
            "justificacion_electores_habilitada_en",
            "fecha_limite_justificacion_electores",
            "solicitudes_cambio_sede_habilitadas_en",
            "fecha_cierre_solicitudes_cambio_sede",
            "notificaciones_ausentes_confirmadas_en",
        ))
        self.crear_asignacion_autoridad(self.registro_en_curso)
        mesa_ausencia = Mesa.objects.create(eleccion=self.eleccion_en_curso, numero=25)
        usuario = get_user_model().objects.create_user(username="registro-ausencia-periodo")
        RegistroParticipacion.objects.create(
            registro_padron=self.registro_en_curso,
            mesa=mesa_ausencia,
            registrada_por=usuario,
            metodo=RegistroParticipacion.Metodo.MANUAL,
        )

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertContains(respuesta, "Eximición de autoridades de mesa")
        self.assertContains(respuesta, "Justificación de inasistencia electoral")
        self.assertNotContains(respuesta, "Solicitud de cambio de sede")
        for fecha in (limite_eximicion, limite_justificativo):
            self.assertContains(respuesta, date_format(fecha, "j \\d\\e F \\d\\e Y"))
        self.assertNotContains(respuesta, "A confirmar")

    def test_muestra_cambio_sede_solo_publicada_antes_de_confirmar_autoridades(self):
        fecha_inicio = timezone.now()
        limite_cambio_sede = timezone.localdate() + timedelta(days=2)
        self.eleccion_en_curso.estado = Eleccion.Estado.PUBLICADA
        self.eleccion_en_curso.solicitudes_cambio_sede_habilitadas_en = fecha_inicio
        self.eleccion_en_curso.fecha_cierre_solicitudes_cambio_sede = limite_cambio_sede
        self.eleccion_en_curso.save(update_fields=(
            "estado",
            "solicitudes_cambio_sede_habilitadas_en",
            "fecha_cierre_solicitudes_cambio_sede",
        ))

        respuesta = self.client.get(reverse("inicio-autenticado"))
        self.assertContains(respuesta, "Solicitud de cambio de sede")

        self.eleccion_en_curso.autoridades_confirmadas_en = fecha_inicio + timedelta(minutes=1)
        self.eleccion_en_curso.save(update_fields=("autoridades_confirmadas_en",))
        respuesta = self.client.get(reverse("inicio-autenticado"))
        self.assertNotContains(respuesta, "Solicitud de cambio de sede")

    def test_oculta_periodos_cerrados_por_fecha_o_evento_de_estado(self):
        fecha_inicio = timezone.now() - timedelta(days=4)
        fecha_futura = timezone.localdate() + timedelta(days=3)
        fecha_vencida = timezone.localdate() - timedelta(days=1)
        self.eleccion_en_curso.autoridades_confirmadas_en = fecha_inicio
        self.eleccion_en_curso.solicitudes_cambio_sede_habilitadas_en = fecha_inicio
        self.eleccion_en_curso.fecha_cierre_solicitudes_cambio_sede = fecha_futura
        self.eleccion_en_curso.fecha_limite_justificacion_autoridades = fecha_futura
        self.eleccion_en_curso.estado = Eleccion.Estado.PUBLICADA
        self.eleccion_en_curso.save(update_fields=(
            "autoridades_confirmadas_en",
            "solicitudes_cambio_sede_habilitadas_en",
            "fecha_cierre_solicitudes_cambio_sede",
            "fecha_limite_justificacion_autoridades",
            "estado",
        ))
        self.crear_asignacion_autoridad(self.registro_en_curso)

        respuesta = self.client.get(reverse("inicio-autenticado"))
        self.assertNotContains(respuesta, "Solicitud de cambio de sede")
        self.assertContains(respuesta, "Eximición de autoridades de mesa")

        self.eleccion_en_curso.fecha_limite_justificacion_autoridades = fecha_vencida
        self.eleccion_en_curso.save(update_fields=("fecha_limite_justificacion_autoridades",))
        respuesta = self.client.get(reverse("inicio-autenticado"))
        self.assertNotContains(respuesta, "Eximición de autoridades de mesa")

        self.eleccion_en_curso.fecha_limite_justificacion_autoridades = fecha_futura
        self.eleccion_en_curso.estado = Eleccion.Estado.EN_CURSO
        self.eleccion_en_curso.save(update_fields=(
            "fecha_limite_justificacion_autoridades",
            "estado",
        ))
        respuesta = self.client.get(reverse("inicio-autenticado"))
        self.assertNotContains(respuesta, "Solicitud de cambio de sede")
        self.assertNotContains(respuesta, "Eximición de autoridades de mesa")

    def test_muestra_la_situacion_electoral_calculada_por_el_historial(self):
        url = reverse("inicio-autenticado")

        en_curso = self.client.get(url)
        self.assertContains(en_curso, "pill info")
        self.assertContains(en_curso, "En Curso")

        self.eleccion_en_curso.notificaciones_ausentes_confirmadas_en = timezone.now()
        self.eleccion_en_curso.justificacion_electores_habilitada_en = timezone.now()
        self.eleccion_en_curso.fecha_limite_justificacion_electores = timezone.localdate() + timedelta(days=5)
        self.eleccion_en_curso.save(
            update_fields=(
                "notificaciones_ausentes_confirmadas_en",
                "justificacion_electores_habilitada_en",
                "fecha_limite_justificacion_electores",
            )
        )

        voto_emitido = self.client.get(url)
        self.assertContains(voto_emitido, "pill ok")
        self.assertContains(voto_emitido, "Voto Emitido")
        self.assertNotContains(voto_emitido, "Justificación de inasistencia electoral")

        mesa = Mesa.objects.create(eleccion=self.eleccion_en_curso, numero=24)
        usuario = get_user_model().objects.create_user(username="registro-inicio-elector")
        RegistroParticipacion.objects.create(
            registro_padron=self.registro_en_curso,
            mesa=mesa,
            registrada_por=usuario,
            metodo=RegistroParticipacion.Metodo.MANUAL,
        )

        inasistencia = self.client.get(url)
        self.assertContains(inasistencia, "pill warn")
        self.assertContains(inasistencia, "En Curso - Voto No Registrado")
        self.assertContains(inasistencia, "Justificación de inasistencia electoral")

        justificativo = JustificativoAusencia.objects.create(
            registro_padron=self.registro_en_curso,
            ausencia=JustificativoAusencia.Ausencia.VOTAR,
            tipo=TipoJustificativo.objects.create(nombre="Motivo inicio"),
            detalle="Detalle de prueba.",
            estado=JustificativoAusencia.Estado.PENDIENTE,
        )
        pendiente = self.client.get(url)
        self.assertContains(pendiente, "pill warn")
        self.assertContains(pendiente, "Justificativo Pendiente de Revisión")
        self.assertContains(pendiente, "Justificación de inasistencia electoral")

        justificativo.estado = JustificativoAusencia.Estado.APROBADO
        justificativo.save(update_fields=("estado",))
        aprobada = self.client.get(url)
        self.assertContains(aprobada, "Inasistencia Justificada")
        self.assertNotContains(aprobada, "Justificación de inasistencia electoral")

        justificativo.estado = JustificativoAusencia.Estado.RECHAZADO
        justificativo.save(update_fields=("estado",))
        rechazada = self.client.get(url)
        self.assertContains(rechazada, "Infractor - Justificación Rechazada")
        self.assertNotContains(rechazada, "Justificación de inasistencia electoral")

    def test_muestra_aviso_y_enlace_al_historial_si_no_hay_elecciones_en_curso(self):
        self.eleccion_en_curso.estado = Eleccion.Estado.FINALIZADA
        self.eleccion_en_curso.save(update_fields=("estado",))

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertContains(respuesta, "Sin elecciones en curso")
        self.assertContains(respuesta, "No hay elecciones en curso en este momento.")
        self.assertContains(
            respuesta,
            f'href="{reverse("historial-electoral")}"',
        )
        self.assertNotContains(respuesta, "Sin información disponible")
