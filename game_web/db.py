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
create table if not exists embedding_profile (
  id integer primary key autoincrement,
  library_id integer not null,
  key text not null,
  model_name text not null,
  created_at text not null,
  foreign key (library_id) references library(id) on delete cascade
);
create table if not exists session (
  id text primary key,
  user_id integer not null,
  created_at text not null,
  expires_at text not null
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
        conn.commit()
    finally:
        conn.close()
