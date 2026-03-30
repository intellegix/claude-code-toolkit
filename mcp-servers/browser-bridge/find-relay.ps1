Get-CimInstance Win32_Process -Filter 'name="node.exe"' | Where-Object {$_.CommandLine -like '*server.js*'} | Select-Object ProcessId,CommandLine | Format-List
