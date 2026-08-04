import argparse
import shutil
import sys
from pathlib import Path
from datetime import datetime


def backup_sqlite(db_name: str, output_dir: str, verbose: bool = False) -> Path:
    source = Path(db_name)

    if not source.exists():
        print(f"Error: database file '{db_name}' not found.")
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{source.stem}_{timestamp}{source.suffix}"
    destination = output_path / backup_filename

    if verbose:
        print(f"Copying '{source}' -> '{destination}'")

    shutil.copy2(source, destination)
    return destination

def restore_sqlite(backup_file: str, target_db: str, verbose: bool = False) -> None:
    backup_path = Path(backup_file)

    if not backup_path.exists():
        print(f"Error: backup file '{backup_file}' not found.")
        sys.exit(1)

    target_path = Path(target_db)

    if target_path.exists():
        confirm = input(f"'{target_db}' already exists. Overwrite? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Restore cancelled.")
            return

    if verbose:
        print(f"Restoring '{backup_path}' -> '{target_path}'")

    shutil.copy2(backup_path, target_path)
    print(f"Restore successful: {target_path}")

def build_parser():
    parser = argparse.ArgumentParser(
        prog="db-backup",
        description="A CLI tool for backing up and restoring databases."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- backup command ----
    backup_parser = subparsers.add_parser("backup", help="Create a database backup")
    backup_parser.add_argument("--db-type", required=True, choices=["sqlite", "mysql", "postgres", "mongodb"])
    backup_parser.add_argument("--host", help="Database host")
    backup_parser.add_argument("--port", type=int, help="Database port")
    backup_parser.add_argument("--user", help="Database username")
    backup_parser.add_argument("--password", help="Database password")
    backup_parser.add_argument("--db-name", required=True, help="Name of the database")
    backup_parser.add_argument("--output", default="./backups", help="Where to store the backup")
    backup_parser.add_argument("--verbose", action="store_true", help="Enable detailed output")

    # ---- restore command ----
    restore_parser = subparsers.add_parser("restore", help="Restore a database from backup")
    restore_parser.add_argument("--db-type", required=True, choices=["sqlite", "mysql", "postgres", "mongodb"])
    restore_parser.add_argument("--backup-file", required=True, help="Path to the backup file")
    restore_parser.add_argument("--target", required=True, help="Path to restore the database to")
    restore_parser.add_argument("--verbose", action="store_true", help="Enable detailed output")

    # ---- list command ----
    list_parser = subparsers.add_parser("list", help="List existing backups")
    list_parser.add_argument("--dir", default="./backups", help="Directory to list backups from")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "backup":
        if args.db_type == "sqlite":
            result = backup_sqlite(args.db_name, args.output, args.verbose)
            print(f"Backup successful: {result}")
        else:
            print(f"[backup] {args.db_type} not implemented yet.")

    elif args.command == "restore":
        if args.db_type == "sqlite":
            restore_sqlite(args.backup_file, args.target, args.verbose)
        else:
            print(f"[restore] {args.db_type} not implemented yet.")
    elif args.command == "list":
        print(f"[list] Would list backups in {args.dir}")


if __name__ == "__main__":
    main()
