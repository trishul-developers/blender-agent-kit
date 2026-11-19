#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python "$ScriptDir\..\tools\install.py" @args
exit $LASTEXITCODE
