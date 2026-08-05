import argparse
import sys
import os
import re
import logging
import time
import requests
import schedule
from pathlib import Path
from datetime import datetime

from connectors import get_connector


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


def cleanup_backups(backup_dir: str, keep: int, dry_run: bool = False) -> None:
    dir_path = Path(backup_dir)
    if not dir_path.exists():
        print(f"No backups found (directory '{backup_dir}' does not exist).")
        return

    all_files = list(dir_path.glob("*.db*")) + list(dir_path.glob("*.sql*")) + list(dir_path.glob("*.zip"))

    if not all_files:
        print(f"No backup files found in '{backup_dir}'.")
        return

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


def send_slack_notification(webhook_url: str, message: str, verbose: bool = False) -> None:
    if not webhook_url:
        return

    try:
        response = requests.post(webhook_url, json={"text": message}, timeout=5)
        if response.status_code != 200:
            logging.warning(f"Slack notification failed: HTTP {response.status_code}")
        elif verbose:
            print("Slack notification sent.")
    except requests.RequestException as e:
        logging.warning(f"Slack notification failed: {e}")


def upload_to_s3(file_path: Path, bucket: str, access_key: str, secret_key: str,
                  endpoint_url: str = None, region: str = "us-east-1", verbose: bool = False) -> bool:
    import boto3
    from botocore.exceptions import ClientError

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url,
            region_name=region
        )
        s3_key = file_path.name

        if verbose:
            print(f"Uploading '{file_path}' to bucket '{bucket}' as '{s3_key}'")

        s3.upload_file(str(file_path), bucket, s3_key)

        if verbose:
            print("Upload complete.")
        return True

    except ClientError as e:
        logging.error(f"Cloud upload failed: {e}")
        return False
    except Exception as e:
        logging.error(f"Cloud upload failed: {e}")
        return False


def run_backup_once(args) -> None:
    """Runs a single backup using the args namespace; used by both direct calls and the scheduler."""
    logging.info(f"Starting backup: db={args.db_name}, type={args.db_type}")
    start_time = time.time()

    aws_access_key = args.aws_access_key or os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = args.aws_secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY")

    try:
        connector = get_connector(
            args.db_type,
            host=args.host, port=args.port,
            user=args.user, password=args.password,
            db_name=args.db_name
        )

        tables_list = args.tables.split(",") if args.tables else None
        result = connector.backup(args.output, args.verbose, compress=not args.no_compress, tables=tables_list)
        elapsed = time.time() - start_time
        logging.info(f"Backup successful: {result} (took {elapsed:.2f}s)")

        if args.upload_to_s3:
            if not args.s3_bucket:
                print("Error: --s3-bucket is required when using --upload-to-s3")
            else:
                uploaded = upload_to_s3(
                    Path(result), args.s3_bucket,
                    aws_access_key, aws_secret_key,
                    args.s3_endpoint, args.aws_region, args.verbose
                )
                if uploaded:
                    logging.info(f"Uploaded to bucket: {args.s3_bucket}/{Path(result).name}")
                else:
                    logging.warning("Cloud upload failed; backup remains available locally.")

        send_slack_notification(
            args.slack_webhook,
            f":white_check_mark: Backup succeeded for `{args.db_name}` ({args.db_type}) in {elapsed:.2f}s -> `{result}`",
            args.verbose
        )

    except SystemExit:
        elapsed = time.time() - start_time
        logging.error(f"Backup failed after {elapsed:.2f}s")
        send_slack_notification(
            args.slack_webhook,
            f":x: Backup FAILED for `{args.db_name}` ({args.db_type}) after {elapsed:.2f}s",
            args.verbose
        )
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logging.exception(f"Backup failed after {elapsed:.2f}s: {e}")
        send_slack_notification(
            args.slack_webhook,
            f":x: Backup FAILED for `{args.db_name}` ({args.db_type}) after {elapsed:.2f}s: {e}",
            args.verbose
        )
        sys.exit(1)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="db-backup",
        description="A CLI tool for backing up and restoring databases."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- backup command ----
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
    backup_parser.add_argument("--slack-webhook", help="Slack webhook URL for completion notifications")
    backup_parser.add_argument("--upload-to-s3", action="store_true", help="Upload the backup to S3-compatible storage after creation")
    backup_parser.add_argument("--s3-bucket", help="Bucket name")
    backup_parser.add_argument("--aws-access-key", help="Access key ID (or set AWS_ACCESS_KEY_ID env var)")
    backup_parser.add_argument("--aws-secret-key", help="Secret access key (or set AWS_SECRET_ACCESS_KEY env var)")
    backup_parser.add_argument("--aws-region", default="us-east-1", help="Region (default: us-east-1)")
    backup_parser.add_argument("--s3-endpoint", help="Custom S3-compatible endpoint (e.g. MinIO, Backblaze, R2); leave blank for AWS")
    backup_parser.add_argument("--schedule", choices=["hourly", "daily"], help="Run backup repeatedly on a schedule (keeps process running)")
    backup_parser.add_argument("--tables", help="Comma-separated list of specific tables to back up (MySQL/Postgres only)")
    
    # ---- restore command ----
    restore_parser = subparsers.add_parser("restore", help="Restore a database from backup")
    restore_parser.add_argument("--db-type", required=True, choices=["sqlite", "mysql", "postgres", "mongodb"])
    restore_parser.add_argument("--backup-file", required=True)
    restore_parser.add_argument("--target", help="Target file/db name (required for sqlite)")
    restore_parser.add_argument("--host")
    restore_parser.add_argument("--port", type=int)
    restore_parser.add_argument("--user")
    restore_parser.add_argument("--password")
    restore_parser.add_argument("--db-name", help="Database name to restore into (mysql/postgres/mongodb)")
    restore_parser.add_argument("--verbose", action="store_true")
    restore_parser.add_argument("--collection", help="Restore only this specific collection (MongoDB only)")
    # ---- list command ----
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
        if args.schedule:
            if args.schedule == "hourly":
                schedule.every().hour.do(run_backup_once, args)
            elif args.schedule == "daily":
                schedule.every().day.at("02:00").do(run_backup_once, args)

            print(f"Scheduled backup to run {args.schedule}. Press Ctrl+C to stop.")
            run_backup_once(args)  # run once immediately too
            while True:
                schedule.run_pending()
                time.sleep(30)
        else:
            run_backup_once(args)

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
            connector.restore(args.backup_file, args.verbose, target=args.target, collection=args.collection)
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