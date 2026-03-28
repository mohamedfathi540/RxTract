
import asyncio
import httpx
import sys

BASE_URL = "http://0.0.0.0:5000"

async def check_health():
    print(f"Checking health at {BASE_URL}/api/v1/...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/v1/")
            if response.status_code == 200:
                print("[OK] Health check passed!")
                print(f"Response: {response.json()}")
                return True
            else:
                print(f"[ERR] Health check failed with status code: {response.status_code}")
                print(f"Response: {response.text}")
                return False
    except httpx.ConnectError:
        print(f"[ERR] Could not connect to {BASE_URL}. Is the server running?")
        return False
    except Exception as e:
        print(f"[ERR] An error occurred: {e}")
        return False

async def main():
    print("Starting verification...")
    health_ok = await check_health()
    
    if health_ok:
        print("\n[OK] Basic verification passed! The server is running and responsive.")
        sys.exit(0)
    else:
        print("\n[WARN] Verification failed. Please check the logs and ensure the server is running.")
        sys.exit(1)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
