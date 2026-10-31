"""
iPhone (iOS 17+) の位置を DVT でセットし、ENTER（または標準入力の終了）まで保持する補助スクリプト。

pymobiledevice3 の `developer dvt simulate-location set` は待機中に input() でイベントループを
止めてしまう。no-root の userspace トンネルは同じイベントループ上で動くため、
数十秒で iPhone 側から切断され位置が元に戻る。ここでは待機を別スレッドで行い、
ループを動かし続ける。さらに定期的に位置を再送し、切断されたら再接続する。

usage: python hold_location.py LAT LNG [--rsd HOST PORT]
"""
import asyncio
import sys
import threading
from contextlib import asynccontextmanager

from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

RESEND_INTERVAL = 15


@asynccontextmanager
async def connect(rsd_addr):
    if rsd_addr:
        # tunneld（管理者権限のカーネルトンネル）がある場合
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        async with RemoteServiceDiscoveryService(rsd_addr) as rsd:
            yield rsd
    else:
        from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
        async with UserspaceRsdTunnel() as rsd:
            yield rsd


async def hold(lat: float, lng: float, rsd_addr, stop: asyncio.Event):
    first = True
    while not stop.is_set():
        try:
            async with connect(rsd_addr) as rsd, DvtProvider(rsd) as dvt, LocationSimulation(dvt) as sim:
                await sim.set(lat, lng)
                if first:
                    print("Press ENTER to exit>", flush=True)
                    first = False
                else:
                    print("reconnected", flush=True)
                while not stop.is_set():
                    try:
                        await asyncio.wait_for(stop.wait(), RESEND_INTERVAL)
                    except asyncio.TimeoutError:
                        await sim.set(lat, lng)  # 通信を絶やさないための再送
        except Exception as e:
            if first:
                raise
            print(f"connection lost: {e!r}; retrying", flush=True)
            await asyncio.sleep(2)


async def main():
    lat, lng = float(sys.argv[1]), float(sys.argv[2])
    rsd_addr = None
    if "--rsd" in sys.argv:
        i = sys.argv.index("--rsd")
        rsd_addr = (sys.argv[i + 1], int(sys.argv[i + 2]))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def wait_stdin():
        sys.stdin.readline()
        loop.call_soon_threadsafe(stop.set)

    # daemon スレッドなので、接続失敗で終了するときに readline 待ちで固まらない
    threading.Thread(target=wait_stdin, daemon=True).start()
    await hold(lat, lng, rsd_addr, stop)


if __name__ == "__main__":
    asyncio.run(main())
