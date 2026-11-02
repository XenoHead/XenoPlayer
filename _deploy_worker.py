import urllib.request
import urllib.error
import secrets
import string
import json

API_TOKEN = "cfat_iNVco1KNPAMJXqE6Taqylcy2cTkaqqt1U27BedD9326721fc"
ACCOUNT_ID = "e94f51b0efd883f9c3b75adba9990061"
DATABASE_ID = "d06fe9bd-e7f1-40dc-a72a-1dd1d6c7738c"
SCRIPT_NAME = "xenoplayer-sharing-hub"

with open("cloudflare/src/reg_key_worker.js", "r", encoding="utf-8") as f:
    script = f.read()

settings = {
    "bindings": [
        {
            "type": "d1_database",
            "name": "DB",
            "database_id": DATABASE_ID,
            "database_name": "xenoplayer-sharing-hub",
        }
    ]
}

boundary = "----WebKitFormBoundary" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

parts = []
# metadata part
parts.append(f"--{boundary}")
parts.append('Content-Disposition: form-data; name="metadata"')
parts.append("Content-Type: application/json; charset=utf-8")
parts.append("")
parts.append(json.dumps(settings))
parts.append("")

# script as body_part  
parts.append(f"--{boundary}")
parts.append('Content-Disposition: form-data; name="body_part"; filename="index.js"')
parts.append("Content-Type: text/javascript; charset=utf-8")
parts.append("")
parts.append(script)
parts.append("")

parts.append(f"--{boundary}--")
parts.append("")

body = "\r\n".join(parts).encode("utf-8")

url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/workers/scripts/{SCRIPT_NAME}"
req = urllib.request.Request(
    url,
    data=body,
    headers={
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    },
    method="PUT",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("PUT:", resp.status, resp.read().decode()[:1000])
except urllib.error.HTTPError as e:
    print("PUT HTTP", e.code, e.read().decode()[:1000])
except Exception as e:
    print("PUT ERR", type(e).__name__, e)
