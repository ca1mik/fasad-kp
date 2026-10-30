from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crm_backend.api import create_app
from crm_backend.store import Store


PASSWORD = "correct horse battery staple"


@pytest.fixture
def crm(tmp_path: Path):
    app = create_app(tmp_path / "factory-a")
    store = app.state.store
    store.create_user("owner", PASSWORD, "admin")
    return app, store


def logged(app, username="owner", password=PASSWORD):
    client = TestClient(app)
    response = client.post("/api/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    return client, {"X-CSRF-Token": csrf}


def setup_catalog(client, headers):
    price = client.post("/api/price", headers=headers, json={
        "article": "Арт.110", "name": "Фасад МДФ", "kind": "фрезеровка",
        "unit": "м²", "price_kopecks": 120_000,
    })
    assert price.status_code == 201, price.text
    dealer_a = client.post("/api/dealers", headers=headers, json={"name": "Дилер А", "discount_bp": 1000}).json()
    dealer_b = client.post("/api/dealers", headers=headers, json={"name": "Дилер Б", "discount_bp": 0}).json()
    for username, dealer in [("dealer_a", dealer_a), ("dealer_b", dealer_b)]:
        response = client.post("/api/users", headers=headers, json={
            "username": username, "password": PASSWORD, "role": "dealer", "dealer_id": dealer["id"]})
        assert response.status_code == 201, response.text
    return price.json()["id"], dealer_a, dealer_b


def order_body(price_id, request_id="request-0001", count=1):
    part = {"price_item_id": price_id, "length_mm": 1000, "width_mm": 500,
            "quantity": 2, "thickness_mm": 16, "color": "Белый софт", "milling": "110"}
    return {"request_id": request_id, "client_name": "Кухня клиента", "parts": [part] * count}


def test_dealer_isolation_for_list_direct_id_and_writes(crm):
    app, _ = crm
    admin, ah = logged(app)
    price_id, dealer_a, dealer_b = setup_catalog(admin, ah)
    a, ha = logged(app, "dealer_a")
    b, hb = logged(app, "dealer_b")
    created = a.post("/api/orders", headers=ha, json=order_body(price_id))
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["dealer_id"] == dealer_a["id"]
    assert len(b.get("/api/orders").json()) == 0
    assert b.get(f"/api/orders/{order['id']}").status_code == 404
    assert b.put(f"/api/orders/{order['id']}", headers=hb, json={**order_body(price_id), "expected_version": 1}).status_code == 404
    assert b.post(f"/api/orders/{order['id']}/submit", headers=hb, json={"expected_version": 1}).status_code == 404
    assert b.post("/api/orders", headers=hb, json={**order_body(price_id, "request-0002"), "dealer_id": dealer_a["id"]}).status_code == 403
    assert a.get("/api/dealers").status_code == 403
    assert a.put("/api/settings", headers=ha, json={"expected_version": 1, "companyName": "Чужая фабрика", "materials": {}}).status_code == 403
    assert a.post("/api/orders", json=order_body(price_id, "request-0003")).status_code == 403
    assert dealer_b["id"] != dealer_a["id"]


def test_order_idempotency_snapshot_versions_and_conflicts(crm):
    app, _ = crm
    admin, ah = logged(app)
    price_id, _, _ = setup_catalog(admin, ah)
    dealer, dh = logged(app, "dealer_a")
    body = order_body(price_id)
    first = dealer.post("/api/orders", headers=dh, json=body).json()
    assert first["subtotal_kopecks"] == 120_000  # 2 × 0.5 m² × 1200 ₽
    assert first["discount_kopecks"] == 12_000
    assert first["total_kopecks"] == 108_000
    same = dealer.post("/api/orders", headers=dh, json=body).json()
    assert same["id"] == first["id"]
    assert len(dealer.get("/api/orders").json()) == 1
    settings = admin.get("/api/settings").json()
    settings["companyName"] = "Новая фабрика"
    settings["expected_version"] = settings.pop("version")
    changed = admin.put("/api/settings", headers=ah, json=settings)
    assert changed.status_code == 200, changed.text
    assert admin.put("/api/settings", headers=ah, json=settings).status_code == 409
    second = dealer.post("/api/orders", headers=dh, json=order_body(price_id, "request-0004")).json()
    assert first["settings_version"] == 1 and second["settings_version"] == 2
    assert dealer.get(f"/api/orders/{first['id']}").json()["settings_snapshot"]["companyName"] != second["settings_snapshot"]["companyName"]
    updated = dealer.put(f"/api/orders/{first['id']}", headers=dh, json={**body, "expected_version": 1, "client_name": "Обновлённая кухня"})
    assert updated.status_code == 200, updated.text
    assert dealer.put(f"/api/orders/{first['id']}", headers=dh, json={**body, "expected_version": 1}).status_code == 409
    sent = dealer.post(f"/api/orders/{first['id']}/submit", headers=dh, json={"expected_version": 2})
    assert sent.status_code == 200 and sent.json()["status"] == "submitted"
    assert dealer.put(f"/api/orders/{first['id']}", headers=dh, json={**body, "expected_version": 3}).status_code == 409
    assert dealer.post(f"/api/orders/{first['id']}/confirm", headers=dh, json={"expected_version": 3}).status_code == 403
    assert admin.post(f"/api/orders/{first['id']}/confirm", headers=ah, json={"expected_version": 3}).json()["status"] == "confirmed"


def test_non_adjacent_identical_parts_group_only_on_full_key(crm):
    app, _ = crm
    admin, ah = logged(app)
    price_id, _, _ = setup_catalog(admin, ah)
    dealer, dh = logged(app, "dealer_a")
    base = order_body(price_id)["parts"][0]
    middle = {**base, "color": "Чёрный"}
    parts = [base] + [middle] * 121 + [base]
    result = dealer.post("/api/orders/preview", headers=dh, json={**order_body(price_id), "parts": parts})
    assert result.status_code == 200, result.text
    groups = result.json()["groups"]
    assert len(groups) == 2
    white = next(group for group in groups if group["color"] == "Белый софт")
    assert white["quantity"] == 4
    assert white["source_ordinals"] == [1, 123]
    distinct = dealer.post("/api/orders/preview", headers=dh, json={**order_body(price_id), "parts": [base, {**base, "thickness_mm": 19}, {**base, "milling": "128"}]})
    assert len(distinct.json()["groups"]) == 3


def test_individual_dealer_price_and_snapshot(crm):
    app, _ = crm
    admin, ah = logged(app)
    price_id, dealer_a, _ = setup_catalog(admin, ah)
    dealer, dh = logged(app, "dealer_a")
    assert dealer.get("/api/dealer-prices").status_code == 403
    override = admin.put(f"/api/dealer-prices/{dealer_a['id']}/{price_id}", headers=ah, json={"price_kopecks": 90_000})
    assert override.status_code == 200, override.text
    assert dealer.get("/api/price").json()[0]["price_kopecks"] == 90_000
    first = dealer.post("/api/orders", headers=dh, json=order_body(price_id)).json()
    assert first["subtotal_kopecks"] == 120_000
    assert first["discount_kopecks"] == 30_000
    assert first["total_kopecks"] == first["parts"][0]["line_kopecks"] == 90_000
    admin.put(f"/api/dealer-prices/{dealer_a['id']}/{price_id}", headers=ah, json={"price_kopecks": 80_000})
    assert dealer.get(f"/api/orders/{first['id']}").json()["parts"][0]["unit_price_kopecks"] == 90_000
    second = dealer.post("/api/orders", headers=dh, json=order_body(price_id, "request-0005")).json()
    assert second["total_kopecks"] == 80_000


def test_installations_and_backup_restore_are_isolated(tmp_path: Path):
    factory_a = Store(tmp_path / "a")
    factory_b = Store(tmp_path / "b")
    factory_a.create_user("only_a", PASSWORD, "admin")
    assert factory_b.authenticate("only_a", PASSWORD) is None
    copy = factory_a.backup(tmp_path / "backup")
    recovered = Store.restore_to(copy, tmp_path / "recovered")
    assert Store(recovered.parent).authenticate("only_a", PASSWORD)
    assert recovered.read_bytes() == copy.read_bytes()
    with pytest.raises(ValueError):
        Store.restore_to(copy, tmp_path / "a")
    with sqlite3.connect(copy) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_upgrade_keeps_data_and_creates_pre_migration_backup(tmp_path: Path):
    directory = tmp_path / "factory"
    original = Store(directory)
    original.create_user("owner", PASSWORD, "admin")
    with original.connection(write=True) as con:
        con.execute("DROP TABLE part_events")
        con.execute("DROP TABLE part_instances")
        con.execute("DROP TABLE dealer_price_overrides")
        con.execute("DROP TABLE workspace_revisions")
        settings = original.current_settings()
        settings.pop("stages")
        settings.pop("version")
        con.execute("UPDATE settings_versions SET data_json=? WHERE version=1", (json.dumps(settings, ensure_ascii=False),))
        con.execute("PRAGMA user_version=1")
    upgraded = Store(directory)
    assert upgraded.authenticate("owner", PASSWORD)
    with upgraded.connection() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 4
        assert con.execute("SELECT COUNT(*) FROM dealer_price_overrides").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM part_instances").fetchone()[0] == 0
    assert upgraded.current_settings()["version"] == 2
    assert upgraded.current_settings()["stages"]
    backups = list((tmp_path / "factory-pre-migration").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 1


def test_unauthenticated_and_csrf_protection(crm):
    app, _ = crm
    guest = TestClient(app)
    assert guest.get("/api/orders").status_code == 401
    assert guest.get("/api/settings").status_code == 401
    admin, ah = logged(app)
    assert admin.post("/api/dealers", json={"name": "Нет CSRF"}).status_code == 403
    assert admin.post("/api/dealers", headers={**ah, "Origin": "https://evil.example"}, json={"name": "Чужой сайт"}).status_code == 403
    assert admin.post("/api/dealers", headers=ah, json={"name": "Свой сайт"}).status_code == 201
    assert admin.post("/api/logout", headers=ah).status_code == 200
    assert admin.get("/api/orders").status_code == 401


def test_physical_parts_defect_replacement_and_completeness(crm):
    app, _ = crm
    admin, ah = logged(app)
    price_id, _, _ = setup_catalog(admin, ah)
    assert admin.post("/api/users", headers=ah, json={"username": "worker", "password": PASSWORD, "role": "worker"}).status_code == 201
    worker, wh = logged(app, "worker")
    dealer, dh = logged(app, "dealer_a")
    order = dealer.post("/api/orders", headers=dh, json=order_body(price_id)).json()
    order = dealer.post(f"/api/orders/{order['id']}/submit", headers=dh, json={"expected_version": 1}).json()
    order = admin.post(f"/api/orders/{order['id']}/confirm", headers=ah, json={"expected_version": 2}).json()
    assert order["status"] == "confirmed"
    instances = worker.get(f"/api/orders/{order['id']}/instances").json()
    assert len(instances) == 2 and len({p["id"] for p in instances}) == 2
    assert dealer.get(f"/api/parts/{instances[0]['id']}/label").status_code == 200
    assert "<svg" in dealer.get(f"/api/parts/{instances[0]['id']}/label").text
    assert dealer.post(f"/api/parts/{instances[0]['id']}/start", headers=dh, json={"request_id": "dealer-action"}).status_code == 403
    assert admin.post(f"/api/orders/{order['id']}/ready", headers=ah, json={"expected_version": 3}).status_code == 409
    first, second = (p["id"] for p in instances)
    defect = worker.post(f"/api/parts/{second}/defect", headers=wh, json={"request_id": "defect-0001", "comment": "Скол кромки"})
    assert defect.status_code == 200, defect.text
    assert worker.post(f"/api/parts/{second}/defect", headers=wh, json={"request_id": "defect-0001", "comment": "Скол кромки"}).status_code == 200
    replacement = next(p for p in worker.get(f"/api/orders/{order['id']}/instances").json() if p["replacement_for"] == second)
    assert worker.get(f"/api/orders/{order['id']}/completeness").json()["defects"] == 1
    for instance_id in (first, replacement["id"]):
        for index in range(len(order["settings_snapshot"]["stages"])):
            started = worker.post(f"/api/parts/{instance_id}/start", headers=wh, json={"request_id": f"start-{instance_id}-{index}"})
            assert started.status_code == 200, started.text
            completed = worker.post(f"/api/parts/{instance_id}/complete", headers=wh, json={"request_id": f"complete-{instance_id}-{index}"})
            assert completed.status_code == 200, completed.text
    counts = dealer.get(f"/api/orders/{order['id']}/completeness").json()
    assert counts == {"order_id": order["id"], "required": 2, "completed": 2, "queued": 0, "in_progress": 0, "defects": 1, "missing": 0, "ready": True}
    ready = admin.post(f"/api/orders/{order['id']}/ready", headers=ah, json={"expected_version": 3})
    assert ready.status_code == 200 and ready.json()["status"] == "ready"
    assert admin.post(f"/api/orders/{order['id']}/confirm", headers=ah, json={"expected_version": 2}).status_code == 409
