"""One-way, non-destructive SQLite -> MariaDB migration helper.

Run Alembic against a new empty MariaDB database first. Back up SQLite and
uploads before running. The script refuses any MariaDB target containing rows.
It never deletes source data.
"""
import os
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, select, func, text
from sqlalchemy.engine import make_url

from config.settings import settings
from database.database import Base
from database import models  # noqa: F401


def main():
    source_path = Path(os.getenv("SOURCE_SQLITE_PATH", "smartnet.db")).resolve()
    if not source_path.is_file():
        raise SystemExit(f"SQLite source not found: {source_path}")
    if not settings.DATABASE_URL.startswith("mysql+asyncmy://"):
        raise SystemExit("DATABASE_URL must use mysql+asyncmy://.")

    source = create_engine(f"sqlite:///{source_path.as_posix()}")
    target_url = make_url(settings.DATABASE_URL).set(drivername="mysql+pymysql")
    target = create_engine(target_url, pool_pre_ping=True)
    metadata = Base.metadata

    try:
        target_tables = set(inspect(target).get_table_names())
        missing = set(metadata.tables) - target_tables
        if missing:
            raise SystemExit("Run alembic upgrade head first; target missing: " + ", ".join(sorted(missing)))

        with target.connect() as connection:
            non_empty = []
            for name, table in metadata.tables.items():
                if connection.execute(select(func.count()).select_from(table)).scalar():
                    non_empty.append(name)
            if non_empty:
                raise SystemExit("Target database is not empty; refusing to overwrite: " + ", ".join(non_empty))

        source_meta = MetaData()
        source_meta.reflect(bind=source)
        copied = {}
        with target.begin() as target_tx:
            target_tx.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for table in metadata.sorted_tables:
                if table.name not in source_meta.tables:
                    continue
                source_table = source_meta.tables[table.name]
                with source.connect() as source_connection:
                    rows = source_connection.execute(select(source_table)).mappings().all()
                if rows:
                    records = [dict(row) for row in rows]
                    for offset in range(0, len(records), 500):
                        target_tx.execute(table.insert(), records[offset:offset + 500])
                copied[table.name] = len(rows)
            target_tx.execute(text("SET FOREIGN_KEY_CHECKS=1"))

        with target.begin() as connection:
            for table in metadata.sorted_tables:
                if "id" in table.c:
                    maximum = connection.execute(select(func.max(table.c.id))).scalar()
                    if maximum is not None:
                        connection.exec_driver_sql(
                            f"ALTER TABLE {table.name} AUTO_INCREMENT = {int(maximum) + 1}"
                        )

        print("SQLite -> MariaDB copy completed. Validate business records before cutover.")
        for table_name, row_count in copied.items():
            print(f"{table_name}: {row_count}")
    finally:
        source.dispose()
        target.dispose()


if __name__ == "__main__":
    main()
