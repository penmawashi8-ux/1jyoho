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

TUNNELD_PORT = 49151  # default tunneld HTTP port


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
    """Query the tunneld HTTP server for active tunnels."""
    url = f"http://127.0.0.1:{TUNNELD_PORT}/list-tunnels"
    with urllib.request.urlopen(url, timeout=3) as resp:
        return json.loads(resp.read())


def _get_rsd() -> tuple[str, int]:
    """Return (rsd_address, rsd_port) from the first active tunnel."""
    tunnels = _get_tunnels()
    if not tunnels:
        raise RuntimeError("tunneld にアクティブなトンネルがありません。iPhoneをUSBで接続してください。")
    # tunnels is a dict keyed by UDID
    first = next(iter(tunnels.values()))
    return first["address"], int(first["port"])


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
    """Run a command via the RSD tunnel (iOS 17+)."""
    host, port = _get_rsd()
    return _run(["--rsd", host, str(port)] + args, timeout=timeout)


@app.get("/")
async def index():
    return FileResponse("index.html")


@app.get("/api/device")
async def get_device_list():
    # iOS 17+: query tunneld HTTP server
    try:
        tunnels = _get_tunnels()
        if tunnels:
            devices = [{"udid": udid, "name": udid} for udid in tunnels]
            return {"connected": True, "devices": devices}
    except Exception:
        pass

    # iOS 16 and below: usbmux
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

    # iOS 17+: via RSD tunnel
    try:
        _run_rsd([
            "developer", "dvt", "simulate-location", "set",
            "--", str(req.lat), str(req.lng),
        ])
        return {
            "success": True,
            "lat": req.lat,
            "lng": req.lng,
            "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}",
        }
    except Exception as e:
        errors.append(f"RSD: {e}")

    # iOS 16 and below: no RSD
    try:
        _run([
            "developer", "dvt", "simulate-location", "set",
            "--", str(req.lat), str(req.lng),
        ])
        return {
            "success": True,
            "lat": req.lat,
            "lng": req.lng,
            "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}",
        }
    except Exception as e:
        errors.append(f"usbmux: {e}")

    raise HTTPException(status_code=500, detail=" / ".join(errors))


@app.post("/api/location/reset")
async def reset_location():
    errors = []

    try:
        _run_rsd(["developer", "dvt", "simulate-location", "clear"])
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"RSD: {e}")

    try:
        _run(["developer", "dvt", "simulate-location", "clear"])
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"usbmux: {e}")

    raise HTTPException(status_code=500, detail=" / ".join(errors))
