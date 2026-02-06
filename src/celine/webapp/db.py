import os
import sqlite3
from pathlib import Path
from typing import Any

DB_DIR = Path(os.environ.get("REC_WEBAPP_DATA_DIR", "data"))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "app.db"

def connect() -> sqlite3.Connection:
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  return conn

def init_db() -> None:
  with connect() as conn:
    conn.executescript(
      '''
      create table if not exists users (
        user_id text primary key,
        email text,
        name text,
        has_smart_meter integer not null default 0
      );

      create table if not exists policy_acceptance (
        user_id text not null,
        policy_version text not null,
        accepted_at text not null,
        accepted_from_ip text not null,
        primary key (user_id, policy_version)
      );

      create table if not exists settings (
        user_id text primary key,
        simple_mode integer not null default 0,
        font_scale real not null default 1.0,
        email_notifications integer not null default 0
      );

      create table if not exists notifications (
        id text primary key,
        user_id text not null,
        created_at text not null,
        title text not null,
        body text not null,
        severity text not null,
        read_at text
      );

      create table if not exists webpush_subscriptions (
        user_id text not null,
        endpoint text not null,
        subscription_json text not null,
        created_at text not null,
        primary key (user_id, endpoint)
      );
      '''
    )

def q1(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Row | None:
  cur = conn.execute(sql, args)
  return cur.fetchone()

def qall(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
  cur = conn.execute(sql, args)
  return cur.fetchall()
