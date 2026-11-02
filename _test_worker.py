import urllib.request
import urllib.error

urls = [
    "https://xenoplayer-sharing-hub.skotxeno.workers.dev/health",
    "https://xenoplayer-sharing-hub.skotxeno.workers.dev/",
]
for url in urls:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"{url}: STATUS {resp.status} -> {resp.read().decode()[:200]}")
    except urllib.error.HTTPError as e:
        print(f"{url}: HTTP {e.code} -> {e.read().decode()[:200]}")
    except Exception as e:
        print(f"{url}: ERR {type(e).__name__} {e}")
