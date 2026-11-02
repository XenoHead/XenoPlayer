import urllib.request
import urllib.error
import json

url = "https://xenoplayer-sharing-hub.skotxeno.workers.dev/api/reg-key/validate"
body = json.dumps({"key": "test"}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print("STATUS", resp.status)
        print(resp.read().decode()[:500])
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:500])
except Exception as e:
    print("ERR", type(e).__name__, e)
