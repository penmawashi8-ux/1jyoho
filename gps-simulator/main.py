import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TUNNELD_PORT = 49151


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
    return FileResponse("index.html")


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
        "message": "デバイスが見つかりません。iPhoneをUSBで接続しtunneldが起動中か確認してください。",
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
