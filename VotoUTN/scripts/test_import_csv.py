import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede
from apps.parametros.models import Departamento, Sede
from apps.padron.services import validar_csv_padron

# Crear recursos mínimos para la prueba
eleccion = Eleccion.objects.create(nombre='Elec Test', estado=Eleccion.Estado.BORRADOR)
claustro = EleccionClaustro.objects.create(eleccion=eleccion, nombre='Claustro Test')

departamento = Departamento.objects.create(codigo='DEP1', nombre='Departamento 1', activo=True)
sede = Sede.objects.create(nombre='Sede1', activa=True)
config = EleccionClaustroDepartamento.objects.create(eleccion_claustro=claustro, departamento=departamento)
EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=config, sede=sede)

# CSV con las columnas solicitadas en el orden pedido por el usuario
csv_text = (
    'DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde asiste,Nivel\n'
    '12345678,LG001,Juan,Perez,DEP1,juan.perez@example.com,No,DEP1,Sede1,Pregrado\n'
)

resultado = validar_csv_padron(csv_text.encode('utf-8'), claustro)
print('Filas:', resultado.filas)
print('Errores:', resultado.errores)

# Mantener los objetos creados en la BD para inspección si es necesario
print('Prueba completada')
