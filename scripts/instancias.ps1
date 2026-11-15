param(
    [ValidateSet("up", "stop", "start", "down", "ps")]
    [string]$Accion = "up",
    [ValidateRange(1, 3)]
    [int[]]$Instancia = @(1, 2, 3)
)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path $PSScriptRoot -Parent
$Compose = Join-Path $Raiz "docker-compose.instancias.yml"
$DirectorioEntornos = Join-Path $Raiz ".instancias"
$Instancia = @($Instancia | Select-Object -Unique)

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
        "up" { Ejecutar-Compose -Numero $Numero -Argumentos @("up", "-d", "--no-build") }
        "start" { Ejecutar-Compose -Numero $Numero -Argumentos @("start") }
        "ps" { Ejecutar-Compose -Numero $Numero -Argumentos @("ps") }
        "stop" { Ejecutar-Compose -Numero $Numero -Argumentos @("stop") }
        "down" { Ejecutar-Compose -Numero $Numero -Argumentos @("down") }
    }
}
