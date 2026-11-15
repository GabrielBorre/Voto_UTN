"""Previsualiza o aplica acciones en un contenedor y una elección explícitos."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from generar_escenarios import RAIZ, huella, leer_configuracion


def preparar(segmento, accion, eleccion, usuario=None, tipo=None, aplicar=False, raiz=RAIZ,
             solo_estudiantes=False, conservar_autoridades=False):
    if conservar_autoridades and accion not in ('cambios', 'ampliar_cambios'):
        raise ValueError('--conservar-autoridades solo corresponde a cambios de sede.')
    c = leer_configuracion(raiz)
    s = next((s for s in c['segmentos'] if s['carpeta'] == segmento), None)
    if s is None:
        raise ValueError('Segmento no configurado.')
    carpeta = raiz / segmento
    control = json.loads((carpeta / 'control.json').read_text(encoding='utf-8'))
    if control['huella_configuracion'] != huella(c) or control['configuracion'] != c or control['segmento'] != s:
        raise ValueError('Configuración modificada: regenerá los archivos antes de continuar.')
    # Comparar también control.json contra una generación reproducible para impedir reservas alteradas.
    from generar_escenarios import construir
    esperado = json.loads(construir(c, s)['control.json'])
    if control != esperado:
        raise ValueError('El archivo de control fue alterado: regenerá el segmento.')
    for nombre, firma in control['archivos'].items():
        if hashlib.sha256((carpeta / nombre).read_bytes()).hexdigest() != firma:
            raise ValueError(f'Archivo alterado: {nombre}. Regenerá el segmento.')
    return dict(control=control, accion=accion, eleccion=eleccion, usuario=usuario, tipo=tipo, aplicar=aplicar,
                solo_estudiantes=solo_estudiantes, conservar_autoridades=conservar_autoridades)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('accion', choices=('verificar', 'reservar', 'cambios', 'ampliar_cambios', 'justificativos'))
    p.add_argument('--contenedor', required=True)
    p.add_argument('--directorio-app', default='/app', help='Directorio que contiene manage.py dentro del contenedor.')
    p.add_argument('--eleccion', required=True, type=int)
    p.add_argument('--segmento', required=True)
    p.add_argument('--usuario', help='Usuario local con permiso de gestionar autoridades, para reservar.')
    p.add_argument('--tipo', type=int, help='ID de un tipo activo, para justificativos.')
    p.add_argument('--aplicar', action='store_true')
    p.add_argument('--solo-estudiantes', action='store_true', help='Validar únicamente el claustro estudiantil del segmento.')
    p.add_argument('--conservar-autoridades', action='store_true', help='Crear cambios de sede sin excluir ni modificar autoridades existentes, aunque sean solicitantes.')
    args = p.parse_args()
    datos = preparar(args.segmento, args.accion, args.eleccion, args.usuario, args.tipo, args.aplicar,
                     solo_estudiantes=args.solo_estudiantes, conservar_autoridades=args.conservar_autoridades)
    motor = (RAIZ / 'motor_django.py').read_text(encoding='utf-8')
    arranque = ('import os,sys,json; os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings"); '
                'import django; django.setup(); datos=json.load(sys.stdin); '
                'exec(compile(datos.pop("motor"),"motor_escenarios","exec")); '
                'print(json.dumps(ejecutar(datos),ensure_ascii=False,indent=2))')
    # Sin shell, sin archivos persistentes en el contenedor y sin montaje del host.
    subprocess.run(['docker', 'exec', '-i', '-w', args.directorio_app, args.contenedor, 'python', '-c', arranque],
                   input=json.dumps({**datos, 'motor': motor}), text=True, encoding='utf-8', check=True)


if __name__ == '__main__':
    main()
