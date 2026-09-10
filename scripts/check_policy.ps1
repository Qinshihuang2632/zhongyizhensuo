$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$k = 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy'
if (Test-Path $k) {
  Get-ItemProperty $k | Select-Object VerifiedAndReputablePolicyState | Format-List
} else {
  Write-Output 'CI Policy key not found'
}
try {
  Get-WinEvent -LogName 'Microsoft-Windows-CodeIntegrity/Operational' -MaxEvents 4 |
    ForEach-Object { '{0}  Id={1}  {2}' -f $_.TimeCreated, $_.Id, (($_.Message -split "`n")[0]) }
} catch {
  Write-Output 'eventlog read fail'
}
