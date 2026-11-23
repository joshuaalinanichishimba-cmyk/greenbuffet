# Stage 12 Windows deployment

The Windows build serves the Vue screens, REST API, and kitchen WebSocket from one process. It uses the existing PostgreSQL database specified in this installation's `backend\.env`.

## Start on the POS PC

From the POS project directory, with the existing virtual environment and `backend\.env` in place:

```powershell
.\scripts\build-pos.ps1
.\scripts\run-pos.ps1
```

Open [the POS](http://127.0.0.1:8088/) in a browser on that PC. In another PowerShell window, check the application and database:

```powershell
Invoke-RestMethod http://127.0.0.1:8088/api/v1/health
```

The expected fields are `status = ok`, `database = connected`, and `environment = production`. Press Ctrl+C in the server window to stop the foreground run.

## Start with Windows

After the foreground check, stop the foreground server. Open Windows PowerShell as Administrator in the POS project directory and run:

```powershell
.\scripts\install-pos-startup.ps1
Get-ScheduledTask -TaskName 'Green Buffet POS'
```

Use the Windows account that can read this installation, access its Python environment, and write its local backups and uploads. Use its account password for the credential prompt. The task starts on boot, runs with limited privileges, and restarts after a server failure. Confirm the health check after restarting Windows during a maintenance window.

## Access from the restaurant Wi-Fi

Use a stable LAN hostname and a PEM certificate and key whose certificate the staff devices trust. The hostname must match the certificate. Run the foreground command to confirm HTTPS before registering the startup task with the same arguments:

```powershell
.\scripts\run-pos.ps1 -ListenAddress 0.0.0.0 `
    -TlsCertificate 'D:\POS-Certificates\pos.crt' -TlsKey 'D:\POS-Certificates\pos.key'
```

If needed, allow TCP 8088 for the Windows Private profile from the local subnet. Open the HTTPS URL on the till and kitchen devices and confirm login and ticket updates. The default startup is available on the POS PC.

## Apply a code update

Get the approved Git revision on the Windows copy, stop the startup task during a maintenance window, build the frontend, and restart the task. Check `/api/v1/health` and print a test receipt on the Windows device before opening the till. Development still runs with `scripts\run.ps1`.

Before trading, verify a restore into a separate test database, enter approved menu prices, count the opening stock, and confirm payroll settings. Run the load script explicitly against a disposable database only.
