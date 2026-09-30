import json
import subprocess
import sys
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

_tunneld_proc: subprocess.Popen | None = None


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
    out = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(out or f"exit code {result.returncode}")
    return out


def _run_rsd(args: list[str], timeout: int = 30) -> str:
    """pymobiledevice3 developer --rsd HOST PORT <args>"""
    host, port = _get_rsd()
    return _run(["developer", "--rsd", host, str(port)] + args, timeout=timeout)


async def _set_via_dt_simulate(lat: float, lng: float):
    """
    DtSimulateLocation: uses com.apple.dt.simulatelocation lockdown service.
    Does NOT go through DVT, so may work without Developer Mode.
    """
    from pymobiledevice3.services.simulate_location import DtSimulateLocation

    host, port = _get_rsd()
    # iOS 17+: connect via RSD
    try:
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        async with RemoteServiceDiscoveryService((host, port)) as rsd:
            async with DtSimulateLocation(rsd) as sim:
                sim.set(lat, lng)
        return
    except Exception:
        pass

    # iOS 16 and below: connect via usbmux
    from pymobiledevice3.lockdown import create_using_usbmux
    lockdown = create_using_usbmux()
    async with DtSimulateLocation(lockdown) as sim:
        sim.set(lat, lng)


async def _reset_via_dt_simulate():
    from pymobiledevice3.services.simulate_location import DtSimulateLocation

    host, port = _get_rsd()
    try:
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        async with RemoteServiceDiscoveryService((host, port)) as rsd:
            async with DtSimulateLocation(rsd) as sim:
                sim.clear()
        return
    except Exception:
        pass

    from pymobiledevice3.lockdown import create_using_usbmux
    lockdown = create_using_usbmux()
    async with DtSimulateLocation(lockdown) as sim:
        sim.clear()


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/api/device")
async def get_device_list():
    try:
        tunnels = _get_tunnels()
        if tunnels:
            devices = [{"udid": udid, "name": udid} for udid in tunnels]
            return {"connected": True, "devices": devices}
    except Exception:
        pass

    try:
        from pymobiledevice3.usbmux import list_devices
        devices = list_devices()
        if devices:
            return {
                "connected": True,
                "devices": [{"udid": d.serial, "name": d.serial} for d in devices],
            }
    except Exception:
        pass

    return {
        "connected": False,
        "devices": [],
        "message": _tunneld_error()
        or "デバイスが見つかりません。iPhoneをUSBで接続し、ロックを解除してください。",
    }


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

    # Method 2: DVT via RSD (requires Developer Mode, iOS 17+)
    try:
        _run_rsd(["dvt", "simulate-location", "set", "--", str(req.lat), str(req.lng)])
        return {
            "success": True,
            "lat": req.lat,
            "lng": req.lng,
            "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}",
        }
    except Exception as e:
        errors.append(f"DVT-RSD: {e}")

    # Method 3: DVT via usbmux (requires Developer Mode, iOS 16 and below)
    try:
        _run(["developer", "dvt", "simulate-location", "set", "--", str(req.lat), str(req.lng)])
        return {
            "success": True,
            "lat": req.lat,
            "lng": req.lng,
            "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}",
        }
    except Exception as e:
        errors.append(f"DVT-usbmux: {e}")

    raise HTTPException(status_code=500, detail=" / ".join(errors))


@app.post("/api/location/reset")
async def reset_location():
    errors = []

    try:
        await _reset_via_dt_simulate()
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"DtSimulate: {e}")

    try:
        _run_rsd(["dvt", "simulate-location", "clear"])
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"DVT-RSD: {e}")

    try:
        _run(["developer", "dvt", "simulate-location", "clear"])
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"DVT-usbmux: {e}")

    raise HTTPException(status_code=500, detail=" / ".join(errors))
