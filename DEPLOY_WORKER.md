# Deploy Reg-Key Worker to Cloudflare

The registration-key endpoint is served by its **own Worker** (`xenoplayer-regkeys`), separate from the
sharing hub. This is deliberate: the sharing hub hostname is behind Cloudflare Access, and the desktop
app cannot complete an interactive Access login, so `/api/reg-key/validate` on that host always fails
with HTTP 403 (`error code: 1010`).

## Prerequisites (already done)
- D1 database `d06fe9bd-e7f1-40dc-a72a-1dd1d6c7738c` exists at account `e94f51b0efd883f9c3b75adba9990061`
- `reg_keys` table migration applied (migration 0003)
- `reg_key_manager.py` GUI created
- `.env` has `REG_KEY_VALIDATE_URL`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNTID`

## Step 1: Deploy the reg-key Worker

From the `cloudflare` folder:

```powershell
npx wrangler deploy --config regkeys.wrangler.jsonc
```

The Worker is published at:
```
https://xenoplayer-regkeys.skotxeno.workers.dev
```

`.env` must point at it:

```
REG_KEY_VALIDATE_URL=https://xenoplayer-regkeys.skotxeno.workers.dev/api/reg-key/validate
```

## Step 2: Verify the endpoint

```powershell
curl.exe https://xenoplayer-regkeys.skotxeno.workers.dev/health
curl.exe -X POST -H "Content-Type: application/json" -d "{\"key\":\"test\",\"key_hash\":\"test\",\"machine_id\":\"test\"}" https://xenoplayer-regkeys.skotxeno.workers.dev/api/reg-key/validate
```

- `/health` must return `{"ok":true}`.
- The POST must return JSON `{"error":"Invalid registration key."}` with HTTP 401.

If you get HTTP 403 with `error code: 1010`, the request was sent with the default Python-urllib
User-Agent. XenoPlayer sends `User-Agent: XenoPlayer/1.0`, so any manual test must set one too.

## Step 3: Create and hand out keys

1. Run: `python reg_key_manager.py`
2. Enter a label (e.g. "Alice"), click **Create Key**
3. Copy the plaintext key shown — give it to the user
4. The key is cached locally for 30 days after first successful validation
5. You can Deactivate/Reactivate/Delete keys anytime from the GUI

The GUI footer shows the Account ID, D1 database ID, whether `CLOUDFLARE_API_TOKEN` was loaded, and the
`REG_KEY_VALIDATE_URL` in use.

## Step 4: User experience

When a user launches XenoPlayer without a valid cached key:
- A dialog prompts for their registration key
- They enter the plaintext key you gave them
- XenoPlayer validates against Cloudflare D1 (through `xenoplayer-regkeys`)
- If valid, the app starts and caches the result for 30 days

## Troubleshooting

- **HTTP 403 on validation**: the URL points at an Access-protected host, or the Worker is not deployed.
  Use `https://xenoplayer-regkeys.skotxeno.workers.dev/api/reg-key/validate`.
- **`error code: 1010`**: Cloudflare blocked the User-Agent. Send a normal UA
  (`User-Agent: XenoPlayer/1.0`).
- **D1 API 403**: `CLOUDFLARE_ACCOUNTID` in `.env` must be `e94f51b0efd883f9c3b75adba9990061`.
- **`CLOUDFLARE_API_TOKEN not set`**: the token in `.env` is empty, or `reg_key_manager.py` was started
  from a folder without `.env` (it now looks next to the script first).
- **Key bound to another machine**: keys are machine-bound on first use. Clear `machine_id` in D1 or
  delete/recreate the key.
