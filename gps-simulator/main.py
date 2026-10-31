import asyncio
import json
import re
import subprocess
import sys
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
TUNNELD_PORT = 49151
TUNNELD_LOG = BASE_DIR / "tunneld.log"
LOCATION_LOG = BASE_DIR / "location.log"

_tunneld_proc: subprocess.Popen | None = None
_ddi_mounted = False
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# iOS 17+ の DVT 位置シミュレーションは接続している間だけ有効なので、プロセスを生かし続ける
_location_proc: subprocess.Popen | None = None


def _tunneld_running() -> bool:
    try:
        _get_tunnels()
        return True
    except Exception:
        return False


def _start_tunneld():
    """tunneld が未起動ならバックグラウンドで起動する（管理者権限が必要）"""
    global _tunneld_proc
    if _tunneld_running():
        return
    log = open(TUNNELD_LOG, "w", encoding="utf-8", errors="replace")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    _tunneld_proc = subprocess.Popen(
        [_cli_path(), "remote", "tunneld"],
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )


def _stop_tunneld():
    global _tunneld_proc
    if _tunneld_proc and _tunneld_proc.poll() is None:
        _tunneld_proc.terminate()
        try:
            _tunneld_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _tunneld_proc.kill()
    _tunneld_proc = None


def _tunneld_error() -> str | None:
    """自動起動した tunneld が異常終了していればログ末尾を返す"""
    if _tunneld_proc is None or _tunneld_proc.poll() is None:
        return None
    try:
        tail = TUNNELD_LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
    except Exception:
        tail = []
    return "tunneld が停止しました（管理者権限で起動しましたか？） " + " ".join(tail)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _start_tunneld()
    yield
    _stop_location_proc()
    _stop_tunneld()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class LocationRequest(BaseModel):
    lat: float
    lng: float


def _cli_path() -> str:
    scripts = Path(sys.executable).parent
    for name in ("pymobiledevice3.exe", "pymobiledevice3"):
        p = scripts / name
        if p.exists():
            return str(p)
    return "pymobiledevice3"


def _get_tunnels() -> dict:
    url = f"http://127.0.0.1:{TUNNELD_PORT}/"
    with urllib.request.urlopen(url, timeout=3) as resp:
        return json.loads(resp.read())


def _get_rsd() -> tuple[str, int]:
    tunnels = _get_tunnels()
    if not tunnels:
        raise RuntimeError("tunneld にアクティブなトンネルがありません。iPhoneをUSBで接続してください。")
    tunnel_list = next(iter(tunnels.values()))
    if not tunnel_list:
        raise RuntimeError("トンネル情報が空です。")
    t = tunnel_list[0]
    return t["tunnel-address"], int(t["tunnel-port"])


def _run(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(
        [_cli_path()] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    out = _ANSI_RE.sub("", result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(out or f"exit code {result.returncode}")
    return out


def _run_rsd(args: list[str], timeout: int = 30) -> str:
    """pymobiledevice3 <args> --rsd HOST PORT（--rsd はサブコマンドの後ろに付ける）"""
    host, port = _get_rsd()
    return _run(args + ["--rsd", host, str(port)], timeout=timeout)


def _with_coords(args: list[str], lat: float, lng: float) -> list[str]:
    return args + ["--", str(lat), str(lng)]


async def _dt_simulate(action):
    """
    DtSimulateLocation: uses com.apple.dt.simulatelocation lockdown service.
    Does NOT go through DVT, so may work without Developer Mode.
    """
    from pymobiledevice3.services.simulate_location import DtSimulateLocation

    errors = []
    # iOS 17+: connect via RSD
    try:
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        async with RemoteServiceDiscoveryService(_get_rsd()) as rsd:
            await action(DtSimulateLocation(rsd))
        return
    except Exception as e:
        errors.append(f"RSD: {e}")

    # iOS 16 and below: connect via usbmux
    try:
        from pymobiledevice3.lockdown import create_using_usbmux
        lockdown = await create_using_usbmux()
        await action(DtSimulateLocation(lockdown))
        return
    except Exception as e:
        errors.append(f"usbmux: {e}")

    raise RuntimeError(", ".join(errors))


async def _set_via_dt_simulate(lat: float, lng: float):
    async def action(sim):
        await sim.set(lat, lng)
    await _dt_simulate(action)


async def _reset_via_dt_simulate():
    async def action(sim):
        await sim.clear()
    await _dt_simulate(action)


async def _list_usbmux_devices():
    from pymobiledevice3.usbmux import list_devices
    devices = list_devices()
    if asyncio.iscoroutine(devices):  # pymobiledevice3 の新しい版では async
        devices = await devices
    return devices


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "index.html")


def _usbmuxd_reachable() -> bool:
    """Windows では Apple Mobile Device Service が 127.0.0.1:27015 で待ち受けている"""
    if sys.platform != "win32":
        return True
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 27015), timeout=2):
            return True
    except OSError:
        return False


