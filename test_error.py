import requests

response = requests.post(
    "http://localhost:5000/api/chat",
    json={"message": "80", "session_id": "test_session_bug"}
)
print(response.status_code)
print(response.text)
