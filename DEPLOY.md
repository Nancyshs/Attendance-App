# Deploying on Windows Server (no Docker)

Target: Windows Server 2019/2022, MySQL 8, Python 3.12+, ~50 trainees scanning at the same time.

## 1. Prerequisites
- **Python 3.12+** (tick "Add to PATH").
- **MySQL 8** (MySQL Installer, "Server only"). Keep the service name (`MySQL80`).
- **Node.js 20+** only on the machine that builds the frontend (can be your laptop: copy `frontend\dist` afterwards).
- [NSSM](https://nssm.cc) to run the app as a service.

## 2. Database
In MySQL Workbench (or `mysql.exe`) as root:
```sql
CREATE DATABASE attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'attendance'@'localhost' IDENTIFIED BY 'A-long-random-password';
GRANT ALL PRIVILEGES ON attendance.* TO 'attendance'@'localhost';
```
In `my.ini` set `max_connections = 200` (the app uses at most `workers x (DB_POOL_SIZE + DB_MAX_OVERFLOW)` = 4 x 20 = 80).

## 3. Install the app
```powershell
cd E:\Attendance_App\backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

cd ..\frontend
npm ci
npm run build            # produces frontend\dist (served by the backend)

cd ..
copy .env.example .env   # then edit: SECRET_KEY, DATABASE_URL, PUBLIC_URL
cd backend
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m scripts.seed --username admin    # creates admin + default survey template
```
**Set `PUBLIC_URL` to the final address before printing badges** - it is encoded in each QR.
The same address is encoded in each session's survey QR (/s/<token>), so phones must be able to open it. Re-run seed after upgrading once to add the standard session survey (8 criteria + 2 open questions).

## 4. Run as a service
Elevated PowerShell:
```powershell
.\deploy\install_service.ps1 -Nssm C:\tools\nssm.exe -Port 8000 -Workers 4
```
Check `http://SERVER:8000/api/health/ready` returns `{"status":"ready","database":"up"}`. Logs: `logs\service.*.log`.

## 5. HTTPS (required for phone cameras only)
- **USB QR readers work over plain HTTP** (they type text like a keyboard).
- Phone camera scanning and the trainee phone portal need **HTTPS** (browsers block the camera on HTTP).
  Options:
  1. **Internal server, internal CA / self-signed**: create a certificate for the server name, install the root on staff phones, then
     `.\deploy\run_server.ps1 -CertFile C:\certs\site.crt -KeyFile C:\certs\site.key` (pass the same to `install_service.ps1`).
  2. **Public DNS name**: use [win-acme](https://www.win-acme.com) for a free Let's Encrypt cert, with IIS as front door
     (see `deploy\web.config`; needs URL Rewrite + ARR). Then set `TRUST_PROXY=true`.
- Open the firewall for the HTTPS port only to your network.

## 6. Backups
1. Create `C:\ProgramData\attendance\backup.cnf` (restrict permissions to Administrators/SYSTEM):
   ```
   [client]
   user=attendance
   password=A-long-random-password
   ```
2. Schedule `deploy\backup.ps1` nightly (command is in the script header). It dumps the DB, zips photos, keeps 30 days.
3. Test a restore once: `mysql attendance < attendance_xxx.sql`.

## 7. Day-to-day
- Sign in as admin -> Trainees: add/import trainees -> **Print badges** (PDF, 4 per A4).
- Schedule: add the day's lectures (or import Excel). Surveys open automatically after each lecture ends (Settings).
- Scanner page: USB reader (cursor in the field, scan) or "Start camera". Mixed use is fine.
- Upgrades: stop service, replace files, `pip install -r requirements.txt`, `npm run build`, `alembic upgrade head`, start service.

## Notes on concurrency
- Check-in/out are decided by the database (unique key + atomic update), so double-scans or two scanners can't create duplicates.
- Each scan carries a client id: a retry/replay returns the stored result instead of recording again.
- Scanner stores scans locally if the network drops and replays them automatically.
- Workers share the port; the login rate-limiter and the 15 s settings cache are per process (harmless).
- Load test (against a **test** DB only): `python -m scripts.load_test --yes`.

