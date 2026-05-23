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


@app.get("/")
async def index():
    return FileResponse("index.html")


@app.get("/api/device")
async def get_device_list():
    # Try usbmux device list
    try:
        from pymobiledevice3.usbmux import list_devices
        devices = list_devices()
        if devices:
            device_list = [{"udid": d.serial, "name": d.serial} for d in devices]
            return {"connected": True, "devices": device_list}
    except Exception as e:
        usbmux_err = str(e)
    else:
        usbmux_err = "no devices"

    # Try tunneld device list (iOS 17+)
    try:
        from pymobiledevice3.tunneld import get_tunneld_devices
        td = await get_tunneld_devices()
        if td:
            device_list = [{"udid": str(d.udid), "name": str(d.udid)} for d in td]
            return {"connected": True, "devices": device_list}
    except Exception:
        pass

    return {
        "connected": False,
        "devices": [],
        "message": f"デバイスが見つかりません。tunneldが起動中か確認してください。(usbmux: {usbmux_err})",
    }


async def _set_location_usbmux(lat: float, lng: float):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    lockdown = create_using_usbmux()
    async with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        LocationSimulation(dvt).set(lat, lng)


async def _reset_location_usbmux():
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    lockdown = create_using_usbmux()
    async with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        LocationSimulation(dvt).clear()


async def _set_location_rsd(lat: float, lng: float):
    from pymobiledevice3.tunneld import get_tunneld_devices
    from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
    from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    devices = await get_tunneld_devices()
    if not devices:
        raise RuntimeError("tunneld にデバイスが見つかりません")
    d = devices[0]
    async with RemoteServiceDiscoveryService((d.address, d.port)) as rsd:
        async with DvtSecureSocketProxyService(lockdown=rsd) as dvt:
            LocationSimulation(dvt).set(lat, lng)


async def _reset_location_rsd():
    from pymobiledevice3.tunneld import get_tunneld_devices
    from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
    from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    devices = await get_tunneld_devices()
    if not devices:
        raise RuntimeError("tunneld にデバイスが見つかりません")
    d = devices[0]
    async with RemoteServiceDiscoveryService((d.address, d.port)) as rsd:
        async with DvtSecureSocketProxyService(lockdown=rsd) as dvt:
            LocationSimulation(dvt).clear()


@app.post("/api/location")
async def set_location(req: LocationRequest):
    errors = []

    # Try iOS 17+ RSD first (tunneld)
    try:
        await _set_location_rsd(req.lat, req.lng)
        return {"success": True, "lat": req.lat, "lng": req.lng,
                "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}"}
    except Exception as e:
        errors.append(f"RSD: {e}")

    # Fallback: usbmux (iOS 16 and below)
    try:
        await _set_location_usbmux(req.lat, req.lng)
        return {"success": True, "lat": req.lat, "lng": req.lng,
                "message": f"位置を設定しました: {req.lat:.6f}, {req.lng:.6f}"}
    except Exception as e:
        errors.append(f"usbmux: {e}")

    raise HTTPException(status_code=500, detail=" / ".join(errors))


@app.post("/api/location/reset")
async def reset_location():
    errors = []

    try:
        await _reset_location_rsd()
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"RSD: {e}")

    try:
        await _reset_location_usbmux()
        return {"success": True, "message": "位置情報シミュレーションを解除しました。"}
    except Exception as e:
        errors.append(f"usbmux: {e}")

    raise HTTPException(status_code=500, detail=" / ".join(errors))
