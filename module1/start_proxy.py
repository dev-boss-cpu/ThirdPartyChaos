"""
ThirdPartyChaos -- Module 1: Proxy Starter
Starts mitmproxy with the InterceptorAddon and (optionally) loads
Module 2's failure injector into the same process so chaos hooks work.
Usage: python start_proxy.py --port 8080
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Ensure module1 and module2 are on sys.path
HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "module2"))


async def _run(port: int) -> None:
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster

    # Load Module 2 failure injector (registers chaos hook in this process)
    try:
        import failure_injector  # noqa: F401
        print("[TPC] Module 2 failure injector loaded — chaos hook registered.")
    except ImportError:
        print("[TPC] Module 2 not found — proxy runs without fault injection.")

    from interceptor import InterceptorAddon

    opts = Options(listen_host="0.0.0.0", listen_port=port)
    master = DumpMaster(opts, with_termlog=True, with_dumper=False)
    master.addons.add(InterceptorAddon())

    print(f"[TPC M1] Proxy listening on port {port}")
    print("[TPC M1] Set HTTP_PROXY=http://localhost:{} in your app".format(port))
    try:
        await master.run()
    except KeyboardInterrupt:
        master.shutdown()
        print("\n[TPC M1] Proxy stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ThirdPartyChaos M1 Proxy")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    asyncio.run(_run(args.port))
