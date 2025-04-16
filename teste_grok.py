import requests
from config_grok import XAI_API_KEY, XAI_API_URL

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {XAI_API_KEY}"
}
payload = {
    "messages": [
        {"role": "system", "content": "You are a test assistant."},
        {"role": "user", "content": "Testing. Just say hi and hello world and nothing else."}
    ],
    "model": "grok-3-latest",
    "stream": False,
    "temperature": 0
}
response = requests.post(f"{XAI_API_URL}/chat/completions", json=payload, headers=headers)
print(response.json())
