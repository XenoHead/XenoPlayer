import hashlib
import json
import os
import secrets
import string
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.request
import urllib.error


def load_env(path=".env"):
    data = {}
    if not os.path.exists(path):
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    except Exception:
        pass
    return data


ENV = load_env()
API_TOKEN = ENV.get("CLOUDFLARE_API_TOKEN", "")
ACCOUNT_ID = ENV.get("CLOUDFLARE_ACCOUNT_ID", ENV.get("CLOUDFLARE_ACCOUNTID", "e94f51b0efd883f9c3b75adba9990061"))
DATABASE_ID = ENV.get("D1_DATABASE_ID", "d06fe9bd-e7f1-40dc-a72a-1dd1d6c7738c")
VALIDATE_URL = ENV.get("REG_KEY_VALIDATE_URL", "")

D1_API = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def d1_query(sql):
    """Run a SQL statement against D1 via the Cloudflare REST API. Returns rows list."""
    if not API_TOKEN:
        raise RuntimeError("CLOUDFLARE_API_TOKEN not set in .env")
    body = json.dumps({"sql": sql}).encode("utf-8")
    req = urllib.request.Request(
        D1_API,
        data=body,
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"D1 API error (HTTP {e.code}): {e.read().decode('utf-8', 'replace')}")
    except Exception as e:
        raise RuntimeError(f"D1 API request failed: {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"D1 API returned invalid JSON: {raw[:200]}")

    if not data.get("success"):
        errors = data.get("errors", [])
        msg = errors[0].get("message", "Unknown D1 error") if errors else "Unknown D1 error"
        raise RuntimeError(f"D1 query failed: {msg}")

    rows = []
    for result in data.get("result", []):
        if isinstance(result, dict) and "results" in result:
            rows.extend(result["results"])
    return rows


def list_keys():
    return d1_query(
        "SELECT id, key_hash, label, machine_id, active, created_at, last_used_at "
        "FROM reg_keys ORDER BY created_at DESC;"
    )


def create_key(label):
    plain = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))
    key_hash = sha256_hex(plain)
    d1_query(
        "INSERT INTO reg_keys (id, key_hash, label, machine_id, active, created_at) "
        "VALUES (lower(hex(randomblob(16))), '{hash}', '{label}', NULL, 1, datetime('now'));".format(
            hash=key_hash, label=label.replace("'", "''")
        )
    )
    return plain


def set_active(key_id, active):
    d1_query("UPDATE reg_keys SET active = {a} WHERE id = '{id}';".format(a=1 if active else 0, id=key_id))


def delete_key(key_id):
    d1_query("DELETE FROM reg_keys WHERE id = '{id}';".format(id=key_id))


class KeyManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("XenoPlayer - Registration Key Manager")
        self.geometry("950x540")

        self.columns = ("id", "key_hash", "label", "machine_id", "active", "created_at", "last_used_at")

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status.pack(side=tk.BOTTOM, fill=tk.X)

        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Label:").pack(side=tk.LEFT)
        self.label_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.label_var, width=24).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Create Key", command=self.on_create).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Deactivate", command=self.on_deactivate).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Reactivate", command=self.on_reactivate).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Delete", command=self.on_delete).pack(side=tk.LEFT, padx=4)

        mid = ttk.Frame(self, padding=8)
        mid.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(mid, columns=self.columns, show="headings", selectmode="extended")
        for col in self.columns:
            self.tree.heading(col, text=col.replace("_", " ").title())
            self.tree.column(col, width=130 if col != "key_hash" else 280, anchor=tk.W)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self.tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scroll.set)

        bottom = ttk.Frame(self, padding=8)
        bottom.pack(fill=tk.X)
        ttk.Label(
            bottom,
            text="Plaintext keys are shown only at creation. Copy them immediately. D1 API via Cloudflare REST (no Node required).",
        ).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        self.refresh()

    def set_status(self, msg):
        self.status_var.set(msg)
        self.update_idletasks()

    def refresh(self):
        self.set_status("Loading keys...")
        for i in self.tree.get_children():
            self.tree.delete(i)
        try:
            rows = list_keys()
        except Exception as e:
            messagebox.showerror("D1 Error", str(e))
            self.set_status("Error loading keys")
            return
        for r in rows:
            vals = [r.get(c, "") for c in self.columns]
            self.tree.insert("", tk.END, values=vals)
        self.set_status(f"{len(rows)} key(s) loaded")

    def selected_ids(self):
        return [self.tree.item(i, "values")[0] for i in self.tree.selection()]

    def on_create(self):
        label = self.label_var.get().strip()
        if not label:
            messagebox.showwarning("Missing label", "Enter a label for the key.")
            return
        try:
            plain = create_key(label)
        except Exception as e:
            messagebox.showerror("Create failed", str(e))
            self.set_status("Create failed")
            return
        self.label_var.set("")
        self.refresh()
        self.show_plaintext(plain, label)
        self.set_status("Key created")

    def show_plaintext(self, plain, label):
        win = tk.Toplevel(self)
        win.title("New Registration Key")
        win.geometry("480x230")
        win.attributes("-topmost", True)
        ttk.Label(win, text=f"Key for: {label}").pack(pady=(14, 4))
        txt = tk.Text(win, height=3, wrap=tk.WORD, font=("Consolas", 12))
        txt.insert("1.0", plain)
        txt.configure(state="disabled")
        txt.pack(padx=16, pady=4, fill=tk.X)
        ttk.Label(
            win, text="Copy this now — it will not be shown again.", foreground="#666"
        ).pack(pady=2)
        ttk.Button(win, text="OK", command=win.destroy).pack(pady=10)

    def on_deactivate(self):
        ids = self.selected_ids()
        if not ids:
            messagebox.showwarning("None selected", "Select a key to deactivate.")
            return
        try:
            for key_id in ids:
                set_active(key_id, 0)
        except Exception as e:
            messagebox.showerror("Deactivate failed", str(e))
            self.set_status("Deactivate failed")
            return
        self.refresh()
        self.set_status(f"Deactivated {len(ids)} key(s)")

    def on_reactivate(self):
        ids = self.selected_ids()
        if not ids:
            messagebox.showwarning("None selected", "Select a key to reactivate.")
            return
        try:
            for key_id in ids:
                set_active(key_id, 1)
        except Exception as e:
            messagebox.showerror("Reactivate failed", str(e))
            self.set_status("Reactivate failed")
            return
        self.refresh()
        self.set_status(f"Reactivated {len(ids)} key(s)")

    def on_delete(self):
        ids = self.selected_ids()
        if not ids:
            messagebox.showwarning("None selected", "Select a key to delete.")
            return
        if not messagebox.askyesno("Delete", f"Delete {len(ids)} key(s)? This cannot be undone."):
            return
        try:
            for key_id in ids:
                delete_key(key_id)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))
            self.set_status("Delete failed")
            return
        self.refresh()
        self.set_status(f"Deleted {len(ids)} key(s)")


if __name__ == "__main__":
    app = KeyManager()
    app.mainloop()
