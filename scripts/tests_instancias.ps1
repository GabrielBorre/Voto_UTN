$ErrorActionPreference = "Stop"
$Errores = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot "instancias.ps1"), [ref]$null, [ref]$Errores
)
if ($Errores) {
    throw ($Errores | Out-String)
}
foreach ($Nombre in @("Restaurar-FotoPostgres", "Inicializar-FotoPostgres")) {
    $Funcion = $Ast.Find({
        param($Nodo)
        $Nodo -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $Nodo.Name -eq $Nombre
    }, $true)
    . ([scriptblock]::Create($Funcion.Extent.Text))
}

$FotoPostgres = [System.IO.Path]::GetTempFileName()
$script:Llamadas = New-Object System.Collections.ArrayList
$script:Tablas = "0"
$script:FallarRestauracion = $false

function Ejecutar-Compose {
    param([int]$Numero, [string[]]$Argumentos)
    if ($Numero -ne 2) {
        throw "La restauracion no debe modificar otras instancias."
    }
    [void]$script:Llamadas.Add($Argumentos)
    if ($Argumentos -contains "-Atc") {
        return $script:Tablas
    }
    if ($script:FallarRestauracion -and $Argumentos -contains "--file") {
        throw "Restauracion fallida simulada"
    }
}

try {
    $script:Tablas = "95"
    Inicializar-FotoPostgres
    if ($script:Llamadas.Count -ne 2) {
        throw "Una base existente no debe restaurarse."
    }

    $script:Llamadas.Clear()
    $script:Tablas = "0"
    Inicializar-FotoPostgres
    $Restauraciones = @($script:Llamadas | Where-Object { $_ -contains "--file" })
    if ($Restauraciones.Count -ne 1) {
        throw "Una base vacia debe restaurarse exactamente una vez."
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
    Write-Host "Pruebas de inicializacion y restauracion: correctas."
}
finally {
    if (Test-Path -LiteralPath $FotoPostgres) {
        Remove-Item -LiteralPath $FotoPostgres -Force
    }
}
