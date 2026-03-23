
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path.cwd()))

from modules.server import start_server

async def main():
    print("Starting server test...")
    # Run for 5 seconds then exit? 
    # Hard to cancel uvicorn from outside without a signal or task cancel.
    # We will just try to start it and see if it crashes immediately.
    try:
        await start_server()
    except Exception as e:
        print(f"CAUGHT ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