def _list_devices_cli() -> list[str]:
    out = _run(["usbmux", "list", "--simple"], timeout=15)
    try:
        data = json.loads(out)
        return [d if isinstance(d, str) else d.get("UniqueDeviceID", "") for d in data]
    except ValueError:
        return [line.strip() for line in out.splitlines() if len(line.strip()) >= 24 and " " not in line.strip()]


@app.get("/api/device")
async def get_device_list():
    errors = []
    try:
        tunnels = _get_tunnels()
        if tunnels:
            devices = [{"udid": udid, "name": udid} for udid in tunnels]
            return {"connected": True, "devices": devices}
    except Exception:
        pass

    try:
        devices = await _list_usbmux_devices()
        if devices:
            return {
                "connected": True,
                "devices": [{"udid": d.serial, "name": d.serial} for d in devices],
            }
    except Exception as e:
        errors.append(f"usbmux: {e}")

    # ライブラリのバージョン差異に備えて CLI でも確認
    try:
        udids = await asyncio.to_thread(_list_devices_cli)
        if udids:
            return {"connected": True, "devices": [{"udid": u, "name": u} for u in udids]}
    except Exception as e:
        lines = [l for l in str(e).splitlines() if "ERROR" in l] or str(e).splitlines()[-1:]
        errors.append("cli: " + " ".join(l.split("ERROR", 1)[-1].strip() for l in lines))

    if not _usbmuxd_reachable():
        message = (
            "Apple Mobile Device Service に接続できません。Microsoft Store の「Apple Devices」"
            "（または iTunes）をインストールして一度起動し、PCを再起動してください。"
        )
    else:
        message = _tunneld_error() or (
            "デバイスが見つかりません。USBケーブルを挿し直し、iPhoneのロックを解除して"
            "「このコンピュータを信頼」をタップしてください。"
        )
    if errors:
        message += " [詳細] " + " / ".join(errors)
    return {"connected": False, "devices": [], "message": message}


@app.get("/api/developer-mode")
async def developer_mode_status():
    try:
        out = await asyncio.to_thread(_run, ["amfi", "developer-mode-status"], 15)
        return {"enabled": "true" in out.lower()}
    except Exception as e:
        return {"enabled": None, "message": str(e)}


@app.post("/api/developer-mode/enable")
async def enable_developer_mode():
    """
    設定アプリにデベロッパーモードが表示されない iPhone 向け。
    1. reveal: 「設定 > プライバシーとセキュリティ」にデベロッパーモードの項目を出す
    2. enable: パスコード未設定なら自動で有効化（iPhone が再起動する）
    """
    try:
        await asyncio.to_thread(_run, ["amfi", "reveal-developer-mode"], 30)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"メニューの表示に失敗しました: {e}")

    try:
        # 再起動を待つので長めのタイムアウト
        await asyncio.to_thread(_run, ["amfi", "enable-developer-mode"], 300)
        return {
            "success": True,
            "revealed": True,
            "message": "デベロッパーモードを有効にしました。再起動後に確認ダイアログが出たら「オンにする」をタップしてください。",
        }
    except Exception as e:
        if "passcode" in str(e).lower():
            message = (
                "隠れていた「デベロッパモード」の項目をiPhoneに表示させました。"
                "iPhoneの「設定」→「プライバシーとセキュリティ」→一番下の「デベロッパモード」をONにして再起動し、"
                "ロック解除時の確認で「オンにする」をタップしてください。"
                "（項目を触らずに済ませたい場合: iPhoneのパスコードを一時的にオフにしてからもう一度実行すると、"
                "自動でONになります。終わったらパスコードを戻してください）"
            )
        else:
            message = f"項目を表示させました。設定から手動でONにしてください（自動有効化エラー: {e}）"
        return {"success": False, "revealed": True, "message": message}


DEVMODE_OFF_HINT = (
    "iPhone側でデベロッパーモードがOFFになっています（iPhone本体がそう応答しました）。"
    "画面上部の「🛠 デベロッパーモードを有効化」を押すか、iPhoneの「設定」→「プライバシーとセキュリティ」→"
    "一番下の「デベロッパモード」をONにして再起動し、再起動後のロック解除時に出る確認で「オンにする」を"
    "タップしてください（これをしないとONになりません）。"
)


async def _location_error_detail(errors: list[str]) -> str:
    """失敗理由のうち、ユーザーが対処できるものを先頭に出す"""
    hint = _tunneld_error()
    if hint is None and any("Developer Mode is disabled" in e for e in errors):
        hint = DEVMODE_OFF_HINT
    if hint is None:
        try:
            out = await asyncio.to_thread(_run, ["amfi", "developer-mode-status"], 15)
            if "false" in out.lower():
                hint = DEVMODE_OFF_HINT
        except Exception:
            pass
    detail = " / ".join(errors)
    if hint:
        return f"{hint} [詳細] {detail[:300]}…" if len(detail) > 300 else f"{hint} [詳細] {detail}"
    return detail


