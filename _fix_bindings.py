import urllib.request
import urllib.error

API_TOKEN = "cfat_iNVco1KNPAMJXqE6Taqylcy2cTkaqqt1U27BedD9326721fc"
ACCOUNT_ID = "e94f51b0efd883f9c3b75adba9990061"
SCRIPT_NAME = "xenoplayer-sharing-hub"

# Update bindings via multipart/form-data PATCH
boundary = "----WebKitFormBoundary" + "".join(__import__("secrets").choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(16))

parts = []
parts.append(f"--{boundary}")
parts.append('Content-Disposition: form-data; name="bindings"')
parts.append("")
parts.append("[]")
parts.append(f"--{boundary}--")
parts.append("")

body = "\r\n".join(parts).encode("utf-8")

url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/workers/scripts/{SCRIPT_NAME}/settings"
req = urllib.request.Request(
    url,
    data=body,
    headers={
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    },
    method="PATCH",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("SETTINGS PATCH:", resp.status, resp.read().decode()[:1000])
except urllib.error.HTTPError as e:
    print("SETTINGS HTTP", e.code, e.read().decode()[:1000])
except Exception as e:
    print("SETTINGS ERR", type(e).__name__, e)
