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
    if (-not (Test-Path -LiteralPath $FotoPostgres -PathType Leaf)) {
        throw "Falta la foto fija de PostgreSQL: $FotoPostgres. No se inicializara una base diferente."
    }

    $ArchivoContenedor = "/tmp/voto-utn-foto-$([guid]::NewGuid().ToString('N')).sql"
    try {
        Ejecutar-Compose -Numero 2 -Argumentos @("cp", $FotoPostgres, "db:$ArchivoContenedor")
        Ejecutar-Compose -Numero 2 -Argumentos @(
            "exec", "-T", "db", "psql", "-U", "postgres", "-d", "voto_utn",
            "--no-psqlrc", "--set", "ON_ERROR_STOP=1", "--single-transaction",
            "--command", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
            "--file", $ArchivoContenedor
        ) | Out-Null
        Write-Host "Foto fija de PostgreSQL restaurada en voto-utn-2."
    }
    finally {
        Ejecutar-Compose -Numero 2 -Argumentos @("exec", "-T", "db", "rm", "-f", $ArchivoContenedor)
    }
}

function Inicializar-FotoPostgres {
    Ejecutar-Compose -Numero 2 -Argumentos @("up", "-d", "--wait", "db")
    $Tablas = Ejecutar-Compose -Numero 2 -Argumentos @(
        "exec", "-T", "db", "psql", "-U", "postgres", "-d", "voto_utn",
        "--no-psqlrc", "-Atc",
        "SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND c.relkind IN ('r', 'p');"
    )
    if ([int]::Parse(($Tablas -join "").Trim()) -eq 0) {
        Restaurar-FotoPostgres
    }
    else {
        Write-Host "Base existente en voto-utn-2: se conservan sus datos."
    }
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
            "POSTGRES_PASSWORD=$(Nueva-Clave)"
            "DJANGO_SECRET_KEY=$(Nueva-Clave)"
            "CLAVE_FIRMA_QR=$(Nueva-Clave)"
            "KEYCLOAK_ADMIN_PASSWORD=$(Nueva-Clave)"
        )
        [System.IO.File]::WriteAllLines($Entorno, $Contenido)
    }
    Ejecutar-Compose -Numero $Numero -Argumentos @("config", "--quiet")
}

if ($Accion -eq "up") {
    Ejecutar-Compose -Numero $Instancia[0] -Argumentos @("build", "web")
}

foreach ($Numero in $Instancia) {
    switch ($Accion) {
        "up" {
            if ($Numero -eq 2) {
                Inicializar-FotoPostgres
            }
            Ejecutar-Compose -Numero $Numero -Argumentos @("up", "-d", "--no-build")
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
