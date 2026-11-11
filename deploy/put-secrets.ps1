# Copy the API keys from .env into AWS Systems Manager Parameter Store (SecureString,
# encrypted with the AWS-managed key). The EC2 server reads them at boot, so keys never
# live in git, the Docker image or the instance user data.
#
# Run it yourself, from the repo root:   powershell -ExecutionPolicy Bypass -File deploy\put-secrets.ps1
# It never prints the key values. Re-running overwrites them (e.g. after rotating a key).

$ErrorActionPreference = "Stop"
$Region = "ap-southeast-2"
$Profile = "ragg"

$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
$values = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $values[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'") }
}

foreach ($pair in @(@("groq_api_key", "GROQ_API_KEY"), @("anthropic_api_key", "ANTHROPIC_API_KEY"))) {
    $name = "/ragg/" + $pair[0]
    $value = $values[$pair[1]]
    if (-not $value) { Write-Host "$($pair[1]) is empty in .env, skipped"; continue }
    # Pass the value through a temporary file so it never appears on a command line.
    $tmp = New-TemporaryFile
    try {
        @{ Name = $name; Value = $value; Type = "SecureString"; Overwrite = $true;
           Description = "Annual Report Analyst app" } | ConvertTo-Json | Set-Content -Encoding ascii $tmp
        $version = aws ssm put-parameter --cli-input-json "file://$tmp" --region $Region --profile $Profile --query Version --output text
        Write-Host "$name stored (version $version)"
    } finally {
        Remove-Item $tmp -Force
    }
}
