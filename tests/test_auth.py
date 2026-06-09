import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_auth_flow():
    print("1. Testing unauthenticated access to /api/v1/tasks...")
    res = requests.post(f"{BASE_URL}/api/v1/tasks", json={"prompt": "Hello"})
    print(f"Status Code: {res.status_code}")
    if res.status_code == 401:
        print("Success: Unauthenticated access blocked.")
    else:
        print(f"Failed: Expected 401, got {res.status_code} - {res.text}")
        return

    print("\n2. Testing login with valid credentials...")
    res = requests.post(f"{BASE_URL}/auth/login", data={"username": "admin", "password": "secret"})
    print(f"Status Code: {res.status_code}")
    if res.status_code == 200:
        token = res.json().get("access_token")
        print(f"Success: Token received! ({token[:20]}...)")
    else:
        print(f"Failed: Expected 200, got {res.status_code} - {res.text}")
        return

    print("\n3. Testing authenticated access to /api/v1/tasks...")
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{BASE_URL}/api/v1/tasks", json={"prompt": "Hello"}, headers=headers)
    print(f"Status Code: {res.status_code}")
    if res.status_code == 200:
        print("Success: Authenticated access allowed.")
    else:
        print(f"Failed: Expected 200, got {res.status_code} - {res.text}")

if __name__ == "__main__":
    test_auth_flow()
