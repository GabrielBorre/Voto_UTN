param(
    [ValidateSet("up", "stop", "start", "down", "ps", "restaurar-foto")]
    [string]$Accion = "up",
    [ValidateRange(1, 3)]
    [int[]]$Instancia = @(1, 2, 3)
)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path $PSScriptRoot -Parent
$Compose = Join-Path $Raiz "docker-compose.instancias.yml"
$DirectorioEntornos = Join-Path $Raiz ".instancias"
$Instancia = @($Instancia | Select-Object -Unique)
$FotoPostgres = Join-Path $DirectorioEntornos "foto-instancia-1.sql"
$DirectorioFoto3 = Join-Path $DirectorioEntornos "foto-instancia-3-v2"

if ($Accion -eq "restaurar-foto" -and ($Instancia.Count -ne 1 -or $Instancia[0] -ne 2)) {
    throw "La accion restaurar-foto requiere -Instancia 2 y reemplaza sus datos."
}

function Nueva-Clave {
    $Bytes = New-Object byte[] 32
    $Generador = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Generador.GetBytes($Bytes)
        return [BitConverter]::ToString($Bytes).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $Generador.Dispose()
    }
}

function Ejecutar-Compose {
    param([int]$Numero, [string[]]$Argumentos)
    $Entorno = Join-Path $DirectorioEntornos "instancia-$Numero.env"
    & docker compose --project-name "voto-utn-$Numero" --env-file $Entorno --file $Compose @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose fallo para voto-utn-$Numero (codigo $LASTEXITCODE)."
    }
}

function Restaurar-FotoPostgres {
    param([int]$Numero = 2, [string]$ArchivoFoto = $FotoPostgres)
    if (-not (Test-Path -LiteralPath $ArchivoFoto -PathType Leaf)) {
        throw "Falta la foto fija de PostgreSQL: $ArchivoFoto. No se inicializara una base diferente."
    }

    $ArchivoContenedor = "/tmp/voto-utn-foto-$([guid]::NewGuid().ToString('N')).sql"
    try {
        Ejecutar-Compose -Numero $Numero -Argumentos @("cp", $ArchivoFoto, "db:$ArchivoContenedor")
        Ejecutar-Compose -Numero $Numero -Argumentos @(
            "exec", "-T", "db", "psql", "-U", "postgres", "-d", "voto_utn",
            "--no-psqlrc", "--set", "ON_ERROR_STOP=1", "--single-transaction",
            "--command", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
            "--file", $ArchivoContenedor
        ) | Out-Null
        Write-Host "Foto fija de PostgreSQL restaurada en voto-utn-$Numero."
    }
    finally {
        Ejecutar-Compose -Numero $Numero -Argumentos @("exec", "-T", "db", "rm", "-f", $ArchivoContenedor)
    }
}

function Validar-FotoInstancia3 {
    $ArchivoHuellas = Join-Path $DirectorioFoto3 "huellas.json"
    if (-not (Test-Path -LiteralPath $ArchivoHuellas -PathType Leaf)) {
        throw "Falta la foto fija de la instancia 3: $ArchivoHuellas. No se modificaran sus datos."
    }
    $Huellas = Get-Content -LiteralPath $ArchivoHuellas -Raw | ConvertFrom-Json
    if ($Huellas.instancia -ne 3) {
        throw "La foto no corresponde a la instancia 3."
    }
    foreach ($Entrada in @(
        @{ Nombre = "postgres.sql"; Huella = $Huellas.postgres_sha256 },
        @{ Nombre = "archivos.tar.gz"; Huella = $Huellas.archivos_sha256 }
    )) {
        $Archivo = Join-Path $DirectorioFoto3 $Entrada.Nombre
        if (-not (Test-Path -LiteralPath $Archivo -PathType Leaf)) {
            throw "Falta un archivo de la foto fija: $Archivo."
        }
        if ((Get-FileHash -LiteralPath $Archivo -Algorithm SHA256).Hash -ne $Entrada.Huella) {
            throw "La foto fija fue alterada: $Archivo. Se cancela la restauracion."
        }
    }
}

function Restaurar-ArchivosInstancia3 {
    $Archivo = Join-Path $DirectorioFoto3 "archivos.tar.gz"
    $Codigo = @'
from pathlib import Path, PurePosixPath
import shutil
import tarfile

raiz = Path('/app')
nombres = {'media', 'generated_qrs'}
with tarfile.open('/foto.tar.gz', 'r:gz') as foto:
    miembros = foto.getmembers()
    for miembro in miembros:
        ruta = PurePosixPath(miembro.name)
        if (ruta.is_absolute() or '..' in ruta.parts or not ruta.parts
                or ruta.parts[0] not in nombres
                or not (miembro.isdir() or miembro.isfile())):
            raise RuntimeError(f'Entrada no permitida en la foto: {miembro.name}')
    for nombre in nombres:
        if not any(m.name == nombre and m.isdir() for m in miembros):
            raise RuntimeError(f'Falta el directorio {nombre} en la foto')
        destino = raiz / nombre
        if not destino.is_dir() or destino.is_symlink():
            raise RuntimeError(f'Volumen de destino no valido: {destino}')
    for nombre in nombres:
        for entrada in (raiz / nombre).iterdir():
            if entrada.is_dir() and not entrada.is_symlink():
                shutil.rmtree(entrada)
            else:
                entrada.unlink()
    foto.extractall(raiz, members=miembros, filter='data')
print('Adjuntos y QR restaurados desde la foto fija de instancia 3.')
'@
    $CodigoBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Codigo))
    Ejecutar-Compose -Numero 3 -Argumentos @(
        "run", "--rm", "--no-deps", "--volume", "${Archivo}:/foto.tar.gz:ro",
        "--entrypoint", "python", "web", "-c",
        "import base64; exec(base64.b64decode('$CodigoBase64'))"
    )
}

