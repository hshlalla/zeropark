import requests

BASE_URL = "http://127.0.0.1:8000"

def get_token(username, password):
    res = requests.post(f"{BASE_URL}/auth/login", data={"username": username, "password": password})
    if res.status_code == 200:
        return res.json().get("access_token")
    return None

def test_rbac():
    print("--- RBAC Access Control Tests ---\n")
    
    # 1. Login as user1
    user1_token = get_token("user1", "secret")
    print(f"User1 Token Acquired: {'Yes' if user1_token else 'No'}")
    
    # 2. Login as admin
    admin_token = get_token("admin", "secret")
    print(f"Admin Token Acquired: {'Yes' if admin_token else 'No'}")
    
    # 3. User1 attempts to access Admin API
    print("\n[Test 1] User1 -> Admin API (/api/v1/admin/system-status)")
    res = requests.get(f"{BASE_URL}/api/v1/admin/system-status", headers={"Authorization": f"Bearer {user1_token}"})
    print(f"Status Code: {res.status_code}")
    if res.status_code == 403:
        print("Success: User1 blocked as expected (403 Forbidden).")
    else:
        print(f"Failed: User1 received {res.status_code}")
        
    # 4. Admin attempts to access Admin API
    print("\n[Test 2] Admin -> Admin API (/api/v1/admin/system-status)")
    res = requests.get(f"{BASE_URL}/api/v1/admin/system-status", headers={"Authorization": f"Bearer {admin_token}"})
    print(f"Status Code: {res.status_code}")
    if res.status_code == 200:
        print("Success: Admin allowed to access Admin API.")
        print(f"Response: {res.json()}")
    else:
        print(f"Failed: Admin received {res.status_code}")
        
    # 5. User1 attempts to access User API
    print("\n[Test 3] User1 -> User API (/api/v1/tasks)")
    res = requests.post(f"{BASE_URL}/api/v1/tasks", json={"prompt": "test"}, headers={"Authorization": f"Bearer {user1_token}"})
    print(f"Status Code: {res.status_code}")
    if res.status_code in [200, 503, 400]: # Since providers may not be registered perfectly, it might throw 503/400. Important part is it's NOT 401/403
        print("Success: User1 passed Auth middleware and reached Business logic.")
    else:
        print(f"Failed: User1 received unexpected status {res.status_code}")

if __name__ == "__main__":
    test_rbac()
