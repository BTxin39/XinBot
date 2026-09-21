"""Local CLI-managed server; control tokens never enter browser APIs."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import webbrowser

import httpx

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data/web_process.json"


def read_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def probe(record):
    if not record:
        return False
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            result = client.get(f"http://127.0.0.1:{record['port']}/api/server/control",
                                headers={"X-XinBot-Control": record["token"]})
        return result.status_code == 200 and result.json().get("pid") == record["pid"]
    except (httpx.HTTPError, ValueError, KeyError):
        return False


def show():
    record = read_state()
    if probe(record):
        print(f"XinBot Web 运行中 | PID {record['pid']} | http://127.0.0.1:{record['port']}/#/")
    else:
        print("XinBot Web 未运行（无可验证的受管进程）")


def shutdown():
    record = read_state()
    if not probe(record):
        print("没有可关闭的 XinBot 受管后端；不会终止未知进程。")
        return
    with httpx.Client(trust_env=False, timeout=3) as client:
        response = client.post(f"http://127.0.0.1:{record['port']}/api/server/control",
                               headers={"X-XinBot-Control": record["token"]})
        response.raise_for_status()
    for _ in range(100):
        if not probe(record):
            print("XinBot Web 已关闭")
            return
        time.sleep(.1)
    raise RuntimeError("后端仍在关闭中，请稍后使用 xinbot start --show 查询")


def launch(port, dev=False):
    record = read_state()
    if probe(record):
        if record['port'] != port or record.get('dev') != dev:
            raise RuntimeError("已有不同配置的后端运行，请先执行 xinbot start web --shutdown")
        show()
        if not dev:
            webbrowser.open(f"http://127.0.0.1:{port}/#/")
        return
    with socket.socket() as check:
        try:
            check.bind(('127.0.0.1', port))
        except OSError:
            raise RuntimeError(f"端口 {port} 已被其他或旧版进程占用，请先关闭原启动终端")
    if not dev and not (ROOT / 'app/web/static/dist/index.html').is_file():
        raise RuntimeError("缺少网页构建文件，请在 app/web 运行 npm run build")
    logs = ROOT / 'data'
    logs.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, '-m', 'app.web.process', str(port)]
    if dev:
        args.append('--dev')
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    with (logs / 'web.log').open('ab') as log:
        child = subprocess.Popen(args, cwd=ROOT, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, **options)
    for _ in range(150):
        record = read_state()
        # Windows venv launchers may create a child with a different PID.
        if record and record.get('port') == port and record.get('dev') == dev and probe(record):
            show()
            if not dev:
                webbrowser.open(f"http://127.0.0.1:{port}/#/")
            return
        if child.poll() is not None:
            break
        time.sleep(.1)
    raise RuntimeError(f"启动未就绪，请查看 {logs / 'web.log'}；使用 --show 确认状态")


def serve(port, dev):
    import uvicorn
    from fastapi import Request, HTTPException
    from app.web.server import app, mount_static
    token = secrets.token_urlsafe(32)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, timeout_graceful_shutdown=10))

    async def control(request: Request):
        if not secrets.compare_digest(request.headers.get('X-XinBot-Control', ''), token):
            raise HTTPException(403, '无效控制凭据')
        if request.method == 'POST':
            server.should_exit = True
        return {'ok': True, 'pid': os.getpid()}

    app.add_api_route('/api/server/control', control, methods=['GET', 'POST'], include_in_schema=False)
    if not dev:
        mount_static()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    record = {'pid': os.getpid(), 'port': port, 'token': token, 'dev': dev}
    fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(record, output)
    try:
        server.run()
    finally:
        if read_state() == record:
            STATE.unlink(missing_ok=True)


if __name__ == '__main__':
    serve(int(sys.argv[1]), '--dev' in sys.argv)
