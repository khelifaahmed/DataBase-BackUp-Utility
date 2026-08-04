from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
import shutil
import subprocess
import sys
import os
import gzip


def compress_file(source_path: Path, delete_original: bool = True) -> Path:
    compressed_path = source_path.with_suffix(source_path.suffix + ".gz")
    with open(source_path, "rb") as f_in:
        with gzip.open(compressed_path, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
    if delete_original:
        source_path.unlink()
    return compressed_path


class DatabaseConnector(ABC):
    """Base class that every database connector must implement."""

    def __init__(self, host=None, port=None, user=None, password=None, db_name=None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db_name = db_name

    @abstractmethod
    def test_connection(self) -> bool:
        """Return True if a connection can be established."""
        raise NotImplementedError

    @abstractmethod
    def backup(self, output_dir: str, verbose: bool = False, compress: bool = True) -> Path:
        """Perform the backup and return the path to the backup file."""
        raise NotImplementedError

    @abstractmethod
    def restore(self, backup_file: str, verbose: bool = False, **kwargs) -> None:
        """Restore the database from a backup file."""
        raise NotImplementedError

class SQLiteConnector(DatabaseConnector):
    def test_connection(self) -> bool:
        return Path(self.db_name).exists()

    def backup(self, output_dir: str, verbose: bool = False, compress: bool = True) -> Path:
        source = Path(self.db_name)
        if not source.exists():
            print(f"Error: database file '{self.db_name}' not found.")
            sys.exit(1)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = output_path / f"{source.stem}_{timestamp}{source.suffix}"

        if verbose:
            print(f"Copying '{source}' -> '{destination}'")
        shutil.copy2(source, destination)

        if compress:
            if verbose:
                print(f"Compressing '{destination}'")
            destination = compress_file(destination)

        return destination

    def restore(self, backup_file: str, verbose: bool = False, target: str = None, **kwargs) -> None:
        backup_path = Path(backup_file)
        if not backup_path.exists():
            print(f"Error: backup file '{backup_file}' not found.")
            sys.exit(1)

        target_path = Path(target)
        if target_path.exists():
            confirm = input(f"'{target}' already exists. Overwrite? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Restore cancelled.")
                return

        if backup_path.suffix == ".gz":
            if verbose:
                print(f"Decompressing '{backup_path}' -> '{target_path}'")
            with gzip.open(backup_path, "rb") as f_in:
                with open(target_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            if verbose:
                print(f"Restoring '{backup_path}' -> '{target_path}'")
            shutil.copy2(backup_path, target_path)

        print(f"Restore successful: {target_path}")

class MySQLConnector(DatabaseConnector):
    def test_connection(self) -> bool:
        import pymysql
        try:
            conn = pymysql.connect(
                host=self.host, port=self.port or 3306,
                user=self.user, password=self.password or "",
                database=self.db_name, connect_timeout=5
            )
            conn.close()
            return True
        except Exception as e:
            print(f"MySQL connection failed: {e}")
            return False

    def backup(self, output_dir: str, verbose: bool = False, compress: bool = True) -> Path:
        if not self.test_connection():
            print("Error: could not connect to MySQL database. Check your credentials.")
            sys.exit(1)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = output_path / f"{self.db_name}_{timestamp}.sql"

        cmd = [
            "mysqldump",
            f"--host={self.host}",
            f"--port={self.port or 3306}",
            f"--user={self.user}",
            self.db_name
        ]

        env = os.environ.copy()
        env["MYSQL_PWD"] = self.password or ""

        if verbose:
            print(f"Running: {' '.join(cmd)}")

        with open(destination, "wb") as out_file:
            result = subprocess.run(cmd, stdout=out_file, stderr=subprocess.PIPE, env=env)

        if result.returncode != 0:
            print(f"mysqldump failed: {result.stderr.decode()}")
            sys.exit(1)

        if compress:
            if verbose:
                print(f"Compressing '{destination}'")
            destination = compress_file(destination)

        return destination

    def restore(self, backup_file: str, verbose: bool = False, **kwargs) -> None:
        backup_path = Path(backup_file)
        if not backup_path.exists():
            print(f"Error: backup file '{backup_file}' not found.")
            sys.exit(1)

        # decompress to a temp .sql if needed
        sql_path = backup_path
        cleanup_temp = False
        if backup_path.suffix == ".gz":
            sql_path = backup_path.with_suffix("")
            with gzip.open(backup_path, "rb") as f_in:
                with open(sql_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            cleanup_temp = True

        cmd = ["mysql", f"--host={self.host}", f"--port={self.port or 3306}", f"--user={self.user}", self.db_name]
        env = os.environ.copy()
        env["MYSQL_PWD"] = self.password or ""

        if verbose:
            print(f"Restoring into MySQL database '{self.db_name}'")

        with open(sql_path, "rb") as in_file:
            result = subprocess.run(cmd, stdin=in_file, stderr=subprocess.PIPE, env=env)

        if cleanup_temp:
            sql_path.unlink()

        if result.returncode != 0:
            print(f"mysql restore failed: {result.stderr.decode()}")
            sys.exit(1)

        print(f"Restore successful into database '{self.db_name}'")


class PostgresConnector(DatabaseConnector):
    def test_connection(self) -> bool:
        import psycopg2
        try:
            conn = psycopg2.connect(
                host=self.host, port=self.port or 5432,
                user=self.user, password=self.password or "",
                dbname=self.db_name, connect_timeout=5
            )
            conn.close()
            return True
        except Exception as e:
            print(f"PostgreSQL connection failed: {e}")
            return False

    def backup(self, output_dir: str, verbose: bool = False, compress: bool = True) -> Path:
        if not self.test_connection():
            print("Error: could not connect to PostgreSQL database. Check your credentials.")
            sys.exit(1)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = output_path / f"{self.db_name}_{timestamp}.sql"

        cmd = [
            "pg_dump",
            f"--host={self.host}",
            f"--port={self.port or 5432}",
            f"--username={self.user}",
            self.db_name
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = self.password or ""

        if verbose:
            print(f"Running: {' '.join(cmd)}")

        with open(destination, "wb") as out_file:
            result = subprocess.run(cmd, stdout=out_file, stderr=subprocess.PIPE, env=env)

        if result.returncode != 0:
            print(f"pg_dump failed: {result.stderr.decode()}")
            sys.exit(1)

        if compress:
            if verbose:
                print(f"Compressing '{destination}'")
            destination = compress_file(destination)

        return destination

    def restore(self, backup_file: str, verbose: bool = False, **kwargs) -> None:
        backup_path = Path(backup_file)
        if not backup_path.exists():
            print(f"Error: backup file '{backup_file}' not found.")
            sys.exit(1)

        sql_path = backup_path
        cleanup_temp = False
        if backup_path.suffix == ".gz":
            sql_path = backup_path.with_suffix("")
            with gzip.open(backup_path, "rb") as f_in:
                with open(sql_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            cleanup_temp = True

        cmd = ["psql", f"--host={self.host}", f"--port={self.port or 5432}", f"--username={self.user}", "-d", self.db_name, "-f", str(sql_path)]
        env = os.environ.copy()
        env["PGPASSWORD"] = self.password or ""

        if verbose:
            print(f"Restoring into PostgreSQL database '{self.db_name}'")

        result = subprocess.run(cmd, stderr=subprocess.PIPE, env=env)

        if cleanup_temp:
            sql_path.unlink()

        if result.returncode != 0:
            print(f"psql restore failed: {result.stderr.decode()}")
            sys.exit(1)

        print(f"Restore successful into database '{self.db_name}'")

def compress_dir(source_dir: Path, delete_original: bool = True) -> Path:
    archive_base = str(source_dir)
    archive_path = shutil.make_archive(archive_base, "zip", root_dir=source_dir)
    if delete_original:
        shutil.rmtree(source_dir)
    return Path(archive_path)


class MongoConnector(DatabaseConnector):
    def _build_uri(self) -> str:
        # Atlas format: mongodb+srv://user:password@cluster-host/?params
        # self.host should be just the cluster hostname, e.g. cluster0.mok2nnd.mongodb.net
        return f"mongodb+srv://{self.user}:{self.password}@{self.host}/?appName=Cluster0"

    def test_connection(self) -> bool:
        import pymongo
        try:
            client = pymongo.MongoClient(self._build_uri(), serverSelectionTimeoutMS=5000)
            client.server_info()
            client.close()
            return True
        except Exception as e:
            print(f"MongoDB connection failed: {e}")
            return False

    def backup(self, output_dir: str, verbose: bool = False, compress: bool = True) -> Path:
        if not self.test_connection():
            print("Error: could not connect to MongoDB database. Check your credentials.")
            sys.exit(1)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_dir = output_path / f"{self.db_name}_{timestamp}"

        cmd = [
            "mongodump",
            f"--uri={self._build_uri()}",
            f"--db={self.db_name}",
            f"--out={dump_dir}"
        ]

        if verbose:
            print(f"Running mongodump for database '{self.db_name}' -> '{dump_dir}'")

        result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

        if result.returncode != 0:
            print(f"mongodump failed: {result.stderr.decode()}")
            sys.exit(1)

        destination = dump_dir
        if compress:
            if verbose:
                print(f"Compressing '{dump_dir}'")
            destination = compress_dir(dump_dir)

        return destination

    def restore(self, backup_file: str, verbose: bool = False, **kwargs) -> None:
        backup_path = Path(backup_file)
        if not backup_path.exists():
            print(f"Error: backup file '{backup_file}' not found.")
            sys.exit(1)

        dump_dir = backup_path
        cleanup_temp = False
        if backup_path.suffix == ".zip":
            dump_dir = backup_path.with_suffix("")
            shutil.unpack_archive(str(backup_path), str(dump_dir))
            cleanup_temp = True

        cmd = [
            "mongorestore",
            f"--uri={self._build_uri()}",
            f"--db={self.db_name}",
            str(dump_dir / self.db_name)
        ]

        if verbose:
            print(f"Restoring into MongoDB database '{self.db_name}'")

        result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

        if cleanup_temp:
            shutil.rmtree(dump_dir)

        if result.returncode != 0:
            print(f"mongorestore failed: {result.stderr.decode()}")
            sys.exit(1)

        print(f"Restore successful into database '{self.db_name}'")

def get_connector(db_type: str, **kwargs) -> DatabaseConnector:
    connectors = {
        "sqlite": SQLiteConnector,
        "mysql": MySQLConnector,
        "postgres": PostgresConnector,
        "mongodb": MongoConnector,
    }

    if db_type not in connectors:
        raise ValueError(f"Unsupported database type: {db_type}")

    return connectors[db_type](**kwargs)