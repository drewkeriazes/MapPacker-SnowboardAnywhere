# Snowboard sim data fetcher. Downloads everything listed in manifests/<slug>.json
# into <raw root>/<slug>/ (-RawDir, else SBA_RAW_ROOT, else raw\ in this checkout). Safe to re-run: finished files are skipped, partial files are retried.
# Works on Windows PowerShell 5.1 and PowerShell 7, on Windows and on Linux (pwsh, the FEAT-245 build runner). No installs needed.
# FEAT-314: retries follow pipeline/retry.json (shared with the probe, pipeline/retry.py): a download that got no answer,
# a 408, 429 or 5xx, or a bad body is retried up to fetch.tries times after the listed waits (Retry-After respected,
# with jitter; other downloads go on meanwhile). A 4xx is not retried (unless listed for its host) and ends the fetch
# with exit 3 instead of 2. Per host calls / retried / recovered / failed go to $env:SBA_RETRY_LOG when it is set.
param(
    [string]$Slug = "vail",
    [int]$Concurrency = 6,
    # parent folder for raw data; downloads go to <RawDir>\<Slug>. Default: SBA_RAW_ROOT, else raw\ inside the repo.
    [string]$RawDir = "",
    # the manifest to fetch. Default: manifests/<Slug>.json in this checkout (a test passes its own)
    [string]$ManifestPath = ""
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13 } catch { try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {} }

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)   # repo root
if (-not $ManifestPath) { $ManifestPath = Join-Path (Join-Path $root "manifests") "$Slug.json" }
if (-not $RawDir) { $RawDir = if ($env:SBA_RAW_ROOT) { $env:SBA_RAW_ROOT } else { Join-Path $root "raw" } }
$rawDir = Join-Path $RawDir $Slug
if (-not (Test-Path $manifestPath)) { Write-Host "Manifest not found: $manifestPath" -ForegroundColor Red; exit 1 }
New-Item -ItemType Directory -Force -Path $rawDir | Out-Null
$log = Join-Path $rawDir "fetch_log.txt"
$rules = Get-Content -Raw -Path (Join-Path $PSScriptRoot "retry.json") | ConvertFrom-Json
function IsTransient($code, $h) {
    if ($code -lt 400 -or $code -ge 500 -or @($rules.transient_status) -contains $code) { return $true }
    $one = $rules.one_off_4xx.PSObject.Properties[$h]
    return ($one -and @($one.Value) -contains $code)
}
function RetryWait($k, $after) {
    $w = @($rules.fetch.waits_s); $s = [double]$w[[Math]::Min($k, $w.Count) - 1]
    if ($after) { $s = [Math]::Max($s, [Math]::Min([double]$after, [double]$rules.max_retry_after_s)) }
    return $s * (1 + [double]$rules.jitter * (2 * (Get-Random -Minimum 0.0 -Maximum 1.0) - 1))
}
function Log($msg) { $line = "{0}  {1}" -f (Get-Date -Format "HH:mm:ss"), $msg; Write-Host $line; Add-Content -Path $log -Value $line }

# Environment notes for the processing side
$envFile = Join-Path $rawDir "env.txt"
$envInfo = @()
$envInfo += "os=" + [System.Environment]::OSVersion.VersionString
$envInfo += "ps=" + $PSVersionTable.PSVersion.ToString()
foreach ($exe in @("python", "py", "node", "npm", "git")) {
    $cmd = Get-Command $exe -ErrorAction SilentlyContinue
    if ($cmd) {
        try { $v = & $exe --version 2>&1 | Select-Object -First 1 } catch { $v = "?" }
        $envInfo += "$exe=" + $cmd.Source + " (" + $v + ")"
    } else { $envInfo += "$exe=missing" }
}
$envInfo | Set-Content -Path $envFile

$manifest = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json
$items = @($manifest.items)
Log "Manifest ${Slug}: $($items.Count) items -> $rawDir"

Add-Type -AssemblyName System.Net.Http
$handler = New-Object System.Net.Http.HttpClientHandler
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$client = New-Object System.Net.Http.HttpClient($handler)
$client.Timeout = [TimeSpan]::FromMinutes(15)
$client.DefaultRequestHeaders.TryAddWithoutValidation("User-Agent", "snowboard-sim-fetch/0.1 (personal project)") | Out-Null

