# Customer ordering demo

This source copy is based on the supplied Stage 11 package. Run it from a separate folder with a fresh PostgreSQL database whose name ends in `_demo`. The normal application defaults to staff mode. Demo mode enables simulated checkout and labels both the storefront and staff screens.

## Run on Windows

Create an empty PostgreSQL database such as `greenbuffet_client_demo` and make a PostgreSQL login with access to it. Use that login in the `DATABASE_URL` value below. Keep the connection string on your computer.

Open PowerShell in the extracted demo folder. If this folder already has `backend\.venv` and `frontend\node_modules`, go directly to the launch commands. For a fresh extraction with Python and Node already installed:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\frontend
npm ci
cd ..
```

Launch the demo:

```powershell
$env:DATABASE_URL = Read-Host 'PostgreSQL URL for the isolated _demo database'
.\scripts\run-demo.ps1
```

Example URL structure `postgresql+psycopg://USERNAME:PASSWORD@localhost:5432/greenbuffet_client_demo`. Percent-encode any reserved characters in the username or password. The initialization command prints the demo owner’s temporary password on first run. Close the two demo PowerShell windows to stop the demo.

## Present the demo

1. Open `http://localhost:5174/demo`. Select a bowl or burrito, choose add-ons, and start checkout.
2. Try pending, success, or failure in the simulation. A successful order reaches the demo staff Orders and Kitchen views without opening a till. Save the tracking link to revisit the order.
3. Sign in as the demo owner at `http://localhost:5174/login`. Advance the ticket in Kitchen and check the updated customer status. View the sale in Reports and its ingredient movements in Stock.
4. For a clean presentation, point the same launch command at a new empty `_demo` database.

The menu prices come from the Stage 11 seed. The logo and illustrative photos come from the earlier browser demo. Payments generate sample ledger entries and never use a payment provider. The demo has no delivery or messaging integrations. Opening stock and menu prices can be set from the demo staff screens before presenting.

The database uses the existing Stage 11 bootstrap, which creates the demo checkout table. Do not extract this package over a Stage 12 installation. Before public hosting, verify the deployment configuration and confirm menu prices and photo rights.

For regression or load testing, install `requests` in the demo virtual environment and set `GREENBUFFET_TEST_API_URL` and `GREENBUFFET_TEST_PASSWORD` for a disposable database. Run the load script directly when needed. It writes sample sales.
