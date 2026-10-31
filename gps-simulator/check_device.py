"""
動作チェック: 位置を変更する直前（DVT の位置シミュレーション機能を開くところ）まで確認して終了する。
位置は変更しない。成功すると "CHECK OK" を出力する。

usage: python check_device.py [--rsd HOST PORT]
"""
import asyncio
import sys

from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation


async def main():
    if "--rsd" in sys.argv:
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        i = sys.argv.index("--rsd")
        ctx = RemoteServiceDiscoveryService((sys.argv[i + 1], int(sys.argv[i + 2])))
    else:
        from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
        ctx = UserspaceRsdTunnel()
    async with ctx as rsd, DvtProvider(rsd) as dvt, LocationSimulation(dvt):
        print(f"CHECK OK (iOS {rsd.product_version})", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
