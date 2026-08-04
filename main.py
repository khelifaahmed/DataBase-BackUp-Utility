import argparse
import sys
import logging
import time
from pathlib import Path
from datetime import datetime

from connectors import get_connector

def cleanup_backups(backup_dir: str, keep: int, dry_run: bool = False) -> None:
    dir_path = Path(backup_dir)
    if not dir_path.exists():
        print(f"No backups found (directory '{backup_dir}' does not exist).")
        return

    all_files = list(dir_path.glob("*.db*")) + list(dir_path.glob("*.sql*")) + list(dir_path.glob("*.zip"))

    if not all_files:
        print(f"No backup files found in '{backup_dir}'.")
        return

    # Group files by database name (the part before the first timestamp-like "_YYYYMMDD")
    import re
    groups = {}
    for file in all_files:
        match = re.match(r"^(.+?)_\d{8}_\d{6}", file.name)
        db_name = match.group(1) if match else file.stem
        groups.setdefault(db_name, []).append(file)

    total_deleted = 0
    for db_name, files in groups.items():
        files_sorted = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
        to_keep = files_sorted[:keep]
        to_delete = files_sorted[keep:]

        if not to_delete:
            continue

        print(f"\n'{db_name}': {len(files_sorted)} backups found, keeping {len(to_keep)}, removing {len(to_delete)}")
        for file in to_delete:
            if dry_run:
                print(f"  [dry-run] Would delete: {file.name}")
            else:
                print(f"  Deleting: {file.name}")
                file.unlink()
                total_deleted += 1
                logging.info(f"Deleted old backup: {file}")

    if dry_run:
        print("\nDry run complete. No files were actually deleted.")
    else:
        print(f"\nCleanup complete. {total_deleted} file(s) deleted.")


def setup_logging(log_dir: str = "./logs") -> None:
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path / "backup.log"),
            logging.StreamHandler()
        ]
    )


def list_backups(backup_dir: str) -> None:
    dir_path = Path(backup_dir)
    if not dir_path.exists():
        print(f"No backups found (directory '{backup_dir}' does not exist).")
        return

    backup_files = sorted(
        list(dir_path.glob("*.db*")) + list(dir_path.glob("*.sql*")) + list(dir_path.glob("*.zip")),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    if not backup_files:
        print(f"No backup files found in '{backup_dir}'.")
        return

    print(f"{'Filename':<40} {'Size':>10}   {'Created'}")
    print("-" * 75)
    for file in backup_files:
        size_kb = file.stat().st_size / 1024
        created = datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{file.name:<40} {size_kb:>8.1f} KB   {created}")


def build_parser():
    parser = argparse.ArgumentParser(prog="db-backup", description="A CLI tool for backing up and restoring databases.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a database backup")
    backup_parser.add_argument("--db-type", required=True, choices=["sqlite", "mysql", "postgres", "mongodb"])
    backup_parser.add_argument("--host")
    backup_parser.add_argument("--port", type=int)
    backup_parser.add_argument("--user")
    backup_parser.add_argument("--password")
    backup_parser.add_argument("--db-name", required=True)
    backup_parser.add_argument("--output", default="./backups")
    backup_parser.add_argument("--verbose", action="store_true")
    backup_parser.add_argument("--no-compress", action="store_true")

    restore_parser = subparsers.add_parser("restore", help="Restore a database from backup")
    restore_parser.add_argument("--db-type", required=True, choices=["sqlite", "mysql", "postgres", "mongodb"])
    restore_parser.add_argument("--backup-file", required=True)
    restore_parser.add_argument("--target", help="Target file/db name (required for sqlite)")
    restore_parser.add_argument("--host")
    restore_parser.add_argument("--port", type=int)
    restore_parser.add_argument("--user")
    restore_parser.add_argument("--password")
    restore_parser.add_argument("--db-name", help="Database name to restore into (mysql/postgres)")
    restore_parser.add_argument("--verbose", action="store_true")

    list_parser = subparsers.add_parser("list", help="List existing backups")
    list_parser.add_argument("--dir", default="./backups")

    # ---- cleanup command ----
    cleanup_parser = subparsers.add_parser("cleanup", help="Delete old backups, keeping only the most recent N per database")
    cleanup_parser.add_argument("--dir", default="./backups", help="Directory containing backups")
    cleanup_parser.add_argument("--keep", type=int, default=5, help="Number of most recent backups to keep per database")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="Preview what would be deleted without deleting")

    return parser


def main():
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "backup":
        logging.info(f"Starting backup: db={args.db_name}, type={args.db_type}")
        start_time = time.time()
        try:
            connector = get_connector(
                args.db_type,
                host=args.host, port=args.port,
                user=args.user, password=args.password,
                db_name=args.db_name
            )
            result = connector.backup(args.output, args.verbose, compress=not args.no_compress)
            elapsed = time.time() - start_time
            logging.info(f"Backup successful: {result} (took {elapsed:.2f}s)")
        except SystemExit:
            elapsed = time.time() - start_time
            logging.error(f"Backup failed after {elapsed:.2f}s")
            raise
        except Exception as e:
            elapsed = time.time() - start_time
            logging.exception(f"Backup failed after {elapsed:.2f}s: {e}")
            sys.exit(1)

    elif args.command == "restore":
        logging.info(f"Starting restore: backup_file={args.backup_file}")
        start_time = time.time()
        try:
            connector = get_connector(
                args.db_type,
                host=args.host, port=args.port,
                user=args.user, password=args.password,
                db_name=args.db_name
            )
            connector.restore(args.backup_file, args.verbose, target=args.target)
            elapsed = time.time() - start_time
            logging.info(f"Restore successful (took {elapsed:.2f}s)")
        except SystemExit:
            elapsed = time.time() - start_time
            logging.error(f"Restore failed after {elapsed:.2f}s")
            raise
        except Exception as e:
            elapsed = time.time() - start_time
            logging.exception(f"Restore failed after {elapsed:.2f}s: {e}")
            sys.exit(1)

    elif args.command == "list":
        list_backups(args.dir)
    elif args.command == "cleanup":
        cleanup_backups(args.dir, args.keep, args.dry_run)

if __name__ == "__main__":
    main()