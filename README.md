# DB Backup Utility

A command-line tool for backing up and restoring databases across multiple database management systems (DBMS). Supports SQLite, MySQL, PostgreSQL, and MongoDB, with compression, local and cloud storage, retention policies, Slack notifications, and scheduling.

This project was built as a learning exercise in Python CLI development, object-oriented design, and working with real-world database tooling.

---

## Features

- **Multiple DBMS support**: SQLite, MySQL, PostgreSQL, MongoDB
- **Connection testing**: validates credentials before attempting a backup
- **Compression**: backups are gzip-compressed (SQL/SQLite) or zipped (MongoDB) by default
- **Local storage**: backups saved to a configurable local directory
- **Cloud storage**: optional upload to any S3-compatible storage service (AWS S3, Cloudflare R2, Backblaze B2, MinIO, etc.)
- **Retention/cleanup**: automatically delete old backups, keeping only the N most recent per database
- **Logging**: every backup/restore attempt is logged with timestamps, duration, and status, both to console and to a log file
- **Slack notifications**: optional success/failure messages sent to a Slack channel via webhook
- **Restore operations**: restore a database from any backup file
- **Selective backup/restore**:
  - MySQL/PostgreSQL: back up specific tables using `--tables`
  - MongoDB: restore a single collection from any full backup using `--collection`
- **Scheduling**: built-in `--schedule` flag for simple recurring backups, plus guidance for OS-level scheduling (Windows Task Scheduler / cron) for production use

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/khelifaahmed/DataBase-BackUp-Utility
cd DataBase-BackUp-Utility
```

### 2. Set up a virtual environment (recommended)

```bash
python -m venv venv
source venv/Scripts/activate   # Windows (Git Bash)
# or: source venv/bin/activate  # macOS/Linux
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs the Python-level dependencies (`pymysql`, `psycopg2-binary`, `pymongo`, `requests`, `boto3`, `schedule`). Note that some DBMS types also require external command-line tools — see below.

---

## Prerequisites by Database Type

