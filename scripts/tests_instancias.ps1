$ErrorActionPreference = "Stop"
$Errores = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot "instancias.ps1"), [ref]$null, [ref]$Errores
)
if ($Errores) {
    throw ($Errores | Out-String)
}
foreach ($Nombre in @("Restaurar-FotoPostgres", "Inicializar-FotoInstancia2", "Validar-FotoInstancia3", "Restaurar-ArchivosInstancia3", "Iniciar-Instancia")) {
    $Funcion = $Ast.Find({
        param($Nodo)
        $Nodo -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $Nodo.Name -eq $Nombre
    }, $true)
    . ([scriptblock]::Create($Funcion.Extent.Text))
}

$FotoPostgres = [System.IO.Path]::GetTempFileName()
$FotoPostgresInstancia2 = [System.IO.Path]::GetTempFileName()
$script:Llamadas = New-Object System.Collections.ArrayList
$script:FallarRestauracion = $false
$script:InstanciaEsperada = 2
$script:EstadoEsquema = "false"

function Ejecutar-Compose {
    param([int]$Numero, [string[]]$Argumentos)
    if ($Numero -ne $script:InstanciaEsperada) {
        throw "La restauracion no debe modificar otras instancias."
    }
    [void]$script:Llamadas.Add($Argumentos)
    if ($Argumentos -contains "--command" -and ($Argumentos -join " ") -like "*to_regclass*") {
        return $script:EstadoEsquema
    }
    if ($script:FallarRestauracion -and $Argumentos -contains "--file") {
        throw "Restauracion fallida simulada"
    }
}

