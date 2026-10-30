"""Fill a throwaway Fasad Portable database with realistic showroom data.

The API must already run against data/portable_sales_video.db on port 8000.
Never run this against the working Portable database.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import uuid

import requests
from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "portable_sales_video.db"
META = ROOT / "data" / "portable_sales_video_meta.json"
BASE = "http://127.0.0.1:8000/api/v1"


def call(session: requests.Session, method: str, route: str, payload=None):
    response = session.request(method, BASE + route, json=payload, timeout=30)
    if not response.ok:
        raise RuntimeError(f"{method} {route}: {response.status_code} {response.text[:700]}")
    return response.json()["data"]


def lead_payload(name: str, phone: str, address: str, direction: str, parts: list[dict]):
    total = sum(Decimal(str(part["amount"])) for part in parts)
    return {
        "source_channel": "manual_manager_input",
        "text": f"Клиент: {name}\nАдрес: {address}\nРасчёт: {total:.2f} ₽",
        "sender": {"full_name": name, "phone": phone, "address": address},
        "direction_code": direction,
        "due_date": (date.today() + timedelta(days=18)).isoformat(),
        "raw_payload": {"parts": parts},
    }


def part(width, height, quantity, article, material, unit_price, kind="enamel"):
    area = Decimal(width) * Decimal(height) * Decimal(quantity) / Decimal(1_000_000)
    amount = area * Decimal(unit_price)
    return {
        "width": width,
        "height": height,
        "quantity": quantity,
        "thickness": 16,
        "article": article,
        "milling": f"Фрезеровка {article}",
        "material": material,
        "kind": kind,
        "unit": "sqm",
        "unit_price": str(unit_price),
        "area_sqm": str(area),
        "amount": str(amount),
    }


def main() -> None:
    assert DB.resolve().is_relative_to((ROOT / "data").resolve())
    assert DB.exists() and not META.exists()
    os.environ["DATABASE_URL"] = f"sqlite:///{DB.as_posix()}"
    os.environ["LICENSE_LOCK_ENABLED"] = "false"
    sys.path.insert(0, str(Path(r"H:\fasad-portable\backend")))

    login = requests.post(
        BASE + "/auth/login",
        json={"login": "admin", "password": "sales-video-2026"},
        timeout=20,
    )
    login.raise_for_status()
    token = login.json()["data"]["token"]["access_token"]
    session = requests.Session()
    session.headers["Authorization"] = "Bearer " + token

    materials = []
    for code, name, color, price in [
        ("mdf-white-16", "МДФ белый глянец, 16 мм", "Белый глянец", 1250),
        ("mdf-grey-16", "МДФ серый матовый, 16 мм", "Серый матовый", 1320),
        ("mdf-oak-16", "МДФ дуб натуральный, 16 мм", "Дуб натуральный", 1490),
    ]:
        materials.append(call(session, "POST", "/materials", {
            "code": code, "name": name, "category": "board", "thickness": 16,
            "length": 2750, "width": 1250, "unit": "sqm", "color": color,
            "price": price, "is_active": True,
        }))
    edge = call(session, "POST", "/edge-materials", {
        "code": "edge-white-1", "name": "Кромка белая, 1 мм", "thickness": 1,
        "color": "Белый", "unit": "m", "price": 42,
    })
    hardware = call(session, "POST", "/hardware", {
        "code": "hinge-110", "name": "Петля 110°", "unit": "pcs", "price": 95,
    })

    rows = [
        lead_payload(
            "Студия интерьера Линия", "+79165550101", "Москва, улица Лесная, 12",
            "enamel", [
                part(720, 420, 6, "FR-101", "Белый глянец, 16 мм", 18500),
                part(500, 300, 4, "FR-102", "Белый глянец, 16 мм", 18500),
            ],
        ),
        lead_payload(
            "Мебельная мастерская Север", "+79165550102", "Химки, Молодёжная улица, 8",
            "pvc", [
                part(650, 420, 5, "PV-205", "Серый матовый, 16 мм", 14900, "pvc"),
                part(800, 300, 3, "PV-206", "Серый матовый, 16 мм", 14900, "pvc"),
            ],
        ),
        lead_payload(
            "Дизайн-бюро Форма", "+79165550103", "Москва, проспект Мира, 31",
            "veneer", [
                part(620, 380, 4, "SH-310", "Дуб натуральный, 16 мм", 22500, "veneer"),
            ],
        ),
    ]
    leads = [call(session, "POST", "/leads/intake", payload) for payload in rows]
    orders = [
        call(session, "POST", f"/leads/{lead['id']}/create-order", {})
        for lead in leads[:2]
    ]
    call(session, "POST", f"/orders/{orders[0]['id']}/payments", {
        "amount": "18000", "method": "account", "comment": "Аванс по заказу",
    })

    # These catalog and warehouse records are demo inventory in this copy only.
    import app.db.base  # noqa: F401 - register all ORM relationships
    from app.db.session import SessionLocal
    from app.modules.orders.models import OrderItem
    from app.modules.parts_generator.models import Part
    from app.modules.stock.models import StockItem, StockMovement
    from app.modules.users.models import User

    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.login == "admin"))
        for index, material in enumerate(materials):
            item = StockItem(
                material_type="material", material_id=uuid.UUID(material["id"]),
                quantity=Decimal(str(42 - index * 8)),
                reserved_quantity=Decimal("0"), unit="sqm",
            )
            db.add(item)
            db.flush()
            db.add(StockMovement(
                stock_item_id=item.id, movement_type="receipt",
                quantity=item.quantity, unit="sqm", created_by=admin.id,
                comment="Поступление материала",
            ))
        order = orders[1]
        order_item = OrderItem(
            order_id=uuid.UUID(order["id"]), item_type="facade", name="Фасады МДФ",
            width=Decimal("650"), height=Decimal("420"), depth=Decimal("16"),
            quantity=5, material_id=uuid.UUID(materials[1]["id"]),
            facade_material_id=uuid.UUID(materials[1]["id"]), thickness=Decimal("16"),
            params_json={}, price=Decimal("0"),
        )
        db.add(order_item)
        db.flush()
        db.add(Part(
            order_id=uuid.UUID(order["id"]), order_item_id=order_item.id,
            part_code="PV-205", name="Фасад МДФ",
            length=Decimal("650"), width=Decimal("420"),
            thickness=Decimal("16"), quantity=5,
            material_id=uuid.UUID(materials[1]["id"]), rotation_allowed=True,
            label_text="Заказ Север · PV-205",
        ))
        db.commit()

    stage = call(session, "POST", f"/orders/{orders[1]['id']}/workflow/bootstrap", {})
    info = {
        "leads": [lead["id"] for lead in leads],
        "orders": [order["id"] for order in orders],
        "stage": stage["id"],
        "materials": [item["id"] for item in materials],
        "edge": edge["id"],
        "hardware": hardware["id"],
    }
    META.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
