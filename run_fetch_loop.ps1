# run_fetch_loop.ps1
#
# Yeh script khud-ba-khud fetch_all_cities command ko har ~65 minute mein
# chalata rehta hai, jab tak sab cities ka data complete na ho jaye.
#
# Kaise chalayein:
#   1. Terminal khol kar project folder mein jao:
#        cd "D:\python projects\Apex_Weather"
#   2. venv activate karo:
#        .venv\Scripts\Activate.ps1
#   3. Is script ko chalao:
#        .\run_fetch_loop.ps1
#
# Rokna ho to Ctrl+C dabao kabhi bhi - progress database mein safe rehta hai,
# dobara chalane par wahi se resume hoga jahan se ruka tha.
#
# Jab terminal mein "Sab chunks, sab cities - complete!" message dikhe,
# to samajh jao poora kaam khatam ho chuka hai - Ctrl+C dabakar loop rok dena.

while ($true) {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - Fetch chala rahe hain..." -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan

    python manage.py fetch_all_cities --batch-size 5

    Write-Host ""
    Write-Host "$(Get-Date -Format 'HH:mm:ss') - Is cycle ka kaam khatam. 65 minute wait kar rahe hain..." -ForegroundColor Yellow
    Write-Host "(Rokna ho to abhi Ctrl+C dabao)" -ForegroundColor Yellow

    Start-Sleep -Seconds 3900
} 