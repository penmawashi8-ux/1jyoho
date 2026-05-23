from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio

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


def get_devices():
    try:
        from pymobiledevice3.usbmux import select_devices_by_connection_type
        return select_devices_by_connection_type("USB")
    except Exception:
        return []


def get_lockdown(udid: str | None = None):
    from pymobiledevice3.lockdown import create_using_usbmux
    return create_using_usbmux(serial=udid)


@app.get("/")
async def index():
    return FileResponse("index.html")


@app.get("/api/device")
async def get_device_list():
    try:
        devices = get_devices()
        if not devices:
            return {"connected": False, "devices": [], "message": "iOSデバイスが見つかりません。USBで接続し、「このコンピュータを信頼」をタップしてください。"}
        device_list = [{"udid": d.serial, "name": getattr(d, "name", d.serial)} for d in devices]
        return {"connected": True, "devices": device_list}
    except Exception as e:
        return {"connected": False, "devices": [], "message": f"デバイス検索エラー: {str(e)}"}


@app.post("/api/location")
async def set_location(req: LocationRequest):
    try:
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService

        lockdown = get_lockdown()
        async with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
            sim = LocationSimulation(dvt)
            sim.set(req.lat, req.lng)
        return {"success": True, "lat": req.lat, "lng": req.lng, "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}"}
    except ModuleNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"pymobiledevice3 が見つかりません: {e}")
    except Exception as e:
        msg = str(e)
        if "No device" in msg or "not connected" in msg.lower():
            raise HTTPException(status_code=503, detail="iOSデバイスが接続されていません。USBで接続してください。")
        raise HTTPException(status_code=500, detail=f"位置設定エラー: {msg}")


@app.post("/api/location/reset")
async def reset_location():
    try:
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService

        lockdown = get_lockdown()
        async with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
            sim = LocationSimulation(dvt)
            sim.clear()
        return {"success": True, "message": "位置情報シミュレーションを解除しました。実際の位置情報に戻ります。"}
    except Exception as e:
        msg = str(e)
        if "No device" in msg or "not connected" in msg.lower():
            raise HTTPException(status_code=503, detail="iOSデバイスが接続されていません。")
        raise HTTPException(status_code=500, detail=f"リセットエラー: {msg}")
