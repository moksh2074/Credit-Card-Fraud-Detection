import httpx
import asyncio
import os

async def test_auth():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Register
        auth_user = {
            "email": os.getenv("AUTH_EMAIL", "moksh@mail.com"),
            "password": os.getenv("AUTH_PASSWORD", "Moksh@1234"),
            "role": "admin",
            "org_id": "org_001"
        }
        try:
            resp = await client.post("/api/v1/auth/register", json=auth_user)
            print(f"Register: {resp.status_code} {resp.text}")
            if resp.status_code not in (201, 400):
                return
        except Exception as e:
            print(f"Register Error: {e}")
            return

        # 2. Login with the SAME credentials used for register.
        login_data = {
            "email": auth_user["email"],
            "password": auth_user["password"]
        }
        resp = await client.post("/api/v1/auth/login", json=login_data)
        print(f"Login: {resp.status_code} {resp.text}")
        if resp.status_code != 200:
            print(
                "Login failed. Make sure AUTH_EMAIL/AUTH_PASSWORD matches a registered user "
                "or delete the existing user and register again."
            )
            return
        token = resp.json().get("access_token")
        
        # 3. Verify access
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/health", headers=headers)
        print(f"Health check with JWT: {resp.status_code} {resp.json()}")

if __name__ == "__main__":
    asyncio.run(test_auth())