def _start_location_proc(args: list[str], timeout: int = 60):
    """
    pymobiledevice3 developer dvt simulate-location set は位置をセットした後
    「Press ENTER to exit」で待機し、終了すると位置が元に戻る。
    そのためバックグラウンドで起動したまま保持し、待機状態に入ったら成功とみなす。
    """
    global _location_proc
    _stop_location_proc()
    log = open(LOCATION_LOG, "w", encoding="utf-8", errors="replace")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [_cli_path()] + args,
        stdin=subprocess.PIPE,  # 何も書き込まないので ENTER 待ちのまま止まる
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = _ANSI_RE.sub("", LOCATION_LOG.read_text(encoding="utf-8", errors="replace"))
        if "Press" in out:
            _location_proc = proc
            return
        if proc.poll() is not None:
            raise RuntimeError(out.strip() or f"exit code {proc.returncode}")
        time.sleep(0.3)
    proc.kill()
    raise RuntimeError("タイムアウトしました: " + LOCATION_LOG.read_text(encoding="utf-8", errors="replace").strip()[-300:])


def _stop_location_proc():
    global _location_proc
    proc, _location_proc = _location_proc, None
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.stdin.write(b"\n")  # Windows: ENTER で正常終了させる
        proc.stdin.flush()
        proc.wait(timeout=5)
        return
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _ensure_ddi_mounted():
    """
    iOS 17+ の DVT は Developer Disk Image（Personalized）がマウントされていないと
    「Failed to start service」になる。Xcode なら自動でやってくれる処理を代わりに行う。
    初回はイメージのダウンロードが入るので時間がかかる。マウント済みなら即成功する。
    """
    global _ddi_mounted
    if _ddi_mounted:
        return
    _run(["mounter", "auto-mount"], timeout=300)
    _ddi_mounted = True


def _dvt_set_args(lat: float, lng: float) -> list[str]:
    args = ["developer", "dvt", "simulate-location", "set"]
    try:
        host, port = _get_rsd()
        args += ["--rsd", host, str(port)]  # "--" より前に置く（後ろだと座標扱いになる）
    except Exception:
        pass  # CLI が tunneld を自動で探す
    return _with_coords(args, lat, lng)


@app.post("/api/location")
async def set_location(req: LocationRequest):
    errors = []

    # Method 1: DtSimulateLocation (no Developer Mode required)
    try:
        await _set_via_dt_simulate(req.lat, req.lng)
        return {
            "success": True,
            "lat": req.lat,
            "lng": req.lng,
            "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}",
        }
    except Exception as e:
        errors.append(f"DtSimulate: {e}")

    # Method 2: DVT (requires Developer Mode, iOS 17+). プロセスを保持し続ける
    try:
        await asyncio.to_thread(_ensure_ddi_mounted)
    except Exception as e:
        errors.append(f"DDIマウント: {e}")
        if "Developer Mode is disabled" in str(e):
            # この状態では他の方法も必ず失敗する。隠れた項目の表示＋自動有効化をその場で行う
            result = await enable_developer_mode()
            raise HTTPException(
                status_code=400,
                detail="iPhoneのデベロッパーモードがOFFだったため、自動で対処しました。" + result["message"],
            )
    try:
        await asyncio.to_thread(_start_location_proc, _dvt_set_args(req.lat, req.lng))
        return {
            "success": True,
            "lat": req.lat,
            "lng": req.lng,
            "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}（このウィンドウを閉じると元に戻ります）",
        }
    except Exception as e:
        errors.append(f"DVT: {e}")

    # Method 3: iOS 16 and below
    try:
        await asyncio.to_thread(
            _run, _with_coords(["developer", "simulate-location", "set"], req.lat, req.lng)
        )
        return {
            "success": True,
            "lat": req.lat,
            "lng": req.lng,
            "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}",
        }
    except Exception as e:
        errors.append(f"iOS16: {e}")

    raise HTTPException(status_code=500, detail=await _location_error_detail(errors))


@app.post("/api/location/reset")
async def reset_location():
    errors = []

    if _location_proc is not None and _location_proc.poll() is None:
        await asyncio.to_thread(_stop_location_proc)
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}

    try:
        await _reset_via_dt_simulate()
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"DtSimulate: {e}")

    try:
        await asyncio.to_thread(_run_rsd, ["developer", "dvt", "simulate-location", "clear"])
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"DVT-RSD: {e}")

    try:
        await asyncio.to_thread(_run, ["developer", "simulate-location", "clear"])
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"DVT-usbmux: {e}")

    raise HTTPException(status_code=500, detail=await _location_error_detail(errors))
