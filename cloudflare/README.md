# XenoPlayer Sharing Hub

The Worker enforces `@xenohead.com` email verification and sends one-time codes through Cloudflare Email Sending. File contents are wrapped in two nested AES-256 encrypted ZIP archives in the browser before upload. R2 stores only the encrypted outer archive; the two generated passwords are shown to the sender once and must be passed to the recipient separately from the share link.

## Configure Cloudflare resources

Update `wrangler.jsonc` with the existing D1 database ID and R2 bucket name. These values were not available in the repository, so the config intentionally contains placeholders rather than guessed production resource identifiers.

The sender address is fixed to `root@xenohead.com` in `src/index.js`. Before using email verification, ensure the `xenohead.com` domain is enabled for Email Sending and the Worker has the `EMAIL` `send_email` binding. Cloudflare currently requires a Workers Paid plan for sending to arbitrary recipient addresses.

## Build and run

From `web`, install the locked dependencies, build the browser ZIP module, and run its tests:

```powershell
npm ci
npm run build:share-crypto
npm test
```

From `cloudflare`, run the Worker tests and apply D1 migrations only after the resource IDs are configured:

```powershell
npm test
npx wrangler d1 migrations apply DB --remote
npx wrangler deploy
```

No email is sent and no Cloudflare resource is changed by the local tests. The optional sender PIN is not part of this initial version.
