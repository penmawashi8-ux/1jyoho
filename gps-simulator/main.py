import subprocess
import sys
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


@app.get("/")
async def index():
    return FileResponse("index.html")


@app.get("/api/device")
async def get_device_list():
    # usbmux (iOS 16 and below)
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

    # tunneld (iOS 17+)
    try:
        from pymobiledevice3.tunneld import get_tunneld_devices
        td = await get_tunneld_devices()
        if td:
            return {
                "connected": True,
                "devices": [{"udid": str(d.udid), "name": str(d.udid)} for d in td],
            }
    except Exception:
        pass

    return {
        "connected": False,
        "devices": [],
        "message": "デバイスが見つかりません。iPhoneをUSBで接続してtunneldが起動中か確認してください。",
    }


@app.post("/api/location")
async def set_location(req: LocationRequest):
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
        raise HTTPException(status_code=500, detail=f"位置設定エラー: {e}")


@app.post("/api/location/reset")
async def reset_location():
    try:
        _run(["developer", "dvt", "simulate-location", "clear"])
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"リセットエラー: {e}")
