from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 4
ROLES = {"admin", "manager", "technologist", "worker", "dealer"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def password_hash(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Пароль должен содержать не менее 12 символов")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def check_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(iterations) < 600_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


DEFAULT_SETTINGS = {
    "companyName": "Фасад Профи",
    "stages": [
        {"name": "Распил", "capacityPerDay": 200},
        {"name": "Фрезеровка ЧПУ", "capacityPerDay": 150},
        {"name": "Отделка", "capacityPerDay": 150},
        {"name": "Контроль качества", "capacityPerDay": 200},
        {"name": "Упаковка", "capacityPerDay": 200},
    ],
    "materials": {
        "МДФ 16 мм": {"name": "МДФ 16 мм", "thickness": 16, "sheetWidth": 2800, "sheetHeight": 2070, "kerf": 4, "margin": 10, "allowRotation": True},
        "МДФ 19 мм": {"name": "МДФ 19 мм", "thickness": 19, "sheetWidth": 2800, "sheetHeight": 2070, "kerf": 4, "margin": 10, "allowRotation": True},
    },
}


class Store:
    def __init__(self, directory: Path | str):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "crm.sqlite3"
        if self.path.exists():
            with sqlite3.connect(self.path) as con:
                old_version = con.execute("PRAGMA user_version").fetchone()[0]
            if 0 < old_version < SCHEMA_VERSION:
                self.backup(self.directory.parent / f"{self.directory.name}-pre-migration")
        self.migrate()

    @contextmanager
    def connection(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA journal_mode=WAL")
        try:
            if write:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if write:
                con.commit()
        except BaseException:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    def migrate(self) -> None:
        with self.connection(write=True) as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"База версии {version} новее программы {SCHEMA_VERSION}; обновление остановлено")
            if version == 0:
                existing = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                if existing:
                    raise RuntimeError("База без версии уже содержит таблицы; автоматическая миграция запрещена")
                schema = """
                    CREATE TABLE dealers (
                      id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                      discount_bp INTEGER NOT NULL DEFAULT 0 CHECK(discount_bp BETWEEN 0 AND 10000),
                      created_at TEXT NOT NULL
                    );
                    CREATE TABLE users (
                      id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                      password_hash TEXT NOT NULL, role TEXT NOT NULL,
                      dealer_id INTEGER REFERENCES dealers(id), active INTEGER NOT NULL DEFAULT 1,
                      created_at TEXT NOT NULL,
                      CHECK ((role='dealer' AND dealer_id IS NOT NULL) OR (role!='dealer' AND dealer_id IS NULL))
                    );
                    CREATE TABLE sessions (
                      token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                      csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL
                    );
                    CREATE TABLE settings_versions (
                      version INTEGER PRIMARY KEY, data_json TEXT NOT NULL,
                      created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
                    );
                    CREATE TABLE price_items (
                      id INTEGER PRIMARY KEY, article TEXT NOT NULL, name TEXT NOT NULL,
                      kind TEXT NOT NULL, unit TEXT NOT NULL CHECK(unit IN ('шт','м²')),
                      price_kopecks INTEGER NOT NULL CHECK(price_kopecks >= 0),
                      active INTEGER NOT NULL DEFAULT 1,
                      UNIQUE(article, kind)
                    );
                    CREATE TABLE orders (
                      id TEXT PRIMARY KEY, dealer_id INTEGER REFERENCES dealers(id),
                      created_by INTEGER NOT NULL REFERENCES users(id),
                      request_id TEXT NOT NULL, status TEXT NOT NULL,
                      version INTEGER NOT NULL DEFAULT 1, settings_version INTEGER NOT NULL REFERENCES settings_versions(version),
                      client_name TEXT NOT NULL, due_date TEXT, notes TEXT NOT NULL DEFAULT '',
                      subtotal_kopecks INTEGER NOT NULL, discount_kopecks INTEGER NOT NULL,
                      total_kopecks INTEGER NOT NULL, snapshot_json TEXT NOT NULL,
                      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                      UNIQUE(created_by, request_id)
                    );
                    CREATE INDEX orders_dealer_idx ON orders(dealer_id, created_at);
                    CREATE TABLE order_parts (
                      id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                      ordinal INTEGER NOT NULL, price_item_id INTEGER NOT NULL REFERENCES price_items(id),
                      article TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
                      length_mm INTEGER NOT NULL CHECK(length_mm > 0),
                      width_mm INTEGER NOT NULL CHECK(width_mm > 0),
                      quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
                      thickness_mm INTEGER NOT NULL CHECK(thickness_mm > 0),
                      color TEXT NOT NULL, milling TEXT NOT NULL,
                      unit TEXT NOT NULL, unit_price_kopecks INTEGER NOT NULL,
                      line_kopecks INTEGER NOT NULL,
                      UNIQUE(order_id, ordinal)
                    );
                    CREATE TABLE audit_log (
                      id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor_id INTEGER REFERENCES users(id),
                      action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
                      detail_json TEXT NOT NULL DEFAULT '{}'
                    );
                """
                for statement in schema.split(";"):
                    if statement.strip():
                        con.execute(statement)
                con.execute("INSERT INTO settings_versions(version,data_json,created_at) VALUES(1,?,?)", (json.dumps(DEFAULT_SETTINGS, ensure_ascii=False), now()))
                con.execute("PRAGMA user_version=1")
            if version <= 1:
                con.execute("""CREATE TABLE dealer_price_overrides (
                    dealer_id INTEGER NOT NULL REFERENCES dealers(id) ON DELETE CASCADE,
                    price_item_id INTEGER NOT NULL REFERENCES price_items(id) ON DELETE CASCADE,
                    price_kopecks INTEGER NOT NULL CHECK(price_kopecks >= 0),
                    PRIMARY KEY(dealer_id,price_item_id)
                )""")
                con.execute("PRAGMA user_version=2")
            if version <= 2:
                con.execute("""CREATE TABLE part_instances (
                    id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
                    order_part_id TEXT NOT NULL REFERENCES order_parts(id),
                    serial INTEGER NOT NULL, stage_index INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'queued',
                    replacement_for TEXT REFERENCES part_instances(id),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(order_part_id,serial)
                )""")
                con.execute("CREATE INDEX part_instances_order_idx ON part_instances(order_id,state)")
                con.execute("""CREATE TABLE part_events (
                    id INTEGER PRIMARY KEY, instance_id TEXT NOT NULL REFERENCES part_instances(id),
                    actor_id INTEGER NOT NULL REFERENCES users(id),
                    action TEXT NOT NULL, stage_name TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '',
                    request_id TEXT NOT NULL UNIQUE, at TEXT NOT NULL
                )""")
                row = con.execute("SELECT version,data_json FROM settings_versions ORDER BY version DESC LIMIT 1").fetchone()
                current_settings = json.loads(row["data_json"])
                if "stages" not in current_settings:
                    current_settings["stages"] = DEFAULT_SETTINGS["stages"]
                    con.execute("INSERT INTO settings_versions(version,data_json,created_at) VALUES(?,?,?)", (row["version"] + 1, json.dumps(current_settings, ensure_ascii=False), now()))
                con.execute("PRAGMA user_version=3")
            if version < 4:
                con.execute("""CREATE TABLE workspace_revisions (
                    revision INTEGER PRIMARY KEY, data_json TEXT NOT NULL,
                    actor_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
                )""")
                con.execute("PRAGMA user_version=4")

    def create_user(self, username: str, password: str, role: str, dealer_id: int | None = None) -> int:
        username = username.strip()
        if not username or len(username) > 80 or role not in ROLES:
            raise ValueError("Некорректный пользователь или роль")
        if (role == "dealer") != (dealer_id is not None):
            raise ValueError("Дилерский пользователь должен быть привязан к дилеру")
        encoded = password_hash(password)
        with self.connection(write=True) as con:
            cur = con.execute("INSERT INTO users(username,password_hash,role,dealer_id,created_at) VALUES(?,?,?,?,?)", (username, encoded, role, dealer_id, now()))
            return cur.lastrowid

    def authenticate(self, username: str, password: str):
        with self.connection() as con:
            user = con.execute("SELECT * FROM users WHERE username=? AND active=1", (username.strip(),)).fetchone()
        if user and check_password(password, user["password_hash"]):
            return dict(user)
        return None

    def new_session(self, user_id: int) -> tuple[str, str]:
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        with self.connection(write=True) as con:
            con.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
            con.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, expiry, now()))
        return token, csrf

    def get_session(self, token: str | None):
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connection() as con:
            row = con.execute("SELECT u.id,u.username,u.role,u.dealer_id,u.active,s.csrf_token FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?", (digest, now())).fetchone()
        return dict(row) if row and row["active"] else None

    def delete_session(self, token: str | None) -> None:
        if token:
            with self.connection(write=True) as con:
                con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def audit(self, con: sqlite3.Connection, actor_id: int | None, action: str, entity: str, entity_id: str, detail: dict | None = None) -> None:
        con.execute("INSERT INTO audit_log(at,actor_id,action,entity,entity_id,detail_json) VALUES(?,?,?,?,?,?)", (now(), actor_id, action, entity, entity_id, json.dumps(detail or {}, ensure_ascii=False)))

    def current_settings(self) -> dict:
        with self.connection() as con:
            row = con.execute("SELECT version,data_json FROM settings_versions ORDER BY version DESC LIMIT 1").fetchone()
        return {"version": row["version"], **json.loads(row["data_json"])}

    def backup(self, destination: Path | str) -> Path:
        target_dir = Path(destination).resolve()
        if target_dir == self.directory or self.directory in target_dir.parents:
            raise ValueError("Резервная копия должна находиться вне каталога рабочей базы")
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"fasad-crm-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}.sqlite3"
        target = target_dir / filename
        with sqlite3.connect(self.path) as source, sqlite3.connect(target) as copy:
            source.backup(copy)
            result = copy.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                target.unlink(missing_ok=True)
                raise RuntimeError(f"Резервная копия повреждена: {result}")
        return target

    @staticmethod
    def restore_to(source: Path | str, destination: Path | str) -> Path:
        source_path = Path(source).resolve(strict=True)
        target_dir = Path(destination).resolve()
        if target_dir == source_path.parent or target_dir in source_path.parents:
            raise ValueError("Каталог восстановления должен отличаться от каталога копии")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "crm.sqlite3"
        if target.exists() or any(target_dir.iterdir()):
            raise ValueError("Восстановление разрешено только в пустой каталог")
        with sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True) as con:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Резервная копия не прошла проверку целостности")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise RuntimeError(f"Версия резервной копии {version} не поддерживается")
        shutil.copy2(source_path, target)
        try:
            Store(target_dir)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
