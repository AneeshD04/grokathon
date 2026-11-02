# Creates the issue-bus labels. Run from repo root after push:
#   pwsh scripts/setup-github-labels.ps1

$ErrorActionPreference = "Stop"
$repo = "AneeshD04/grokathon"

function Set-Label($name, $color, $description) {
  gh label create $name --repo $repo --color $color --description $description 2>$null
  if ($LASTEXITCODE -ne 0) {
    gh label edit $name --repo $repo --color $color --description $description
  }
}

Set-Label "agent-bus" "0E8A16" "Issue is on the agent messaging bus"
Set-Label "type:task" "1D76DB" "Work that touches files"
Set-Label "type:ping" "C5DEF5" "Chat / mention thread"
Set-Label "type:handoff" "FBCA04" "Delegation to another agent"
Set-Label "type:blocker" "D93F0B" "Someone is stuck"
Set-Label "type:decision" "5319E7" "Conductor needs to call it"

Set-Label "status:inbox" "EDEDED" "Unclaimed"
Set-Label "status:claimed" "C2E0C6" "CLAIM posted"
Set-Label "status:in-progress" "0E8A16" "Branch exists / coding"
Set-Label "status:blocked" "B60205" "Waiting"
Set-Label "status:review" "0052CC" "PR up"
Set-Label "status:done" "000000" "Closed"

Set-Label "lane:aneesh" "BFD4F2" "Conductor"
Set-Label "lane:devanshu" "F9D0C4" "backend/"
Set-Label "lane:kabir" "D4C5F9" "frontend/"
Set-Label "lane:athithan" "C2E0C6" "bots/"
Set-Label "lane:shared" "FEF2C0" "shared/ contracts"

Set-Label "prio:p0" "B60205" "Demo-blocking"
Set-Label "prio:p1" "FBCA04" "Should ship"
Set-Label "prio:p2" "C5DEF5" "Nice"

Write-Host "Labels ready on $repo"
