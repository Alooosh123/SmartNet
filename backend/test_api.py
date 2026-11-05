import httpx
from pathlib import Path

BASE = 'http://127.0.0.1:8000'

client = httpx.Client(timeout=10.0)

print('=== 1. Root and Health Endpoints ===')
resp = client.get(BASE + '/')
print('GET / ->', resp.status_code, resp.json())
assert resp.status_code == 200

resp = client.get(BASE + '/api/health')
print('GET /api/health ->', resp.status_code, resp.json())
assert resp.status_code == 200

print('\n=== 2. Security Test: MikroTik Endpoints without Auth ===')
resp = client.get(BASE + '/mikrotik/status')
print('Unauthenticated GET /mikrotik/status ->', resp.status_code, resp.json())
assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
print('PASS: Endpoint correctly protected against unauthorized access!')

print('\n=== 3. Admin Authentication ===')
resp = client.post(BASE + '/auth/login', data={'username': 'admin', 'password': 'admin123'})
print('POST /auth/login ->', resp.status_code)
assert resp.status_code == 200, f"Login failed: {resp.text}"
token = resp.json().get('access_token')
admin_headers = {'Authorization': f'Bearer {token}'}
print('Admin Token obtained successfully, role:', resp.json().get('role'))

print('\n=== 4. Authenticated MikroTik Access ===')
resp = client.get(BASE + '/mikrotik/status', headers=admin_headers)
print('Auth GET /mikrotik/status ->', resp.status_code, resp.json().get('platform'))
assert resp.status_code == 200

resp = client.get(BASE + '/mikrotik/users', headers=admin_headers)
users = resp.json()
print('Auth GET /mikrotik/users -> count:', len(users))
assert resp.status_code == 200

print('\n=== 5. Disconnect User Endpoint ===')
resp = client.post(BASE + '/mikrotik/users/user_demo_1/disconnect', headers=admin_headers)
print('POST /mikrotik/users/user_demo_1/disconnect ->', resp.status_code, resp.json())
assert resp.status_code == 200

print('\n=== 6. Cards Generation and Styled PDF Download ===')
payload = {'count': 2, 'profile': '1 Day', 'length': 6, 'hide_password': False}
resp = client.post(BASE + '/cards/generate', json=payload, headers=admin_headers)
print('POST /cards/generate ->', resp.status_code)
assert resp.status_code == 200
batch = resp.json()
batch_id = batch.get('id')

resp = client.get(BASE + f'/cards/{batch_id}/pdf', headers=admin_headers)
print(f'GET /cards/{batch_id}/pdf ->', resp.status_code, 'Bytes:', len(resp.content), 'Content-Type:', resp.headers.get('content-type'))
assert resp.status_code == 200
assert len(resp.content) > 1000

print('\n=== 7. Client Registration & Secure Webhook Confirmation ===')
test_client_user = f"client_test_{batch_id}"
resp = client.post(BASE + '/auth/register', json={'username': test_client_user, 'password': 'Password123'})
print('POST /auth/register ->', resp.status_code, resp.json())
assert resp.status_code == 200
reg_id = resp.json().get('registration_id')

# Test unauthorized confirmation attempt (should fail without secret)
resp_unauth = client.post(BASE + f'/auth/registrations/{reg_id}/confirm?days=30')
print('Unauthenticated Webhook Confirm ->', resp_unauth.status_code)
assert resp_unauth.status_code == 401
print('PASS: Webhook confirmation correctly rejected without secret!')

# Confirm with correct secret
resp_confirm = client.post(BASE + f'/auth/registrations/{reg_id}/confirm?days=30&secret=smartnet-webhook-secret-key')
print('Authorized Webhook Confirm ->', resp_confirm.status_code, resp_confirm.json())
assert resp_confirm.status_code == 200
assert resp_confirm.json().get('paid') is True
assert resp_confirm.json().get('processed') is False

# Payment confirmation only marks the request as paid; admin approval creates the client.
resp_approve = client.post(BASE + f'/auth/registrations/{reg_id}/approve?days=30', headers=admin_headers)
print('Admin approval after payment ->', resp_approve.status_code, resp_approve.json())
assert resp_approve.status_code == 200

print('\n=== 8. Client Login ===')
resp_client_login = client.post(BASE + '/auth/login', data={'username': test_client_user, 'password': 'Password123'})
print('Client login ->', resp_client_login.status_code, 'role:', resp_client_login.json().get('role'))
assert resp_client_login.status_code == 200
client_token = resp_client_login.json().get('access_token')
client_headers = {'Authorization': f'Bearer {client_token}'}

print('\n=== 9. Authenticated Chat Test ===')
resp_chat = client.post(BASE + '/client/chat', json={'message': 'كيف يمكنني تجديد اشتراكي؟'}, headers=client_headers)
print('POST /client/chat ->', resp_chat.status_code, 'Reply:', resp_chat.json().get('reply'))
assert resp_chat.status_code == 200

resp_get_chat = client.get(BASE + f'/client/chat?username={test_client_user}', headers=client_headers)
print('GET /client/chat -> count:', len(resp_get_chat.json()))
assert resp_get_chat.status_code == 200

print('\n🎉 ALL INTEGRATION AND SECURITY TESTS PASSED SUCCESSFULLY! 🎉')
client.close()

