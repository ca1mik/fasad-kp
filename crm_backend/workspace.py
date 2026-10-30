"""Versioned storage for the complete staff workspace, independent of dealer orders."""
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .store import now, password_hash

COLLECTIONS = ('leads', 'clients', 'orders', 'quotes', 'priceItems',
               'depositMovements', 'machines', 'workers', 'stock', 'stockMovements')


def validate_finances(previous, value):
    """Validate the complete financial change inside the revision transaction."""
    def reject(message):
        raise HTTPException(422, message)

    def cents(amount, positive=False):
        try:
            number = Decimal(str(amount))
            if not number.is_finite():
                raise InvalidOperation
            rounded = number.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if number != rounded or positive and rounded <= 0 or rounded < 0:
                raise InvalidOperation
            return int(rounded * 100)
        except (InvalidOperation, ValueError, TypeError):
            reject('Суммы должны быть неотрицательными, с точностью до копейки')

    old_rows = {row['id']: row for row in previous.get('depositMovements', [])}
    new_rows = {row['id']: row for row in value.get('depositMovements', [])}
    if any(new_rows.get(key) != row for key, row in old_rows.items()):
        reject('Проведённые движения депозита нельзя изменять или удалять')
    clients = {row['id'] for row in value.get('clients', [])}
    balances, ledger_delta = {}, {}
    for row in new_rows.values():
        kind, client = row.get('kind'), row.get('clientId')
        if kind not in {'topup', 'withdrawal', 'spend', 'refund'} or client not in clients:
            reject('Некорректная операция или клиент депозита')
        amount = cents(row.get('amount'), positive=True)
        if kind == 'withdrawal' and not str(row.get('reason', '')).strip():
            reject('Для уменьшения депозита требуется причина')
        balances[client] = balances.get(client, 0) + (amount if kind in {'topup', 'refund'} else -amount)
        if row['id'] not in old_rows and kind in {'spend', 'refund'}:
            key = (client, row.get('orderId'))
            ledger_delta[key] = ledger_delta.get(key, 0) + (amount if kind == 'spend' else -amount)
    if any(balance < 0 for balance in balances.values()):
        reject('На депозите недостаточно средств')

    def deposit_payments(state, check=False):
        totals = {}
        ids = set()
        for order in state.get('orders', []):
            paid = 0
            for payment in order.get('payments', []):
                identifier = payment.get('id')
                # Historical imports without IDs are normalized by the browser.
                if identifier and identifier in ids:
                    reject('Повторяющаяся оплата')
                ids.add(identifier) if identifier else None
                amount = cents(payment.get('amount'), positive=True)
                paid += amount
                if payment.get('method') == 'deposit':
                    key = (order.get('clientId'), order['id'])
                    totals[key] = totals.get(key, 0) + amount
            if check and ('payments' in order or 'paidAmount' in order):
                if paid != cents(order.get('paidAmount', 0)):
                    reject('Оплаченная сумма не совпадает с историей оплат')
                if paid > cents(order.get('amount', 0)):
                    reject('Оплата превышает сумму заказа')
        return totals
    before = deposit_payments(previous)
    after = deposit_payments(value, check=True)
    for key in set(before) | set(after) | set(ledger_delta):
        if after.get(key, 0) - before.get(key, 0) != ledger_delta.get(key, 0):
            reject('Оплата с депозита и движение денег должны сохраняться вместе')


class FirstAdmin(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=1024)


class WorkspaceWrite(BaseModel):
    expected_revision: int = Field(ge=0)
    data: dict

    @field_validator('data')
    @classmethod
    def validate_data(cls, value):
        if set(value) - {*COLLECTIONS, 'factorySettings'}:
            raise ValueError('Неизвестные разделы файла')
        for key in COLLECTIONS:
            rows = value.get(key)
            if not isinstance(rows, list) or len(rows) > 20000:
                raise ValueError(f'{key}: требуется список не более 20000 записей')
            ids = set()
            for row in rows:
                if key == 'stockMovements' and isinstance(row, dict) and 'id' not in row:
                    continue
                if not isinstance(row, dict) or not isinstance(row.get('id'), (str, int)):
                    raise ValueError(f'{key}: у каждой записи должен быть ID')
                identifier = str(row['id'])
                if not identifier or identifier in ids:
                    raise ValueError(f'{key}: пустой или повторяющийся ID')
                ids.add(identifier)
        if not isinstance(value.get('factorySettings'), dict):
            raise ValueError('Отсутствуют настройки производства')
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise ValueError('Недопустимые значения в данных') from exc
        if len(encoded.encode('utf-8')) > 10_000_000:
            raise ValueError('Размер данных превышает 10 МБ')
        return value


