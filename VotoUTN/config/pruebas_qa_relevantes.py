"""Selección explícita de 67 pruebas funcionales relevantes para QA."""

PRUEBAS_RELEVANTES = {
    "apps.asistencia.tests.ServicioAsistenciaQrTests": (
        "test_acepta_codigo_qr_con_firma_valida",
        "test_rechaza_codigo_qr_con_firma_alterada",
        "test_rechaza_codigo_qr_firmado_con_otra_clave",
        "test_el_generador_y_el_validador_comparten_clave_de_firma",
    ),
    "apps.asistencia.tests.ServicioRegistroParticipacionEleccionTests": (
        "test_registrar_lote_marca_qr_de_otra_eleccion",
    ),
    "apps.asistencia.tests.NomenclaturaDominioTests": (
        "test_el_serializador_recibe_codigos_qr",
    ),
    "apps.asistencia.tests.ModeloElectoralTests": (
        "test_turno_rechaza_un_horario_invalido",
        "test_mesa_y_padron_deben_corresponder_a_la_misma_eleccion",
    ),
    "apps.asistencia.tests.PermisosParticipacionTests": (
        "test_administrativo_asignado_puede_registrar_en_su_eleccion",
        "test_administrativo_global_puede_abrir_asistencia_de_cualquier_eleccion_activa",
        "test_autoridad_de_mesa_no_puede_registrar_participacion",
    ),
    "apps.asistencia.tests.VistaCargaManualEscritorioTests": (
        "test_la_vista_incluye_formulario_manual_y_escanner_movil",
    ),
    "apps.asistencia.tests.CicloDeVidaEleccionTests": (
        "test_solo_abre_con_mesas_y_cerrar_la_deshabilita",
    ),
    "apps.asistencia.tests.ImportacionPadronTests": (
        "test_confirma_csv_valido_y_es_idempotente",
        "test_rechaza_formula_y_sede_fuera_del_alcance",
    ),
    "apps.asistencia.tests.AutoridadesMesaTests": (
        "test_asignacion_valida_sincroniza_el_rol_operativo",
        "test_rechaza_mesa_de_otro_claustro",
    ),
    "apps.padron.tests.PadronViewsTests": (
        "test_previsualizacion_guarda_y_muestra_registros_ya_existentes",
        "test_previsualizacion_calcula_nuevos_y_existentes_aunque_haya_errores",
        "test_validar_csv_padron_mapea_departamento_principal_correctamente",
        "test_validar_csv_padron_acepta_dni_numerico_de_excel",
        "test_validar_csv_padron_indica_solo_el_legajo_incorrecto",
        "test_confirmar_importacion_no_requiere_maximo_por_mesa",
    ),
    "apps.padron.tests.CalculoMesasAutomaticasEleccionTests": (
        "test_calcula_todos_los_claustros_por_sede_electoral_y_respeta_maximos",
        "test_error_en_un_claustro_no_borra_la_distribucion_anterior",
        "test_elector_sin_sede_asignada_impide_el_calculo_completo",
    ),
    "apps.padron.tests.ProteccionEmisionQrTests": (
        "test_generar_qr_marca_emision_y_numero_de_mesa",
        "test_no_regenera_mesas_despues_de_emitir_qr",
        "test_bloquea_cambio_directo_de_mesa_despues_de_emitir_qr",
        "test_falla_de_archivos_no_marca_qr_como_emitido",
    ),
    "apps.padron.tests.AsignacionSedesClaustroTests": (
        "test_salta_destino_no_habilitado_y_continua_con_la_siguiente_regla",
        "test_una_sede_se_asigna_automaticamente_y_multi_sede_sin_regla_queda_pendiente",
    ),
    "apps.padron.tests.EliminarPadronClaustroTests": (
        "test_no_elimina_si_hay_participacion_registrada",
    ),
    "apps.autoridades.tests.AutoridadesImportTests": (
        "test_validar_csv_autoridades_acepta_formato_nuevo",
        "test_validar_csv_autoridades_rechaza_nombre_que_no_coincide_con_el_padron",
        "test_validar_csv_autoridades_rechaza_correo_que_no_coincide_con_el_padron",
        "test_validar_csv_autoridades_acepta_variantes_de_mayusculas_espacios_y_tildes",
        "test_validar_archivo_xlsx_usa_el_lector_de_excel",
        "test_validar_csv_autoridades_rechaza_elector_de_otro_claustro",
        "test_formulario_manual_solo_ofrece_candidatos_y_mesas_del_claustro",
    ),
    "apps.autoridades.tests.TurnosAutoridadesTests": (
        "test_el_limite_se_aplica_por_mesa_y_turno",
        "test_no_permite_quitar_un_turno_con_autoridades_asignadas",
    ),
    "apps.autoridades.tests.ElectorBackendTests": (
        "test_elector_virtual_no_se_guarda_en_auth_user",
    ),
    "apps.elecciones.tests_permisos.CreacionEleccionPorAdministradorJuntaTests": (
        "test_deshabilita_nueva_eleccion_y_muestra_el_estado_en_curso",
        "test_habilita_nueva_eleccion_si_no_hay_eleccion_en_curso",
        "test_listados_separan_elecciones_cerradas_de_las_gestionables",
        "test_administrador_junta_puede_editar_eleccion_creada_por_otro",
        "test_administrativo_sin_eleccion_asignada_puede_hacer_sus_tareas_en_todas",
        "test_nueva_eleccion_copia_la_organizacion_del_claustro",
        "test_gestiona_departamentos_del_claustro_y_hereda_sus_sedes",
        "test_no_permite_quitar_un_departamento_utilizado_por_una_mesa",
        "test_usuario_sin_rol_no_puede_crear_eleccion",
        "test_administrativo_junta_no_puede_crear_elecciones",
    ),
    "apps.elecciones.tests_permisos.EleccionCerradaSoloConsultaTests": (
        "test_pantallas_de_configuracion_de_eleccion_cerrada_estan_bloqueadas",
        "test_eleccion_cerrada_rechaza_edicion_y_cambio_de_estado_por_post",
        "test_historial_sigue_consultable_y_dashboard_permanece_pendiente",
    ),
    "apps.auditoria.tests.AuditoriaParticipacionTests": (
        "test_registro_qr_crea_evento_de_auditoria",
        "test_registro_manual_crea_evento_de_auditoria",
    ),
    "apps.auditoria.tests.AuditoriaEleccionTests": (
        "test_cambio_de_estado_crea_evento_de_auditoria",
    ),
    "apps.elecciones.tests_unica_eleccion.EleccionUnicaNoCerradaTests": (
        "test_no_permite_otra_eleccion_en_cualquier_estado_no_cerrado",
        "test_permite_varias_elecciones_cerradas_y_una_no_cerrada",
        "test_formulario_rechaza_crear_otra_eleccion_no_cerrada",
    ),
    "apps.reportes.tests.ReportesCSVTests": (
        "test_valor_csv_sanitiza_formulas",
    ),
    "apps.partidos.tests_identidad_candidatos.IdentidadCandidatoTests": (
        "test_dni_y_legajo_identifican_al_mismo_elector",
        "test_cuil_exige_tipo_del_padron_y_no_deriva_desde_dni",
    ),
    "config.test_runner_tests.PruebasCorredorExcelTests": (
        "test_docstring_mapea_metadatos_de_prueba",
        "test_libro_excel_conserva_columnas_y_resultado",
    ),
}

CANTIDAD_PRUEBAS_RELEVANTES = sum(
    len(metodos) for metodos in PRUEBAS_RELEVANTES.values()
)
