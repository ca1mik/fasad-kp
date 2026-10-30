from __future__ import annotations

import json
import re
import sqlite3
from html import escape as html_escape
from io import BytesIO
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .store import Store, now


def fail(status: int, message: str):
    raise HTTPException(status_code=status, detail=message)


def clean_text(value: str, limit: int = 255) -> str:
    result = value.strip()
    if not result or len(result) > limit:
        fail(422, f"Обязательное поле должно содержать от 1 до {limit} символов")
    return result


class Login(BaseModel):
    username: str
    password: str


class DealerCreate(BaseModel):
    name: str
    discount_bp: int = Field(default=0, ge=0, le=10000)


class UserCreate(BaseModel):
    username: str
    password: str
    role: Literal["admin", "manager", "technologist", "worker", "dealer"]
    dealer_id: int | None = None


class PriceCreate(BaseModel):
    article: str
    name: str
    kind: str
    unit: Literal["шт", "м²"]
    price_kopecks: int = Field(ge=0, le=1_000_000_000)


class DealerPrice(BaseModel):
    price_kopecks: int = Field(ge=0, le=1_000_000_000)


class Material(BaseModel):
    name: str
    thickness: int = Field(ge=1, le=100)
    sheetWidth: int = Field(ge=100, le=5000)
    sheetHeight: int = Field(ge=100, le=5000)
    kerf: int = Field(ge=0, le=20)
    margin: int = Field(ge=0, le=100)
    allowRotation: bool