# Per-host politeness: how many requests may be in flight at once
function HostLimit($url) {
    if ($url -like "*nationalmap.gov*") { return 2 }
    if ($url -like "*planetarycomputer*") { return 3 }
    if ($url -like "*overpass-api.de*") { return 1 }
    return $Concurrency
}

# Build the work list, skipping finished files
$work = New-Object System.Collections.Generic.List[object]
$skipped = 0
foreach ($it in $items) {
    # the manifest's paths use /; the platform's own separator, so the .NET file calls below get a real path on
    # Linux too (a \ there is part of the file name)
    $dest = Join-Path $rawDir ($it.path -replace "/", [System.IO.Path]::DirectorySeparatorChar)
    if ((Test-Path $dest) -and ((Get-Item $dest).Length -gt 0)) { $skipped++; continue }
    $alts = @(); if ($it.alts) { $alts = @($it.alts) }
    $work.Add([pscustomobject]@{ url = $it.url; path = $it.path; dest = $dest; method = $it.method; body = $it.body; tries = 0; alts = $alts; due = [datetime]::MinValue; host0 = ([Uri]$it.url).Host })
}
Log "Skipping $skipped already downloaded; $($work.Count) to fetch"

$inflight = @{}      # task -> item
$hostCounts = @{}
$done = 0; $failed = New-Object System.Collections.Generic.List[object]; $bytes = 0L; $refused = 0
$tally = @{}     # host -> calls, retried, recovered, failed (FEAT-314)
function Count($it, $ok, $retries) {     # $retries: how many times it was retried
    $h = $it.host0
    if (-not $script:tally.ContainsKey($h)) { $script:tally[$h] = [ordered]@{ calls = 0; retried = 0; recovered = 0; failed = 0 } }
    $t = $script:tally[$h]; $t.calls++
    if ($retries -gt 0) { $t.retried++; if ($ok) { $t.recovered++ } }
    if (-not $ok) { $t.failed++ }
}
$queue = New-Object System.Collections.Generic.Queue[object]
foreach ($w in $work) { $queue.Enqueue($w) }
$deferred = New-Object System.Collections.Generic.List[object]
$lastReport = Get-Date

function StartItem($it) {
    $h = ([Uri]$it.url).Host
    if ($it.method -eq "POST") {
        $content = New-Object System.Net.Http.StringContent($it.body, [System.Text.Encoding]::UTF8, "application/x-www-form-urlencoded")
        $task = $client.PostAsync($it.url, $content)
    } else {
        # DATA-021: the 3DEP ImageServer drops some exports without answering; a healthy 1500 px chunk takes
        # about 10 s, so give up on it after 3 min and retry instead of holding one of its two slots for 15 min
        $limit = if ($it.url -like "*nationalmap.gov*") { [TimeSpan]::FromMinutes(3) } else { $client.Timeout }
        $cts = New-Object System.Threading.CancellationTokenSource($limit)
        $task = $client.GetAsync($it.url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead, $cts.Token)
    }
    $script:inflight[$task] = $it
    if (-not $script:hostCounts.ContainsKey($h)) { $script:hostCounts[$h] = 0 }
    $script:hostCounts[$h]++
}

