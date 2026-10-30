r"""Run one isolated Fasad CRM installation.

Examples:
  py -3.12 crm_server.py init --admin owner
  py -3.12 crm_server.py serve
  py -3.12 crm_server.py backup --to C:\FasadBackups
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from crm_backend.store import Store


def data_dir() -> Path:
    return Path(os.getenv("FASAD_CRM_DATA_DIR", Path(__file__).parent / "data" / "crm"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fasad CRM: отдельная серверная база предприятия")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="Создать первого администратора")
    initialize.add_argument("--admin", required=True)
    serve = commands.add_parser("serve", help="Запустить API и портал")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8770)
    serve.add_argument("--tls-cookie", action="store_true", help="Secure-cookie при работе за HTTPS reverse proxy")
    backup = commands.add_parser("backup", help="Проверенная резервная копия SQLite")
    backup.add_argument("--to", default=os.getenv("FASAD_CRM_BACKUP_DIR", "C:\\FasadBackups"))
    restore = commands.add_parser("restore", help="Восстановить копию в новый пустой каталог")
    restore.add_argument("--from", dest="source", required=True)
    restore.add_argument("--into", required=True)
    args = parser.parse_args()
    if args.command == "restore":
        print(f"Восстановлено: {Store.restore_to(args.source, args.into)}")
        return
    store = Store(data_dir())
    if args.command == "init":
        with store.connection() as con:
            if con.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                parser.error("Пользователи уже есть. Дополнительных создавайте через API администратора.")
        password = getpass.getpass("Пароль администратора (от 12 символов): ")
        repeat = getpass.getpass("Повторите пароль: ")
        if password != repeat:
            parser.error("Пароли не совпали")
        store.create_user(args.admin, password, "admin")
        print(f"Администратор {args.admin} создан. База: {store.path}")
    elif args.command == "backup":
        print(f"Резервная копия проверена: {store.backup(args.to)}")
    else:
        import uvicorn
        from crm_backend.api import create_app

        if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.tls_cookie:
            parser.error("Для внешнего адреса обязателен HTTPS reverse proxy и --tls-cookie")
        app = create_app(data_dir(), secure_cookies=args.tls_cookie)
        print(f"Fasad CRM: http://{args.host}:{args.port}; база {store.path}")
        uvicorn.run(app, host=args.host, port=args.port, proxy_headers=args.tls_cookie, forwarded_allow_ips="127.0.0.1" if args.tls_cookie else "")


if __name__ == "__main__":
    main()
