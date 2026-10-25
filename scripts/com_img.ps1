# Open a circuit via Multisim COM, export schematic PNG and netlist report.
# Must run in 32-bit PowerShell (MSInterface.dll is 32-bit). Keep this file ASCII-only:
# Windows PowerShell 5 reads BOM-less scripts as ANSI/GBK, non-ASCII text breaks parsing.
param([string]$src, [string]$img)
$app = New-Object -ComObject MultisimInterface.MultisimApp
$app.Connect()
try { $c = $app.OpenFile($src); "opened: " + $c.CircuitName } catch { "OpenFile failed: $_ ; " + $app.LastErrorMessage; exit 1 }
try { $r = $c.GetCircuitImage(0, $img + ".0"); "png -> $r" } catch { "image failed: $_" }
try { "netlist:"; $c.ReportNetlist($false, 0, "") } catch { "netlist failed: $_" }
$app.Disconnect()