class Stage(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    capacityPerDay: int = Field(ge=1, le=10000)


class SettingsUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    companyName: str
    materials: dict[str, Material]
    stages: list[Stage] | None = Field(default=None, min_length=1, max_length=15)


class PartInput(BaseModel):
    price_item_id: int
    length_mm: int = Field(gt=0, le=5000)
    width_mm: int = Field(gt=0, le=5000)
    quantity: int = Field(gt=0, le=10000)
    thickness_mm: int = Field(gt=0, le=100)
    color: str = Field(min_length=1, max_length=120)
    milling: str = Field(min_length=1, max_length=120)


class OrderInput(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)
    client_name: str = Field(min_length=1, max_length=255)
    due_date: date | None = None
    notes: str = Field(default="", max_length=2000)
    dealer_id: int | None = None
    parts: list[PartInput] = Field(min_length=1, max_length=500)


class OrderUpdate(OrderInput):
    expected_version: int = Field(ge=1)


class VersionInput(BaseModel):
    expected_version: int = Field(ge=1)


class PartAction(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)
    comment: str = Field(default="", max_length=1000)


def order_visible(con: sqlite3.Connection, order_id: str, user: dict):
    row = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row or (user["role"] == "dealer" and row["dealer_id"] != user["dealer_id"]):
        fail(404, "Заказ не найден")
    return row


def serialize_order(con: sqlite3.Connection, row: sqlite3.Row) -> dict:
    parts = [dict(p) for p in con.execute("SELECT * FROM order_parts WHERE order_id=? ORDER BY ordinal", (row["id"],)).fetchall()]
    result = dict(row)
    result["parts"] = parts
    result["groups"] = grouped_parts(parts)
    result["settings_snapshot"] = json.loads(result.pop("snapshot_json"))
    return result


def grouped_parts(parts: list[dict]) -> list[dict]:
    """Aggregate identical physical parts even when separated by unrelated rows."""
    groups: dict[tuple, dict] = {}
    for part in parts:
        key = (part["article"].strip().casefold(), part["kind"].strip().casefold(),
               part["length_mm"], part["width_mm"], part["thickness_mm"],
               part["color"].strip().casefold(), part["milling"].strip().casefold(),
               part["unit"], part["unit_price_kopecks"])
        if key not in groups:
            groups[key] = {"article": part["article"], "kind": part["kind"],
                           "length_mm": part["length_mm"], "width_mm": part["width_mm"],
                           "thickness_mm": part["thickness_mm"], "color": part["color"],
                           "milling": part["milling"], "unit": part["unit"],
                           "quantity": 0, "line_kopecks": 0, "source_ordinals": []}
        group = groups[key]
        group["quantity"] += part["quantity"]
        group["line_kopecks"] += part["line_kopecks"]
        group["source_ordinals"].append(part["ordinal"])
    return list(groups.values())


def route_for_order(row: sqlite3.Row) -> list[str]:
    snapshot = json.loads(row["snapshot_json"])
    stages = snapshot.get("stages") or []
    return [stage["name"] for stage in stages]


def instances_for_order(con: sqlite3.Connection, order_id: str) -> list[dict]:
    return [dict(row) for row in con.execute("SELECT * FROM part_instances WHERE order_id=? ORDER BY order_part_id,serial", (order_id,))]


def completeness(con: sqlite3.Connection, order_id: str) -> dict:
    required = con.execute("SELECT COALESCE(SUM(quantity),0) FROM order_parts WHERE order_id=?", (order_id,)).fetchone()[0]
    counts = {row["state"]: row["count"] for row in con.execute("SELECT state,COUNT(*) AS count FROM part_instances WHERE order_id=? GROUP BY state", (order_id,))}
    completed = counts.get("complete", 0)
    return {"order_id": order_id, "required": required, "completed": completed,
            "queued": counts.get("queued", 0), "in_progress": counts.get("in_progress", 0),
            "defects": counts.get("defect", 0), "missing": max(0, required - completed),
            "ready": required > 0 and completed >= required and counts.get("queued", 0) == 0 and counts.get("in_progress", 0) == 0}


def priced_parts(con: sqlite3.Connection, values: list[PartInput], discount_bp: int, dealer_id: int | None):
    lines = []
    subtotal = 0
    total = 0
    for index, part in enumerate(values, 1):
        item = con.execute("SELECT * FROM price_items WHERE id=? AND active=1", (part.price_item_id,)).fetchone()
        if not item:
            fail(422, f"Позиция прайса {part.price_item_id} не найдена")
        override = con.execute("SELECT price_kopecks FROM dealer_price_overrides WHERE dealer_id=? AND price_item_id=?", (dealer_id, item["id"])).fetchone() if dealer_id else None
        effective_unit = override[0] if override else (item["price_kopecks"] * (10000 - discount_bp) + 5000) // 10000
        def amount(unit_price: int) -> int:
            if item["unit"] == "м²":
                return (part.quantity * part.length_mm * part.width_mm * unit_price + 500_000) // 1_000_000
            return part.quantity * unit_price
        subtotal += amount(item["price_kopecks"])
        line = amount(effective_unit)
        total += line
        lines.append({"ordinal": index, "price_item_id": item["id"], "article": item["article"], "name": item["name"],
                      "kind": item["kind"], "length_mm": part.length_mm, "width_mm": part.width_mm,
                      "quantity": part.quantity, "thickness_mm": part.thickness_mm,
                      "color": clean_text(part.color, 120), "milling": clean_text(part.milling, 120),
                      "unit": item["unit"], "unit_price_kopecks": effective_unit, "line_kopecks": line})
    return lines, subtotal, subtotal - total, total


def save_parts(con: sqlite3.Connection, order_id: str, lines: list[dict]) -> None:
    con.execute("DELETE FROM order_parts WHERE order_id=?", (order_id,))
    for line in lines:
        con.execute("""INSERT INTO order_parts(id,order_id,ordinal,price_item_id,article,name,kind,length_mm,width_mm,quantity,
                     thickness_mm,color,milling,unit,unit_price_kopecks,line_kopecks)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"{order_id}-P{line['ordinal']}", order_id, *line.values()))


def create_app(data_dir: Path | str, *, secure_cookies: bool = False) -> FastAPI:
    store = Store(data_dir)
    app = FastAPI(title="Fasad CRM API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin:
                try:
                    from urllib.parse import urlsplit
                    parsed = urlsplit(origin)
                    if parsed.netloc != request.headers.get("host") or parsed.scheme != request.url.scheme:
                        return Response("Недопустимый источник запроса", status_code=403)
                except ValueError:
                    return Response("Недопустимый источник запроса", status_code=403)
        return await call_next(request)

    def user_session(fasad_session: str | None = Cookie(default=None)) -> dict:
        session = store.get_session(fasad_session)
        if not session:
            fail(401, "Требуется вход")
        return session

    def write_session(request: Request, user: dict = Depends(user_session), x_csrf_token: str | None = Header(default=None)) -> dict:
        if request.method not in {"GET", "HEAD"} and x_csrf_token != user["csrf_token"]:
            fail(403, "Неверный токен операции")
        return user

    def allowed(user: dict, *roles: str) -> None:
        if user["role"] not in roles:
            fail(403, "Недостаточно прав")

    def public_user(user: dict) -> dict:
        return {key: user[key] for key in ("id", "username", "role", "dealer_id")}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/login")
    def login(body: Login, response: Response):
        user = store.authenticate(body.username, body.password)
        if not user:
            fail(401, "Неверное имя или пароль")
        token, csrf = store.new_session(user["id"])
        response.set_cookie("fasad_session", token, httponly=True, secure=secure_cookies, samesite="strict", max_age=12 * 3600, path="/")
        return {"user": public_user(user), "csrf_token": csrf}

    @app.get("/api/me")
    def me(user: dict = Depends(user_session)):
        return {"user": public_user(user), "csrf_token": user["csrf_token"]}

    @app.post("/api/logout")
    def logout(response: Response, user: dict = Depends(write_session), fasad_session: str | None = Cookie(default=None)):
        store.delete_session(fasad_session)
        response.delete_cookie("fasad_session", path="/")
        return {"ok": True}

    @app.get("/api/settings")
    def get_settings(user: dict = Depends(user_session)):
        return store.current_settings()

    @app.put("/api/settings")
    def update_settings(body: SettingsUpdate, user: dict = Depends(write_session)):
        allowed(user, "admin")
        company = clean_text(body.companyName)
        if not body.materials or len(body.materials) > 30:
            fail(422, "Укажите от 1 до 30 материалов")
        materials = {}
        for key, material in body.materials.items():
            name = clean_text(key, 120)
            if material.name.strip() != name or material.sheetWidth <= 2 * material.margin + material.kerf or material.sheetHeight <= 2 * material.margin + material.kerf:
                fail(422, "Некорректная рабочая зона материала")
            materials[name] = material.model_dump()
        with store.connection(write=True) as con:
            current = con.execute("SELECT version FROM settings_versions ORDER BY version DESC LIMIT 1").fetchone()[0]
            if current != body.expected_version:
                fail(409, "Настройки уже изменены другим пользователем")
            previous = json.loads(con.execute("SELECT data_json FROM settings_versions WHERE version=?", (current,)).fetchone()[0])
            stages = [stage.model_dump() for stage in body.stages] if body.stages is not None else previous.get("stages", [])
            if not stages or len({stage["name"].strip().casefold() for stage in stages}) != len(stages):
                fail(422, "Маршрут должен содержать уникальные этапы")
            for stage in stages:
                stage["name"] = clean_text(stage["name"], 120)
            version = current + 1
            con.execute("INSERT INTO settings_versions VALUES(?,?,?,?)", (version, json.dumps({"companyName": company, "materials": materials, "stages": stages}, ensure_ascii=False), user["id"], now()))
            store.audit(con, user["id"], "settings.updated", "settings", str(version))
        return store.current_settings()

    @app.get("/api/dealers")
    def dealers(user: dict = Depends(user_session)):
        allowed(user, "admin", "manager")
        with store.connection() as con:
            return [dict(row) for row in con.execute("SELECT * FROM dealers ORDER BY name")]

    @app.post("/api/dealers", status_code=201)
    def create_dealer(body: DealerCreate, user: dict = Depends(write_session)):
        allowed(user, "admin")
        with store.connection(write=True) as con:
            try:
                cur = con.execute("INSERT INTO dealers(name,discount_bp,created_at) VALUES(?,?,?)", (clean_text(body.name), body.discount_bp, now()))
            except sqlite3.IntegrityError:
                fail(409, "Дилер с таким названием уже существует")
            store.audit(con, user["id"], "dealer.created", "dealer", str(cur.lastrowid))
            return dict(con.execute("SELECT * FROM dealers WHERE id=?", (cur.lastrowid,)).fetchone())

    @app.post("/api/users", status_code=201)
    def create_user(body: UserCreate, user: dict = Depends(write_session)):
        allowed(user, "admin")
        if body.role == "dealer" and body.dealer_id is None or body.role != "dealer" and body.dealer_id is not None:
            fail(422, "Дилерская роль требует привязки к дилеру")
        try:
            new_id = store.create_user(body.username, body.password, body.role, body.dealer_id)
        except sqlite3.IntegrityError:
            fail(409, "Пользователь существует или дилер не найден")
        except ValueError as exc:
            fail(422, str(exc))
        with store.connection(write=True) as con:
            store.audit(con, user["id"], "user.created", "user", str(new_id), {"role": body.role})
        return {"id": new_id, "username": body.username.strip(), "role": body.role, "dealer_id": body.dealer_id}

    @app.get("/api/price")
    def price(user: dict = Depends(user_session)):
        discount_bp = 0
        with store.connection() as con:
            if user["role"] == "dealer":
                discount_bp = con.execute("SELECT discount_bp FROM dealers WHERE id=?", (user["dealer_id"],)).fetchone()[0]
            rows = [dict(row) for row in con.execute("SELECT * FROM price_items WHERE active=1 ORDER BY article,kind")]
            if user["role"] == "dealer":
                overrides = {row["price_item_id"]: row["price_kopecks"] for row in con.execute("SELECT price_item_id,price_kopecks FROM dealer_price_overrides WHERE dealer_id=?", (user["dealer_id"],))}
                for row in rows:
                    row["price_kopecks"] = overrides.get(row["id"], (row["price_kopecks"] * (10000 - discount_bp) + 5000) // 10000)
        return rows

    @app.get("/api/dealer-prices")
    def dealer_prices(user: dict = Depends(user_session)):
        allowed(user, "admin", "manager")
        with store.connection() as con:
            return [dict(row) for row in con.execute("SELECT * FROM dealer_price_overrides ORDER BY dealer_id,price_item_id")]

    @app.put("/api/dealer-prices/{dealer_id}/{price_item_id}")
    def set_dealer_price(dealer_id: int, price_item_id: int, body: DealerPrice, user: dict = Depends(write_session)):
        allowed(user, "admin", "manager")
        with store.connection(write=True) as con:
            if not con.execute("SELECT 1 FROM dealers WHERE id=?", (dealer_id,)).fetchone() or not con.execute("SELECT 1 FROM price_items WHERE id=? AND active=1", (price_item_id,)).fetchone():
                fail(404, "Дилер или позиция прайса не найдены")
            con.execute("INSERT INTO dealer_price_overrides VALUES(?,?,?) ON CONFLICT(dealer_id,price_item_id) DO UPDATE SET price_kopecks=excluded.price_kopecks", (dealer_id, price_item_id, body.price_kopecks))
            store.audit(con, user["id"], "dealer_price.updated", "dealer_price", f"{dealer_id}:{price_item_id}", {"price_kopecks": body.price_kopecks})
        return {"dealer_id": dealer_id, "price_item_id": price_item_id, "price_kopecks": body.price_kopecks}

    @app.post("/api/price", status_code=201)
    def add_price(body: PriceCreate, user: dict = Depends(write_session)):
        allowed(user, "admin", "manager")
        article = re.sub(r"^(?:АРТ\.?|АРТИКУЛ\s*|ART\.?|ARTICLE\s*)", "", body.article.strip().upper()).strip(" .№")
        if not article or len(article) > 80:
            fail(422, "Укажите артикул до 80 символов")
        with store.connection(write=True) as con:
            try:
                cur = con.execute("INSERT INTO price_items(article,name,kind,unit,price_kopecks) VALUES(?,?,?,?,?)", (article, clean_text(body.name), clean_text(body.kind, 120), body.unit, body.price_kopecks))
            except sqlite3.IntegrityError:
                fail(409, "Такой артикул и тип работы уже есть")
            store.audit(con, user["id"], "price.created", "price", str(cur.lastrowid))
            return dict(con.execute("SELECT * FROM price_items WHERE id=?", (cur.lastrowid,)).fetchone())

    @app.post("/api/orders/preview")
    def preview_order(body: OrderInput, user: dict = Depends(write_session)):
        with store.connection() as con:
            dealer_id = user["dealer_id"] if user["role"] == "dealer" else body.dealer_id
            discount_bp = 0
            if dealer_id:
                dealer = con.execute("SELECT discount_bp FROM dealers WHERE id=?", (dealer_id,)).fetchone()
                if not dealer:
                    fail(422, "Дилер не найден")
                discount_bp = dealer[0]
            lines, subtotal, discount, total = priced_parts(con, body.parts, discount_bp, dealer_id)
        return {"parts": lines, "groups": grouped_parts(lines), "subtotal_kopecks": subtotal, "discount_kopecks": discount, "total_kopecks": total, "settings_version": store.current_settings()["version"]}

    @app.post("/api/orders", status_code=201)
    def create_order(body: OrderInput, user: dict = Depends(write_session)):
        allowed(user, "admin", "manager", "dealer")
        if sum(part.quantity for part in body.parts) > 5000:
            fail(422, "В одном заказе допускается не более 5000 физических деталей")
        with store.connection(write=True) as con:
            existing = con.execute("SELECT * FROM orders WHERE created_by=? AND request_id=?", (user["id"], body.request_id)).fetchone()
            if existing:
                return serialize_order(con, existing)
            dealer_id = user["dealer_id"] if user["role"] == "dealer" else body.dealer_id
            if user["role"] == "dealer" and body.dealer_id not in (None, dealer_id):
                fail(403, "Нельзя создать заказ для другого дилера")
            discount_bp = 0
            if dealer_id is not None:
                dealer = con.execute("SELECT discount_bp FROM dealers WHERE id=?", (dealer_id,)).fetchone()
                if not dealer:
                    fail(422, "Дилер не найден")
                discount_bp = dealer[0]
            lines, subtotal, discount, total = priced_parts(con, body.parts, discount_bp, dealer_id)
            settings = con.execute("SELECT * FROM settings_versions ORDER BY version DESC LIMIT 1").fetchone()
            number = con.execute("SELECT COALESCE(MAX(CAST(SUBSTR(id,3) AS INTEGER)),0)+1 FROM orders").fetchone()[0]
            order_id = f"F-{number:06d}"
            timestamp = now()
            con.execute("""INSERT INTO orders(id,dealer_id,created_by,request_id,status,settings_version,client_name,due_date,notes,
                         subtotal_kopecks,discount_kopecks,total_kopecks,snapshot_json,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (order_id, dealer_id, user["id"], body.request_id, "draft", settings["version"], clean_text(body.client_name),
                         body.due_date.isoformat() if body.due_date else None, body.notes.strip(), subtotal, discount, total,
                         settings["data_json"], timestamp, timestamp))
            save_parts(con, order_id, lines)
            store.audit(con, user["id"], "order.created", "order", order_id)
            return serialize_order(con, con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())

    @app.get("/api/orders")
    def orders(user: dict = Depends(user_session)):
        with store.connection() as con:
            if user["role"] == "dealer":
                rows = con.execute("SELECT * FROM orders WHERE dealer_id=? ORDER BY created_at DESC", (user["dealer_id"],)).fetchall()
            else:
                rows = con.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
            return [serialize_order(con, row) for row in rows]

    @app.get("/api/orders/{order_id}")
    def order_detail(order_id: str, user: dict = Depends(user_session)):
        with store.connection() as con:
            return serialize_order(con, order_visible(con, order_id, user))

    @app.put("/api/orders/{order_id}")
    def update_order(order_id: str, body: OrderUpdate, user: dict = Depends(write_session)):
        allowed(user, "admin", "manager", "dealer")
        if sum(part.quantity for part in body.parts) > 5000:
            fail(422, "В одном заказе допускается не более 5000 физических деталей")
        with store.connection(write=True) as con:
            row = order_visible(con, order_id, user)
            if row["status"] != "draft":
                fail(409, "Изменять можно только черновик")
            if row["version"] != body.expected_version:
                fail(409, "Заказ уже изменён другим пользователем")
            if row["request_id"] != body.request_id or (body.dealer_id not in (None, row["dealer_id"])):
                fail(422, "Нельзя изменить исходный ключ или дилера")
            discount_bp = con.execute("SELECT discount_bp FROM dealers WHERE id=?", (row["dealer_id"],)).fetchone()[0] if row["dealer_id"] else 0
            lines, subtotal, discount, total = priced_parts(con, body.parts, discount_bp, row["dealer_id"])
            con.execute("""UPDATE orders SET client_name=?,due_date=?,notes=?,subtotal_kopecks=?,discount_kopecks=?,
                         total_kopecks=?,version=version+1,updated_at=? WHERE id=?""",
                        (clean_text(body.client_name), body.due_date.isoformat() if body.due_date else None, body.notes.strip(),
                         subtotal, discount, total, now(), order_id))
            save_parts(con, order_id, lines)
            store.audit(con, user["id"], "order.updated", "order", order_id, {"version": row["version"] + 1})
            return serialize_order(con, con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())

    def transition(order_id: str, body: VersionInput, user: dict, from_status: str, to_status: str, roles: tuple[str, ...]):
        allowed(user, *roles)
        with store.connection(write=True) as con:
            row = order_visible(con, order_id, user)
            if row["status"] != from_status or row["version"] != body.expected_version:
                fail(409, "Статус или версия заказа изменились")
            if to_status == "confirmed":
                route = route_for_order(row)
                if not route:
                    fail(422, "Для заказа не задан производственный маршрут")
                for part in con.execute("SELECT * FROM order_parts WHERE order_id=? ORDER BY ordinal", (order_id,)):
                    for serial in range(1, part["quantity"] + 1):
                        part_id = f"{part['id']}-{serial:04d}"
                        con.execute("INSERT INTO part_instances(id,order_id,order_part_id,serial,created_at,updated_at) VALUES(?,?,?,?,?,?)", (part_id, order_id, part["id"], serial, now(), now()))
            if to_status == "ready" and not completeness(con, order_id)["ready"]:
                fail(409, "Нельзя завершить неукомплектованный заказ")
            con.execute("UPDATE orders SET status=?,version=version+1,updated_at=? WHERE id=?", (to_status, now(), order_id))
            store.audit(con, user["id"], f"order.{to_status}", "order", order_id)
            return serialize_order(con, con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())

    @app.post("/api/orders/{order_id}/submit")
    def submit(order_id: str, body: VersionInput, user: dict = Depends(write_session)):
        return transition(order_id, body, user, "draft", "submitted", ("admin", "manager", "dealer"))

    @app.post("/api/orders/{order_id}/confirm")
    def confirm(order_id: str, body: VersionInput, user: dict = Depends(write_session)):
        return transition(order_id, body, user, "submitted", "confirmed", ("admin", "manager"))

    @app.post("/api/orders/{order_id}/ready")
    def ready(order_id: str, body: VersionInput, user: dict = Depends(write_session)):
        return transition(order_id, body, user, "confirmed", "ready", ("admin", "manager"))

    @app.get("/api/orders/{order_id}/completeness")
    def order_completeness(order_id: str, user: dict = Depends(user_session)):
        with store.connection() as con:
            order_visible(con, order_id, user)
            return completeness(con, order_id)

    @app.get("/api/orders/{order_id}/instances")
    def order_instances(order_id: str, user: dict = Depends(user_session)):
        with store.connection() as con:
            order_visible(con, order_id, user)
            return instances_for_order(con, order_id)

    def visible_instance(con: sqlite3.Connection, instance_id: str, user: dict):
        instance = con.execute("SELECT * FROM part_instances WHERE id=?", (instance_id,)).fetchone()
        if not instance:
            fail(404, "Деталь не найдена")
        order = order_visible(con, instance["order_id"], user)
        return instance, order

    def instance_detail(con: sqlite3.Connection, instance: sqlite3.Row, order: sqlite3.Row) -> dict:
        part = con.execute("SELECT * FROM order_parts WHERE id=?", (instance["order_part_id"],)).fetchone()
        route = route_for_order(order)
        events = [dict(row) for row in con.execute("SELECT action,stage_name,comment,at FROM part_events WHERE instance_id=? ORDER BY id", (instance["id"],))]
        return {**dict(instance), "order_status": order["status"], "client_name": order["client_name"],
                "part": dict(part), "route": route, "current_stage": route[instance["stage_index"]] if instance["stage_index"] < len(route) else None,
                "events": events}

    @app.get("/api/parts/{instance_id}")
    def part_detail(instance_id: str, user: dict = Depends(user_session)):
        with store.connection() as con:
            instance, order = visible_instance(con, instance_id, user)
            return instance_detail(con, instance, order)

    def part_action(instance_id: str, body: PartAction, user: dict, action: str) -> dict:
        allowed(user, "admin", "manager", "technologist", "worker")
        with store.connection(write=True) as con:
            instance, order = visible_instance(con, instance_id, user)
            if order["status"] != "confirmed":
                fail(409, "Заказ не находится в производстве")
            existing = con.execute("SELECT instance_id,action FROM part_events WHERE request_id=?", (body.request_id,)).fetchone()
            if existing:
                if existing["instance_id"] != instance_id or existing["action"] != action:
                    fail(409, "Ключ операции уже используется")
                return instance_detail(con, instance, order)
            route = route_for_order(order)
            stage = route[instance["stage_index"]]
            if action == "start" and instance["state"] != "queued":
                fail(409, "Взять в работу можно только ожидающую деталь")
            if action == "complete" and instance["state"] != "in_progress":
                fail(409, "Завершить можно только начатую операцию")
            if action == "defect" and instance["state"] not in {"queued", "in_progress"}:
                fail(409, "Брак можно отметить только у незавершённой детали")
            if action == "defect" and not body.comment.strip():
                fail(422, "Укажите причину брака")
            state = "in_progress" if action == "start" else "defect" if action == "defect" else "complete" if instance["stage_index"] + 1 == len(route) else "queued"
            index = instance["stage_index"] + (1 if action == "complete" else 0)
            con.execute("UPDATE part_instances SET state=?,stage_index=?,updated_at=? WHERE id=?", (state, index, now(), instance_id))
            con.execute("INSERT INTO part_events(instance_id,actor_id,action,stage_name,comment,request_id,at) VALUES(?,?,?,?,?,?,?)", (instance_id, user["id"], action, stage, body.comment.strip(), body.request_id, now()))
            if action == "defect":
                next_serial = con.execute("SELECT COALESCE(MAX(serial),0)+1 FROM part_instances WHERE order_part_id=?", (instance["order_part_id"],)).fetchone()[0]
                replacement_id = f"{instance['order_part_id']}-{next_serial:04d}"
                con.execute("INSERT INTO part_instances(id,order_id,order_part_id,serial,replacement_for,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (replacement_id, instance["order_id"], instance["order_part_id"], next_serial, instance_id, now(), now()))
            store.audit(con, user["id"], f"part.{action}", "part", instance_id, {"stage": stage})
            return instance_detail(con, con.execute("SELECT * FROM part_instances WHERE id=?", (instance_id,)).fetchone(), order)

    @app.post("/api/parts/{instance_id}/start")
    def start_part(instance_id: str, body: PartAction, user: dict = Depends(write_session)):
        return part_action(instance_id, body, user, "start")

    @app.post("/api/parts/{instance_id}/complete")
    def complete_part(instance_id: str, body: PartAction, user: dict = Depends(write_session)):
        return part_action(instance_id, body, user, "complete")

    @app.post("/api/parts/{instance_id}/defect")
    def defect_part(instance_id: str, body: PartAction, user: dict = Depends(write_session)):
        return part_action(instance_id, body, user, "defect")

    @app.get("/api/parts/{instance_id}/label", response_class=HTMLResponse)
    def part_label(instance_id: str, request: Request, user: dict = Depends(user_session)):
        import segno
        with store.connection() as con:
            instance, order = visible_instance(con, instance_id, user)
            part = con.execute("SELECT * FROM order_parts WHERE id=?", (instance["order_part_id"],)).fetchone()
        target = f"{str(request.base_url).rstrip('/')}/?part={instance_id}"
        svg = BytesIO()
        segno.make_qr(target).save(svg, kind="svg", scale=4)
        return HTMLResponse(f"<!doctype html><html lang='ru'><meta charset='utf-8'><title>Этикетка {html_escape(instance_id)}</title><style>body{{font:16px Arial;margin:2cm}}.label{{border:1px solid #222;padding:18px;width:420px}}svg{{width:180px;height:180px}}@media print{{button{{display:none}}}}</style><button onclick='print()'>Печать</button><div class='label'><h2>{html_escape(instance_id)}</h2>{svg.getvalue().decode('utf-8')}<p>Заказ {html_escape(order['id'])} · {part['length_mm']} × {part['width_mm']} × {part['thickness_mm']} мм</p><p>{html_escape(part['article'])} · {html_escape(part['color'])} · {html_escape(part['milling'])}</p></div></html>")

    @app.get("/api/audit")
    def audit(user: dict = Depends(user_session)):
        allowed(user, "admin")
        with store.connection() as con:
            return [dict(row) for row in con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")]

    from .workspace import install_workspace
    install_workspace(app, store, user_session, write_session)

    portal_dir = Path(__file__).parent.parent / "crm_portal"
    @app.get("/")
    def root():
        return FileResponse(portal_dir / "index.html")

    app.mount("/static", StaticFiles(directory=portal_dir), name="static")
    return app