function Iniciar-Instancia {
    param([int]$Numero)
    if ($Numero -eq 3) {
        Validar-FotoInstancia3
        Ejecutar-Compose -Numero 3 -Argumentos @("up", "-d", "--wait", "db")
        Ejecutar-Compose -Numero 3 -Argumentos @("stop", "web", "notificaciones")
        Restaurar-FotoPostgres -Numero 3 -ArchivoFoto (Join-Path $DirectorioFoto3 "postgres.sql")
        Restaurar-ArchivosInstancia3
    }
    Ejecutar-Compose -Numero $Numero -Argumentos @("up", "-d", "--no-build")
}

function Instalar-CertificadoCaddy {
    param([int]$Numero)
    $Entorno = Join-Path $DirectorioEntornos "instancia-$Numero.env"
    $Archivo = [System.IO.Path]::GetTempFileName()
    $Certificado = $null
    try {
        $Codigo = 1
        for ($Intento = 1; $Intento -le 30; $Intento++) {
            $PreferenciaAnterior = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $Resultado = & docker compose --project-name "voto-utn-$Numero" --env-file $Entorno --file $Compose cp "proxy:/data/caddy/pki/authorities/local/root.crt" $Archivo 2>&1
                $Codigo = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $PreferenciaAnterior
            }
            if ($Codigo -eq 0) {
                break
            }
            if ($Intento -lt 30) {
                Start-Sleep -Seconds 2
            }
        }
        if ($Codigo -ne 0) {
            throw "No se pudo obtener el certificado de Caddy de voto-utn-$Numero. $($Resultado | Out-String)"
        }

        $Certificado = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($Archivo)
        $RutaCertificado = "Cert:\CurrentUser\Root\$($Certificado.Thumbprint)"
        if (Test-Path $RutaCertificado) {
            Write-Host "Certificado de Caddy de voto-utn-$Numero ya instalado para el usuario actual."
            return
        }

        & certutil -user -addstore Root $Archivo
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudo instalar el certificado de Caddy de voto-utn-$Numero (codigo $LASTEXITCODE)."
        }
        if (-not (Test-Path $RutaCertificado)) {
            throw "El certificado de Caddy de voto-utn-$Numero no aparece en el almacen del usuario actual."
        }
        Write-Host "Certificado de Caddy de voto-utn-$Numero instalado para el usuario actual."
    }
    finally {
        if ($null -ne $Certificado) {
            $Certificado.Dispose()
        }
        Remove-Item -LiteralPath $Archivo -Force
    }
}

foreach ($Numero in $Instancia) {
    $Entorno = Join-Path $DirectorioEntornos "instancia-$Numero.env"
    if (-not (Test-Path $Entorno)) {
        if ($Accion -ne "up") {
            throw "No existe el entorno de voto-utn-$Numero. Ejecutar primero la accion up."
        }
        New-Item -ItemType Directory -Path $DirectorioEntornos -Force | Out-Null
        $Contenido = @(
            "INSTANCIA=$Numero"
            "PUERTO_HTTP=$(8000 + $Numero)"
            "PUERTO_HTTPS=$(8443 + $Numero)"
            "PUERTO_KEYCLOAK=$(8080 + $Numero)"
            "PUERTO_DB=$(5432 + $Numero)"
            "PUERTO_MAILPIT=$(8025 + $Numero)"
            "PUERTO_SMTP=$(1025 + $Numero)"
            "POSTGRES_PASSWORD=admin"
            "DJANGO_SECRET_KEY=admin"
            "CLAVE_FIRMA_QR=admin"
            "KEYCLOAK_ADMIN_PASSWORD=admin"
        )
        [System.IO.File]::WriteAllLines($Entorno, $Contenido)
    }
    Ejecutar-Compose -Numero $Numero -Argumentos @("config", "--quiet")
}

if ($Accion -eq "up") {
    if ($Instancia -contains 3) {
        Validar-FotoInstancia3
    }
    Ejecutar-Compose -Numero $Instancia[0] -Argumentos @("build", "web")
}

foreach ($Numero in $Instancia) {
    switch ($Accion) {
        "up" {
            Iniciar-Instancia -Numero $Numero
            Instalar-CertificadoCaddy -Numero $Numero
        }
        "restaurar-foto" {
            if (-not (Test-Path -LiteralPath $FotoPostgres -PathType Leaf)) {
                throw "Falta la foto fija de PostgreSQL: $FotoPostgres."
            }
            Ejecutar-Compose -Numero 2 -Argumentos @("up", "-d", "--wait", "db")
            Ejecutar-Compose -Numero 2 -Argumentos @("stop", "web", "notificaciones")
            Restaurar-FotoPostgres
            Ejecutar-Compose -Numero 2 -Argumentos @("up", "-d", "--no-build", "web", "notificaciones")
        }
        "start" {
            Ejecutar-Compose -Numero $Numero -Argumentos @("start")
            Instalar-CertificadoCaddy -Numero $Numero
        }
        "ps" { Ejecutar-Compose -Numero $Numero -Argumentos @("ps") }
        "stop" { Ejecutar-Compose -Numero $Numero -Argumentos @("stop") }
        "down" { Ejecutar-Compose -Numero $Numero -Argumentos @("down") }
    }
}