| Database   | Requires                                                                 | Notes |
|------------|---------------------------------------------------------------------------|-------|
| SQLite     | Nothing extra (built into Python)                                        | Works out of the box |
| MySQL      | `mysqldump` / `mysql` CLI tools on your PATH                             | Comes bundled with MySQL Server, MariaDB, or XAMPP |
| PostgreSQL | `pg_dump` / `psql` CLI tools on your PATH                                | Install from [postgresql.org/download](https://www.postgresql.org/download/) |
| MongoDB    | `mongodump` / `mongorestore` (MongoDB Database Tools) on your PATH        | Download from [mongodb.com/try/download/database-tools](https://www.mongodb.com/try/download/database-tools) |

Verify each tool is available before use:
```bash
mysqldump --version
pg_dump --version
mongodump --version
```

If a command isn't found, add its installation's `bin` folder to your system PATH.

---

## Usage

### Backup

```bash
python main.py backup --db-type <sqlite|mysql|postgres|mongodb> --db-name <name> [options]
```

**SQLite:**
```bash
python main.py backup --db-type sqlite --db-name mydb.db --verbose
```

**MySQL:**
```bash
python main.py backup --db-type mysql --host 127.0.0.1 --port 3306 --user root --password mypassword --db-name mydb --verbose
```

**PostgreSQL:**
```bash
python main.py backup --db-type postgres --host 127.0.0.1 --port 5432 --user postgres --password mypassword --db-name mydb --verbose
```

**MongoDB (Atlas or self-hosted):**
```bash
python main.py backup --db-type mongodb --host cluster0.xxxxx.mongodb.net --user myuser --password mypassword --db-name mydb --verbose
```

**Common backup options:**

| Flag | Description |
|------|-------------|
| `--output` | Directory to store backups (default: `./backups`) |
| `--no-compress` | Skip compression |
| `--tables` | Comma-separated list of specific tables to back up (MySQL/Postgres only) |
| `--verbose` | Print detailed progress output |
| `--slack-webhook` | Slack webhook URL for completion notifications |
| `--upload-to-s3` | Upload the backup to S3-compatible storage after creation |
| `--s3-bucket` | Target bucket name |
| `--s3-endpoint` | Custom S3-compatible endpoint (leave blank for real AWS S3) |
| `--schedule` | Run repeatedly (`hourly` or `daily`); keeps the process running |

### Restore

```bash
python main.py restore --db-type <type> --backup-file <path> [options]
```

**SQLite:**
```bash
python main.py restore --db-type sqlite --backup-file backups/mydb_20260101_120000.db.gz --target mydb.db --verbose
```

**MySQL/PostgreSQL:**
```bash
python main.py restore --db-type mysql --host 127.0.0.1 --port 3306 --user root --password mypassword --db-name mydb --backup-file backups/mydb_20260101_120000.sql.gz --verbose
```

**MongoDB (full database):**
```bash
python main.py restore --db-type mongodb --host cluster0.xxxxx.mongodb.net --user myuser --password mypassword --db-name mydb --backup-file backups/mydb_20260101_120000.zip --verbose
```

**MongoDB (single collection only):**
```bash
python main.py restore --db-type mongodb --host cluster0.xxxxx.mongodb.net --user myuser --password mypassword --db-name mydb --backup-file backups/mydb_20260101_120000.zip --collection users --verbose
```

### List backups

```bash
python main.py list --dir ./backups
```

### Clean up old backups

Preview what would be deleted (recommended first):
```bash
python main.py cleanup --keep 5 --dry-run
```

Actually delete, keeping only the 5 most recent backups per database:
```bash
python main.py cleanup --keep 5
```

---

## Cloud Storage

Backups can be uploaded to any S3-compatible object storage service via `boto3`, including AWS S3, Cloudflare R2, Backblaze B2, and self-hosted MinIO.

For local development and testing, this project was verified against [MinIO](https://min.io/), an S3-compatible storage server that runs entirely on your own machine — no cloud account or credit card required.

**Running MinIO locally:**
```bash
./minio.exe server ./minio-data --console-address ":9001"
```
Web console: `http://127.0.0.1:9001` (default credentials: `minioadmin` / `minioadmin`)

**Uploading a backup to MinIO:**
```bash
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"
python main.py backup --db-type sqlite --db-name mydb.db --upload-to-s3 --s3-bucket db-backups --s3-endpoint http://127.0.0.1:9000 --verbose
```

**Uploading to a real cloud provider:**
Omit `--s3-endpoint` for AWS S3, or set it to your provider's endpoint for R2/Backblaze/etc. Credentials can be passed via `--aws-access-key`/`--aws-secret-key`, or preferably set as environment variables:
```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
```

---

## Scheduling

### Built-in scheduler (simple, demo-friendly)

```bash
python main.py backup --db-type sqlite --db-name mydb.db --schedule daily --verbose
```

This runs an initial backup immediately, then repeats on the given interval. **The terminal/process must stay open** for this to keep working — it does not survive a reboot or closed terminal.

### OS-level scheduling (recommended for real/production use)

For reliable, unattended scheduling, use your operating system's scheduler to run the tool's existing commands — no code changes needed.

**Windows Task Scheduler:**
1. Open Task Scheduler → Create Basic Task
2. Set a trigger (e.g. Daily at 2:00 AM)
3. Action: Start a program
   - Program: path to `python.exe`
   - Arguments: `main.py backup --db-type sqlite --db-name mydb.db --output ./backups`
   - Start in: your project folder

**Linux/macOS cron:**
```bash
0 2 * * * cd /path/to/project && /path/to/venv/bin/python main.py backup --db-type sqlite --db-name mydb.db
```

---

## Logging

All backup and restore operations are logged to `logs/backup.log`, including start time, duration, status, and errors. Logs are also printed to the console.

---

## Security Notes

- **Never commit credentials** (database passwords, Slack webhooks, cloud access keys) to version control. This project keeps them out of the codebase — pass them via command-line flags or environment variables.
- Prefer environment variables over CLI flags for secrets where possible (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), since command-line arguments can appear in shell history and process listings.
- For real cloud deployments, scope IAM/API credentials to the minimum permissions needed (e.g. access to a single bucket) rather than using broad "full access" policies.
- `backups/`, `logs/`, and `venv/` are excluded from version control via `.gitignore`.

---

## Known Limitations

- **Selective restore for MySQL/PostgreSQL** is achieved by selectively **backing up** specific tables (via `--tables`), rather than filtering an existing full backup at restore time. `mysqldump`/`pg_dump` produce a single combined SQL file, so true per-table extraction from an existing full dump would require custom SQL parsing, which is out of scope for this tool.
- **MongoDB selective restore** (`--collection`) is fully supported and works against any existing full backup, since `mongodump` naturally stores each collection as a separate file.
- On some Windows configurations, `mongorestore`/`pymongo` connections to MongoDB Atlas may fail with a TLS handshake error (`TLSV1_ALERT_INTERNAL_ERROR`), typically caused by antivirus software performing HTTPS/TLS inspection, or a system clock drift. If you encounter this: verify your system clock is accurate, temporarily disable antivirus HTTPS scanning, or test from a different network.
- The built-in `--schedule` flag only runs while the terminal process stays open; use OS-level scheduling (Task Scheduler/cron) for unattended production use.

---

## Project Structure

```
.
├── main.py            # CLI entry point, argument parsing, orchestration
├── connectors.py       # Database connector classes (one per DBMS) + factory function
├── requirements.txt    # Python dependencies
├── backups/            # Local backup storage (gitignored)
├── logs/                # Backup/restore logs (gitignored)
└── README.md
```

### Architecture

Each supported database type is implemented as a class (`SQLiteConnector`, `MySQLConnector`, `PostgresConnector`, `MongoConnector`) inheriting from an abstract `DatabaseConnector` base class, which defines a common interface (`test_connection`, `backup`, `restore`). A factory function (`get_connector`) selects the right class based on the `--db-type` flag. This makes it straightforward to add support for additional database types without modifying the CLI logic in `main.py`.

---

## License

This project was built for educational purposes.
