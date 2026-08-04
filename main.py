import argparse

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

    # ---- restore command ----
    restore_parser = subparsers.add_parser("restore", help="Restore a database from backup")
    restore_parser.add_argument("--db-type", required=True, choices=["sqlite", "mysql", "postgres", "mongodb"])
    restore_parser.add_argument("--backup-file", required=True, help="Path to the backup file")

    # ---- list command ----
    list_parser = subparsers.add_parser("list", help="List existing backups")
    list_parser.add_argument("--dir", default="./backups", help="Directory to list backups from")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "backup":
        print(f"[backup] Would back up {args.db_type} database '{args.db_name}' to {args.output}")
    elif args.command == "restore":
        print(f"[restore] Would restore {args.db_type} database from {args.backup_file}")
    elif args.command == "list":
        print(f"[list] Would list backups in {args.dir}")


if __name__ == "__main__":
    main()