def install_workspace(app, store, user_session, write_session):
    def local_setup(request):
        if not request.client or request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
            raise HTTPException(403, 'Первичная настройка доступна только на компьютере сервера')

    @app.get('/api/setup')
    def setup_status(request: Request):
        local_setup(request)
        with store.connection() as con:
            configured = bool(con.execute('SELECT COUNT(*) FROM users').fetchone()[0])
        return {'configured': configured}

    @app.post('/api/setup', status_code=201)
    def setup_admin(body: FirstAdmin, request: Request):
        local_setup(request)
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Недопустимый источник запроса')
        username = body.username.strip()
        if not username:
            raise HTTPException(422, 'Введите логин')
        encoded = password_hash(body.password)
        with store.connection(write=True) as con:
            if con.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
                raise HTTPException(409, 'Администратор уже создан. Войдите в систему.')
            row = con.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,'admin',?)", (username, encoded, now()))
            store.audit(con, row.lastrowid, 'installation.initialized', 'user', str(row.lastrowid))
        return {'ok': True}

    def staff(user):
        if user['role'] not in {'admin', 'manager'}:
            raise HTTPException(403, 'Общее рабочее место доступно администратору и менеджеру')

    @app.get('/api/workspace')
    def read_workspace(user=Depends(user_session)):
        staff(user)
        with store.connection() as con:
            row = con.execute('SELECT * FROM workspace_revisions ORDER BY revision DESC LIMIT 1').fetchone()
        return {'revision': row['revision'], 'data': json.loads(row['data_json'])} if row else {'revision': 0, 'data': None}

    @app.get('/api/workspace/version')
    def workspace_version(user=Depends(user_session)):
        staff(user)
        with store.connection() as con:
            revision = con.execute('SELECT COALESCE(MAX(revision),0) FROM workspace_revisions').fetchone()[0]
        return {'revision': revision}

    def save(body, user, importing=False):
        staff(user)
        if importing and user['role'] != 'admin':
            raise HTTPException(403, 'Перенос данных доступен только администратору')
        with store.connection(write=True) as con:
            current = con.execute('SELECT COALESCE(MAX(revision),0) FROM workspace_revisions').fetchone()[0]
            if current != body.expected_revision:
                raise HTTPException(409, 'Данные изменены другим сотрудником. Сохраните свою копию и загрузите актуальные данные.')
            if importing and current:
                raise HTTPException(409, 'Импорт разрешён только в пустое рабочее место')
            previous_row = con.execute('SELECT data_json FROM workspace_revisions WHERE revision=?', (current,)).fetchone()
            previous = json.loads(previous_row['data_json']) if previous_row else {}
            # Imported historical ledgers are checked against their own baseline.
            validate_finances(body.data if importing else previous, body.data)
            revision = current + 1
            con.execute('INSERT INTO workspace_revisions VALUES(?,?,?,?)',
                        (revision, json.dumps(body.data, ensure_ascii=False, allow_nan=False), user['id'], now()))
            # Prior committed states remain recoverable, and are included in SQLite backups.
            store.audit(con, user['id'], 'workspace.imported' if importing else 'workspace.saved', 'workspace', str(revision))
        return {'revision': revision}

    @app.put('/api/workspace')
    def save_workspace(body: WorkspaceWrite, user=Depends(write_session)):
        return save(body, user)

    @app.post('/api/workspace/import')
    def import_workspace(body: WorkspaceWrite, user=Depends(write_session)):
        return save(body, user, importing=True)

    @app.post('/api/workspace/backup')
    def create_backup(user=Depends(write_session)):
        if user['role'] != 'admin':
            raise HTTPException(403, 'Резервная копия доступна только администратору')
        path = store.backup(store.directory.parent / (store.directory.name + '-backups'))
        return {'name': path.name}

    @app.get('/api/workspace/backup/{name}')
    def download_backup(name: str, user=Depends(user_session)):
        if user['role'] != 'admin':
            raise HTTPException(403, 'Резервная копия доступна только администратору')
        if Path(name).name != name or not name.startswith('fasad-crm-') or not name.endswith('.sqlite3'):
            raise HTTPException(404, 'Копия не найдена')
        directory = (store.directory.parent / (store.directory.name + '-backups')).resolve()
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise HTTPException(404, 'Копия не найдена')
        return FileResponse(path, filename=name, media_type='application/vnd.sqlite3', headers={'Cache-Control': 'no-store'})

    demo = Path(__file__).resolve().parents[1] / 'demo'

    @app.get('/work/', response_class=HTMLResponse)
    def workspace_page():
        content = (demo / 'index.html').read_text(encoding='utf-8')
        content = content.replace('<head>', '<head><base href="/work/assets/">', 1)
        start = content.index('  <script src="app.js"></script>')
        end = content.index('</body>', start)
        content = content[:start] + '  <script src="workspace_server.js"></script>\n' + content[end:]
        version = str(max(path.stat().st_mtime_ns for path in demo.rglob('*') if path.suffix in {'.js', '.css'}))
        content = re.sub(r'((?:src|href)=")([^"?]+\.(?:js|css))(")',
                         lambda match: match[1] + match[2] + '?v=' + version + match[3], content)
        return HTMLResponse(content, headers={'Cache-Control': 'no-store'})

    app.mount('/work/assets', StaticFiles(directory=demo), name='workspace-assets')