while ($queue.Count -gt 0 -or $inflight.Count -gt 0 -or $deferred.Count -gt 0) {
    # fill in-flight slots, respecting per-host limits
    $n = $queue.Count
    for ($k = 0; $k -lt $n -and $inflight.Count -lt $Concurrency; $k++) {
        $it = $queue.Dequeue()
        if ((Get-Date) -lt $it.due) { $deferred.Add($it); continue }    # waiting before its retry
        $h = ([Uri]$it.url).Host
        $cur = 0; if ($hostCounts.ContainsKey($h)) { $cur = $hostCounts[$h] }
        if ($cur -ge (HostLimit $it.url)) { $deferred.Add($it); continue }
        StartItem $it
    }
    foreach ($d in $deferred) { $queue.Enqueue($d) }
    $deferred.Clear()

    if ($inflight.Count -eq 0) { Start-Sleep -Milliseconds 200; continue }

    $tasks = [System.Threading.Tasks.Task[]]@($inflight.Keys)
    $idx = [System.Threading.Tasks.Task]::WaitAny($tasks, 2000)
    if ($idx -lt 0) {
        if (((Get-Date) - $lastReport).TotalSeconds -ge 15) {
            Log ("  ... {0} done, {1} in flight, {2} queued, {3:N0} MB" -f $done, $inflight.Count, $queue.Count, ($bytes / 1MB)); $lastReport = Get-Date
        }
        continue
    }
    $task = $tasks[$idx]
    $it = $inflight[$task]
    $inflight.Remove($task)
    $h = ([Uri]$it.url).Host; $hostCounts[$h]--
    $ok = $false; $err = ""; $code = 0; $after = $null
    try {
        if ($task.IsFaulted) { throw $task.Exception.InnerException }
        if ($task.IsCanceled) { throw "timed out" }
        $resp = $task.Result
        $code = [int]$resp.StatusCode
        if (-not $resp.IsSuccessStatusCode) {
            if ($resp.Headers.RetryAfter -and $resp.Headers.RetryAfter.Delta) { $after = $resp.Headers.RetryAfter.Delta.TotalSeconds }
            $resp.Dispose()
            throw ("HTTP " + $code)
        }
        $tmp = $it.dest + ".part"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $it.dest) | Out-Null
        $fs = [System.IO.File]::Create($tmp)
        try { $resp.Content.CopyToAsync($fs).Wait() } finally { $fs.Close() }
        $resp.Dispose()
        $len = (Get-Item $tmp).Length
        if ($len -le 0) { throw "empty response" }
        # Overpass returns 200 with an HTML/remark body when it fails; sanity check JSON
        if ($it.path -like "osm/*") {
            $head = [System.IO.File]::ReadAllText($tmp).Substring(0, [Math]::Min(200, $len))
            if ($head -notmatch '"elements"' -and $head -notmatch '"version"') { throw "overpass error: $head" }
        }
        if (Test-Path $it.dest) { Remove-Item $it.dest -Force }
        Rename-Item -Path $tmp -NewName (Split-Path -Leaf $it.dest)
        $bytes += $len; $done++; $ok = $true
    } catch {
        $err = $_.Exception.Message
        if (Test-Path ($it.dest + ".part")) { Remove-Item ($it.dest + ".part") -Force }
    }
    if ($ok) { Count $it $true $it.tries }
    else {
        $it.tries++
        $retry = IsTransient $code $h
        if ($retry -and $it.alts.Count -gt 0) {
            # rotate to the next mirror
            $next = $it.alts[0]; $it.alts = @($it.alts | Select-Object -Skip 1) + @($it.url); $it.url = $next
        }
        if ($retry -and $it.tries -lt [int]$rules.fetch.tries) {
            $s = RetryWait $it.tries $after
            Log ("  retry {0} ({1}) in {2:N0} s after error: {3} -> {4}" -f $it.path, $it.tries, $s, $err, ([Uri]$it.url).Host)
            $it.due = (Get-Date).AddSeconds($s)
            $queue.Enqueue($it)
        } else {
            if (-not $retry) { $refused++; $err += " (a 4xx: not retried)" }
            Log ("  FAILED {0}: {1}" -f $it.path, $err)
            Count $it $false ($it.tries - 1)
            $failed.Add($it)
        }
    }
    if (((Get-Date) - $lastReport).TotalSeconds -ge 15) {
        Log ("  ... {0} done, {1} in flight, {2} queued, {3:N0} MB" -f $done, $inflight.Count, $queue.Count, ($bytes / 1MB)); $lastReport = Get-Date
    }
}

Log ("Finished: {0} downloaded ({1:N0} MB), {2} skipped, {3} failed" -f $done, ($bytes / 1MB), $skipped, $failed.Count)
foreach ($h in $tally.Keys) {
    $t = $tally[$h]
    if ($t.retried) { Log ("  {0}: {1} downloads, {2} retried, {3} recovered, {4} failed" -f $h, $t.calls, $t.retried, $t.recovered, $t.failed) }
    if ($env:SBA_RETRY_LOG) {
        $line = [ordered]@{ tool = "fetch"; host = $h; calls = $t.calls; retried = $t.retried; recovered = $t.recovered; failed = $t.failed }
        Add-Content -Path $env:SBA_RETRY_LOG -Value ($line | ConvertTo-Json -Compress)
    }
}
if ($failed.Count -gt 0) {
    Log "Failed items (re-run this script to retry them):"
    foreach ($f in $failed) { Log ("  " + $f.path) }
    if ($refused -gt 0) { exit 3 }
    exit 2
}
"complete $(Get-Date -Format o)" | Set-Content -Path (Join-Path $rawDir "FETCH_COMPLETE.txt")
exit 0