try {
    Restaurar-FotoPostgres
    $Restauraciones = @($script:Llamadas | Where-Object { $_ -contains "--file" })
    if ($Restauraciones.Count -ne 1) {
        throw "La restauracion explicita debe ejecutarse exactamente una vez."
    }
    $Comando = $Restauraciones[0]
    if ($Comando -notcontains "--single-transaction" -or $Comando -notcontains "ON_ERROR_STOP=1") {
        throw "La restauracion debe ser atomica y detenerse ante errores."
    }
    if ($Comando -notcontains "DROP SCHEMA public CASCADE; CREATE SCHEMA public;") {
        throw "La restauracion debe reemplazar el esquema, no mezclar datos."
    }

    $script:Llamadas.Clear()
    $script:FallarRestauracion = $true
    $ErrorPropagado = $false
    try { Restaurar-FotoPostgres }
    catch { $ErrorPropagado = $_.Exception.Message -eq "Restauracion fallida simulada" }
    if (-not $ErrorPropagado -or $script:Llamadas[-1] -notcontains "rm") {
        throw "Un error debe propagarse y limpiar la copia temporal."
    }

    Remove-Item -LiteralPath $FotoPostgres
    $script:Llamadas.Clear()
    $FotoAusente = $false
    try { Restaurar-FotoPostgres }
    catch { $FotoAusente = $_.Exception.Message -like "Falta la foto fija*" }
    if (-not $FotoAusente -or $script:Llamadas.Count -ne 0) {
        throw "Sin foto no debe intentarse modificar la base."
    }
    $script:FallarRestauracion = $false
    Write-Host "Pruebas de restauracion: correctas."

    Set-Content -LiteralPath $FotoPostgresInstancia2 -Value "Foto PostgreSQL de instancia 2"
    $script:Llamadas.Clear()
    Inicializar-FotoInstancia2
    if (@($script:Llamadas | Where-Object { $_ -contains "--file" }).Count -ne 1) {
        throw "Una base nueva de instancia 2 debe restaurar su foto actual."
    }

    $script:EstadoEsquema = "true"
    $script:Llamadas.Clear()
    Inicializar-FotoInstancia2
    if (@($script:Llamadas | Where-Object { $_ -contains "--file" }).Count -ne 0) {
        throw "Una base existente de instancia 2 no debe reemplazarse."
    }
    $script:EstadoEsquema = "false"
    Remove-Item -LiteralPath $FotoPostgresInstancia2
    $script:Llamadas.Clear()
    $FotoAusente = $false
    try { Inicializar-FotoInstancia2 }
    catch { $FotoAusente = $_.Exception.Message -like "Falta la foto fija*" }
    if (-not $FotoAusente -or @($script:Llamadas | Where-Object { $_ -contains "--file" }).Count -ne 0) {
        throw "Una base nueva sin foto debe detenerse antes de levantar la aplicacion."
    }
    $script:Llamadas.Clear()
    try { Iniciar-Instancia -Numero 2 }
    catch { $FotoAusente = $_.Exception.Message -like "Falta la foto fija*" }
    if (-not $FotoAusente -or @($script:Llamadas | Where-Object { $_ -contains "--no-build" }).Count -ne 0) {
        throw "Sin foto, el inicio de instancia 2 debe detenerse antes de levantar la aplicacion."
    }

    Set-Content -LiteralPath $FotoPostgresInstancia2 -Value "Foto PostgreSQL de instancia 2"
    $script:Llamadas.Clear()
    Iniciar-Instancia -Numero 2
    if (@($script:Llamadas | Where-Object { $_ -contains "--file" }).Count -ne 1 -or
        @($script:Llamadas | Where-Object { $_ -contains "--no-build" }).Count -ne 1) {
        throw "El inicio de una instancia 2 nueva debe restaurar la foto antes de levantar los servicios."
    }

    $script:FallarRestauracion = $false
    foreach ($Numero in @(1, 2)) {
        $script:InstanciaEsperada = $Numero
        $script:EstadoEsquema = "true"
        $script:Llamadas.Clear()
        Iniciar-Instancia -Numero $Numero
        if (@($script:Llamadas | Where-Object { $_ -contains "--no-build" }).Count -ne 1) {
            throw "up debe levantar los servicios de la instancia."
        }
        if ($Numero -eq 1 -and $script:Llamadas.Count -ne 1) {
            throw "up de instancia 1 no debe ejecutar la inicializacion de la foto."
        }
        if ($Numero -eq 2 -and @($script:Llamadas | Where-Object { $_ -contains "--file" }).Count -ne 0) {
            throw "up de una instancia 2 existente no debe restaurar la foto."
        }
    }

    $DirectorioFoto3 = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $DirectorioFoto3 | Out-Null
    $script:InstanciaEsperada = 3
    $script:Llamadas.Clear()
    $FotoAusente = $false
    try { Iniciar-Instancia -Numero 3 }
    catch { $FotoAusente = $_.Exception.Message -like "Falta la foto fija*" }
    if (-not $FotoAusente -or $script:Llamadas.Count -ne 0) {
        throw "up de instancia 3 sin foto no debe modificar contenedores ni datos."
    }

    $Sql3 = Join-Path $DirectorioFoto3 "postgres.sql"
    $Archivos3 = Join-Path $DirectorioFoto3 "archivos.tar.gz"
    Set-Content -LiteralPath $Sql3 -Value "Foto PostgreSQL de prueba"
    Set-Content -LiteralPath $Archivos3 -Value "Foto de archivos de prueba"
    $Huellas = @{
        instancia = 3
        postgres_sha256 = (Get-FileHash -LiteralPath $Sql3 -Algorithm SHA256).Hash
        archivos_sha256 = (Get-FileHash -LiteralPath $Archivos3 -Algorithm SHA256).Hash
    }
    $Huellas | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $DirectorioFoto3 "huellas.json")
    Iniciar-Instancia -Numero 3
    $Restauraciones = @($script:Llamadas | Where-Object { $_ -contains "--file" })
    $Archivos = @($script:Llamadas | Where-Object { $_ -contains "--volume" })
    if ($Restauraciones.Count -ne 1 -or $Archivos.Count -ne 1) {
        throw "up de instancia 3 debe restaurar PostgreSQL y archivos exactamente una vez."
    }
    if ($script:Llamadas[1][0] -ne "stop" -or $script:Llamadas[1] -notcontains "notificaciones") {
        throw "La restauracion debe detener los escritores antes de modificar datos."
    }
    if ($script:Llamadas[-1] -notcontains "--no-build") {
        throw "Los servicios deben arrancar despues de restaurar todos los datos."
    }
    if ($Archivos[0] -notcontains "${Archivos3}:/foto.tar.gz:ro") {
        throw "La foto de archivos debe montarse en solo lectura."
    }
    $script:Llamadas.Clear()
    Iniciar-Instancia -Numero 3
    if (@($script:Llamadas | Where-Object { $_ -contains "--file" }).Count -ne 1) {
        throw "Cada up debe restaurar la misma foto, aunque ya existan datos."
    }

    $script:Llamadas.Clear()
    $script:FallarRestauracion = $true
    $ErrorPropagado = $false
    try { Iniciar-Instancia -Numero 3 }
    catch { $ErrorPropagado = $_.Exception.Message -eq "Restauracion fallida simulada" }
    if (-not $ErrorPropagado -or @($script:Llamadas | Where-Object { $_ -contains "--no-build" }).Count -ne 0) {
        throw "Una restauracion fallida debe dejar los servicios escritores detenidos."
    }
    $script:FallarRestauracion = $false

    foreach ($Archivo in @($Sql3, $Archivos3)) {
        $Original = Get-Content -LiteralPath $Archivo -Raw
        Add-Content -LiteralPath $Archivo -Value "Alterado"
        $script:Llamadas.Clear()
        $FotoAlterada = $false
        try { Iniciar-Instancia -Numero 3 }
        catch { $FotoAlterada = $_.Exception.Message -like "La foto fija fue alterada*" }
        if (-not $FotoAlterada -or $script:Llamadas.Count -ne 0) {
            throw "Una foto alterada debe rechazarse antes de modificar datos."
        }
        [System.IO.File]::WriteAllText($Archivo, $Original)
    }
    Write-Host "Pruebas de foto fija y up de instancia 3: correctas."
}
finally {
    if (Test-Path -LiteralPath $FotoPostgres) {
        Remove-Item -LiteralPath $FotoPostgres -Force
    }
    if (Test-Path -LiteralPath $FotoPostgresInstancia2) {
        Remove-Item -LiteralPath $FotoPostgresInstancia2 -Force
    }
    if ($DirectorioFoto3 -and (Test-Path -LiteralPath $DirectorioFoto3)) {
        foreach ($Nombre in @("postgres.sql", "archivos.tar.gz", "huellas.json")) {
            $Archivo = Join-Path $DirectorioFoto3 $Nombre
            if (Test-Path -LiteralPath $Archivo) {
                Remove-Item -LiteralPath $Archivo -Force
            }
        }
        Remove-Item -LiteralPath $DirectorioFoto3
    }
}
