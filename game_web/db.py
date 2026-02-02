import sqlite3


SCHEMA_SQL = """
create table if not exists admin_user (
  id integer primary key autoincrement,
  username text unique not null,
  password_hash text not null,
  created_at text not null
);
create table if not exists library (
  id integer primary key autoincrement,
  name text unique not null,
  index_uid text unique not null,
  description text,
  created_at text not null,
  updated_at text not null
);
create table if not exists dataset (
  id integer primary key autoincrement,
  library_id integer not null,
  filename text not null,
  storage_path text not null,
  size_bytes integer not null,
  created_at text not null,
  foreign key (library_id) references library(id) on delete cascade
);
create table if not exists job (
  id integer primary key autoincrement,
  library_id integer not null,
  dataset_id integer not null,
  job_type text not null,
  status text not null,
  log_path text,
  error text,
  created_at text not null,
  updated_at text not null,
  foreign key (library_id) references library(id) on delete cascade,
  foreign key (dataset_id) references dataset(id) on delete cascade
);
create table if not exists embedding_profile (
  id integer primary key autoincrement,
  library_id integer not null,
  key text not null,
  model_name text not null,
  use_fp16 integer not null default 0,
  max_length integer not null default 128,
  variant text not null default 'raw',
  enabled integer not null default 1,
  created_at text not null,
  foreign key (library_id) references library(id) on delete cascade
);
create table if not exists session (
  id text primary key,
  user_id integer not null,
  created_at text not null,
  expires_at text not null
);
create table if not exists settings (
  key text primary key,
  value text not null,
  updated_at text not null
);
"""


def connect_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("pragma foreign_keys = on")
    return conn


def init_db(db_path: str) -> None:
    conn = connect_db(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        migrate_db(conn)
        conn.commit()
    finally:
        conn.close()


def migrate_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists settings (
          key text primary key,
          value text not null,
          updated_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists dataset (
          id integer primary key autoincrement,
          library_id integer not null,
          filename text not null,
          storage_path text not null,
          size_bytes integer not null,
          created_at text not null,
          foreign key (library_id) references library(id) on delete cascade
        )
        """
    )
    conn.execute(
        """
        create table if not exists job (
          id integer primary key autoincrement,
          library_id integer not null,
          dataset_id integer not null,
          job_type text not null,
          status text not null,
          log_path text,
          error text,
          created_at text not null,
          updated_at text not null,
          foreign key (library_id) references library(id) on delete cascade,
          foreign key (dataset_id) references dataset(id) on delete cascade
        )
        """
    )
    cur = conn.execute("pragma table_info(embedding_profile)")
    existing = {row[1] for row in cur.fetchall()}
    columns = [
        ("use_fp16", "integer not null default 0"),
        ("max_length", "integer not null default 128"),
        ("variant", "text not null default 'raw'"),
        ("enabled", "integer not null default 1"),
    ]
    for name, ddl in columns:
        if name not in existing:
            conn.execute(f"alter table embedding_profile add column {name} {ddl}")
    conn.execute(
        "create unique index if not exists embedding_profile_library_key_idx "
        "on embedding_profile (library_id, key)"
    )
    conn.execute(
        "create index if not exists dataset_library_idx on dataset (library_id)"
    )
    conn.execute("create index if not exists job_status_idx on job (status)")
    conn.execute("create index if not exists job_library_idx on job (library_id)")
