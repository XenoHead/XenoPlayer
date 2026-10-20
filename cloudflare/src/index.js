const SESSION_LIFETIME_MS = 30 * 24 * 60 * 60 * 1000;
const PASSWORD_ITERATIONS = 100000;
const DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
const EMAIL_CODE_LIFETIME_MS = 10 * 60 * 1000;
const EMAIL_FROM = "root@xenohead.com";

class HttpError extends Error {
    constructor(status, message, headers = {}) {
        super(message);
        this.status = status;
        this.headers = headers;
    }
}

function json(data, status = 200, headers = {}) {
    return new Response(JSON.stringify(data), {
        status,
        headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
            ...headers,
        },
    });
}

function corsHeaders() {
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-File-Name, X-Recipient-Email",
        "Access-Control-Max-Age": "86400",
    };
}

function base64Url(bytes) {
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

async function randomToken() {
    return base64Url(crypto.getRandomValues(new Uint8Array(32)));
}

async function sha256(value) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return base64Url(new Uint8Array(digest));
}

async function derivePassword(password, salt) {
    const key = await crypto.subtle.importKey(
        "raw",
        new TextEncoder().encode(password),
        "PBKDF2",
        false,
        ["deriveBits"],
    );
    const bits = await crypto.subtle.deriveBits(
        { name: "PBKDF2", hash: "SHA-256", salt, iterations: PASSWORD_ITERATIONS },
        key,
        256,
    );
    return base64Url(new Uint8Array(bits));
}

function decodeBase64Url(value) {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(normalized + "=".repeat((4 - normalized.length % 4) % 4));
    return Uint8Array.from(binary, character => character.charCodeAt(0));
}

function constantTimeEqual(left, right) {
    const leftBytes = new TextEncoder().encode(left);
    const rightBytes = new TextEncoder().encode(right);
    let difference = leftBytes.length ^ rightBytes.length;
    for (let index = 0; index < Math.max(leftBytes.length, rightBytes.length); index++) {
        difference |= (leftBytes[index] || 0) ^ (rightBytes[index] || 0);
    }
    return difference === 0;
}

async function readJson(request) {
    try {
        return await request.json();
    } catch {
        throw new HttpError(400, "Request body must be valid JSON.");
    }
}

function publicUser(row) {
    return {
        id: row.id,
        username: row.username,
        email: row.email || null,
        emailVerified: Boolean(row.email_verified_at),
        createdAt: row.created_at,
        lastSeenAt: row.last_seen_at,
    };
}

async function createSession(env, userId) {
    const token = await randomToken();
    const now = new Date();
    const expiresAt = new Date(now.getTime() + SESSION_LIFETIME_MS).toISOString();
    await env.DB.prepare(
        "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
    ).bind(await sha256(token), userId, expiresAt, now.toISOString()).run();
    return { token, expiresAt };
}

async function checkAuthRateLimit(request, env, action, maxAttempts, windowMs) {
    const clientAddress = request.headers.get("CF-Connecting-IP") || "local";
    await checkRateLimit(env, `${action}:${clientAddress}`, maxAttempts, windowMs);
}

async function checkRateLimit(env, bucket, maxAttempts, windowMs) {
    const bucketKey = await sha256(bucket);
    const now = Date.now();
    const windowStart = Math.floor(now / windowMs) * windowMs;
    const result = await env.DB.prepare(
        `INSERT INTO auth_rate_limits (bucket_key, window_start, attempts)
         VALUES (?, ?, 1)
         ON CONFLICT (bucket_key) DO UPDATE SET
           attempts = CASE WHEN window_start = excluded.window_start THEN attempts + 1 ELSE 1 END,
           window_start = excluded.window_start
         RETURNING attempts`,
    ).bind(bucketKey, windowStart).first();
    await env.DB.prepare("DELETE FROM auth_rate_limits WHERE window_start < ?")
        .bind(now - 24 * 60 * 60 * 1000).run();
    if (result.attempts > maxAttempts) {
        const retryAfter = Math.ceil((windowStart + windowMs - now) / 1000);
        throw new HttpError(429, "Too many attempts. Please try again later.", { "Retry-After": String(retryAfter) });
    }
}

function normalizeEmail(value) {
    if (typeof value !== "string") return "";
    const email = value.trim().toLowerCase();
    return /^[a-z0-9][a-z0-9._+-]{0,63}@xenohead\.com$/.test(email) ? email : "";
}

async function requestEmailCode(request, env) {
    const body = await readJson(request);
    const email = normalizeEmail(body.email);
    if (!email) throw new HttpError(400, "Enter a valid @xenohead.com email address.");
    if (!env.EMAIL) throw new HttpError(503, "Email verification is not configured yet.");

    const clientAddress = request.headers.get("CF-Connecting-IP") || "local";
    await checkRateLimit(env, `email-code-ip:${clientAddress}`, 10, 60 * 60 * 1000);
    await checkRateLimit(env, `email-code-address:${email}`, 3, 60 * 60 * 1000);

    const code = String(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000).padStart(6, "0");
    const now = new Date();
    const expiresAt = new Date(now.getTime() + EMAIL_CODE_LIFETIME_MS).toISOString();
    const codeHash = await sha256(`${email}:${code}`);
    await env.DB.prepare(
        `INSERT INTO email_verification_codes (email, code_hash, expires_at, created_at, attempts)
         VALUES (?, ?, ?, ?, 0)
         ON CONFLICT (email) DO UPDATE SET
           code_hash = excluded.code_hash,
           expires_at = excluded.expires_at,
           created_at = excluded.created_at,
           attempts = 0`,
    ).bind(email, codeHash, expiresAt, now.toISOString()).run();

    try {
        await env.EMAIL.send({
            to: email,
            from: EMAIL_FROM,
            subject: "Your XenoPlayer Sharing Hub verification code",
            text: `Your XenoPlayer verification code is ${code}. It expires in 10 minutes. If you did not request this, you can ignore this email.`,
            html: `<p>Your XenoPlayer verification code is <strong>${code}</strong>.</p><p>It expires in 10 minutes. If you did not request this, you can ignore this email.</p>`,
        });
    } catch (error) {
        await env.DB.prepare("DELETE FROM email_verification_codes WHERE email = ? AND code_hash = ?")
            .bind(email, codeHash).run();
        console.error("Email verification delivery failed:", error?.code || "unknown");
        throw new HttpError(502, "The verification email could not be sent. Try again later.");
    }

    return json({ ok: true, expiresInSeconds: EMAIL_CODE_LIFETIME_MS / 1000 });
}

async function consumeEmailCode(env, email, code) {
    const normalizedCode = typeof code === "string" ? code.trim() : "";
    if (!/^\d{6}$/.test(normalizedCode)) {
        throw new HttpError(400, "Enter the six-digit email verification code.");
    }
    const now = new Date().toISOString();
    const record = await env.DB.prepare(
        `UPDATE email_verification_codes
         SET attempts = attempts + 1
         WHERE email = ? AND expires_at > ? AND attempts < 5
         RETURNING code_hash`,
    ).bind(email, now).first();
    if (!record) throw new HttpError(400, "The verification code is invalid or expired.");
    const suppliedHash = await sha256(`${email}:${normalizedCode}`);
    if (!constantTimeEqual(suppliedHash, record.code_hash)) {
        throw new HttpError(400, "The verification code is invalid or expired.");
    }
    await env.DB.prepare("DELETE FROM email_verification_codes WHERE email = ? AND code_hash = ?")
        .bind(email, record.code_hash).run();
}

async function requireUser(request, env) {
    const authorization = request.headers.get("Authorization") || "";
    const match = authorization.match(/^Bearer\s+([A-Za-z0-9_-]{40,})$/i);
    if (!match) throw new HttpError(401, "Please sign in.");

    const now = new Date().toISOString();
    const row = await env.DB.prepare(
        `SELECT users.id, users.username, users.email, users.email_verified_at,
                users.created_at, users.last_seen_at
         FROM sessions JOIN users ON users.id = sessions.user_id
         WHERE sessions.token_hash = ? AND sessions.expires_at > ?`,
    ).bind(await sha256(match[1]), now).first();
    if (!row) throw new HttpError(401, "Session expired. Please sign in again.");

    await env.DB.prepare("UPDATE users SET last_seen_at = ? WHERE id = ?")
        .bind(now, row.id).run();
    row.last_seen_at = now;
    return { user: publicUser(row), tokenHash: await sha256(match[1]) };
}

function requireVerifiedEmail(user) {
    if (!user.email || !user.emailVerified || !normalizeEmail(user.email)) {
        throw new HttpError(403, "Verify your @xenohead.com email address before using Sharing Hub.");
    }
}

async function register(request, env) {
    await checkAuthRateLimit(request, env, "register", 20, 60 * 60 * 1000);
    const body = await readJson(request);
    const username = typeof body.username === "string" ? body.username.trim() : "";
    const password = typeof body.password === "string" ? body.password : "";
    const email = normalizeEmail(body.email);
    if (!email) throw new HttpError(400, "Enter a valid @xenohead.com email address.");
    if (!/^[A-Za-z0-9_.-]{3,32}$/.test(username)) {
        throw new HttpError(400, "Username must be 3–32 characters using letters, numbers, ., _ or -.");
    }
    if (password.length < 8 || new TextEncoder().encode(password).length > 256) {
        throw new HttpError(400, "Password must be at least 8 characters and no more than 256 bytes.");
    }

    await consumeEmailCode(env, email, body.verificationCode);
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const now = new Date().toISOString();
    const user = {
        id: crypto.randomUUID(),
        username,
        email,
        email_verified_at: now,
        password_hash: await derivePassword(password, salt),
        password_salt: base64Url(salt),
        created_at: now,
        last_seen_at: now,
    };
    try {
        await env.DB.prepare(
            `INSERT INTO users
             (id, username, email, email_verified_at, password_hash, password_salt, created_at, last_seen_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        ).bind(
            user.id, user.username, user.email, user.email_verified_at,
            user.password_hash, user.password_salt, now, now,
        ).run();
    } catch (error) {
        if (String(error?.message || error).includes("UNIQUE constraint failed: users.username")) {
            throw new HttpError(409, "That username is already taken.");
        }
        if (String(error?.message || error).includes("users.email")) {
            throw new HttpError(409, "That email address is already registered.");
        }
        throw error;
    }

    const session = await createSession(env, user.id);
    return json({ user: publicUser(user), ...session }, 201);
}

async function login(request, env) {
    await checkAuthRateLimit(request, env, "login", 10, 15 * 60 * 1000);
    const body = await readJson(request);
    const username = typeof body.username === "string" ? body.username.trim() : "";
    const password = typeof body.password === "string" ? body.password : "";
    if (!username || !password) throw new HttpError(400, "Enter a username and password.");

    const row = await env.DB.prepare(
        `SELECT id, username, email, email_verified_at, password_hash, password_salt,
                created_at, last_seen_at
         FROM users WHERE username = ?`,
    ).bind(username).first();
    if (!row) throw new HttpError(401, "Incorrect username or password.");
    const actualHash = await derivePassword(password, decodeBase64Url(row.password_salt));
    if (!constantTimeEqual(actualHash, row.password_hash)) {
        throw new HttpError(401, "Incorrect username or password.");
    }

    const now = new Date().toISOString();
    await env.DB.prepare("UPDATE users SET last_seen_at = ? WHERE id = ?").bind(now, row.id).run();
    row.last_seen_at = now;
    const session = await createSession(env, row.id);
    return json({ user: publicUser(row), ...session });
}

async function getShares(env, userId) {
    const results = await env.DB.prepare(
        `SELECT id, kind, title, file_name, recipient_email, mime_type, size_bytes, created_at
         FROM shares WHERE user_id = ? ORDER BY created_at DESC`,
    ).bind(userId).all();
    return results.results;
}

function safeFileName(value) {
    const name = value.replace(/[\\/<>:"|?*\u0000-\u001f]/g, "_").trim();
    return (name || "encrypted-share.zip").slice(0, 240);
}

function encodeFileName(value) {
    return encodeURIComponent(value).replace(/['()*]/g, character =>
        `%${character.charCodeAt(0).toString(16).toUpperCase()}`,
    );
}

function isValidHttpUrl(value) {
    try {
        const url = new URL(value);
        return url.protocol === "http:" || url.protocol === "https:";
    } catch {
        return false;
    }
}

async function createLink(request, env, userId) {
    const body = await readJson(request);
    const targetUrl = typeof body.url === "string" ? body.url.trim() : "";
    if (targetUrl.length > 2048 || !isValidHttpUrl(targetUrl)) {
        throw new HttpError(400, "Enter a valid http or https URL (up to 2048 characters).");
    }
    const title = typeof body.title === "string" ? body.title.trim().slice(0, 200) : "";
    const id = crypto.randomUUID();
    const createdAt = new Date().toISOString();
    await env.DB.prepare(
        `INSERT INTO shares
         (id, user_id, kind, title, target_url, created_at)
         VALUES (?, ?, 'link', ?, ?, ?)`,
    ).bind(id, userId, title || targetUrl, targetUrl, createdAt).run();
    return json({ id, kind: "link", title: title || targetUrl, createdAt }, 201);
}

async function createFile(request, env, userId) {
    if (!env.FILES) throw new HttpError(503, "File sharing storage is not enabled yet.");
    if (!request.body) throw new HttpError(400, "No file was supplied.");
    const recipientEmail = normalizeEmail(request.headers.get("X-Recipient-Email"));
    if (!recipientEmail) throw new HttpError(400, "Enter the recipient's @xenohead.com email address.");
    const maxBytes = Number.parseInt(env.MAX_UPLOAD_BYTES || "", 10) || DEFAULT_MAX_UPLOAD_BYTES;
    const contentLength = request.headers.get("Content-Length");
    if (contentLength === null) throw new HttpError(411, "The file size could not be determined.");
    const announcedSize = Number(contentLength);
    if (!Number.isSafeInteger(announcedSize) || announcedSize < 0) {
        throw new HttpError(400, "The file size is invalid.");
    }
    if (announcedSize < 52) throw new HttpError(400, "The encrypted archive is incomplete.");
    if (announcedSize > maxBytes) {
        throw new HttpError(413, "The encrypted archive exceeds the 100 MB upload limit.");
    }

    let requestedName = request.headers.get("X-File-Name") || "shared-file";
    try {
        requestedName = decodeURIComponent(requestedName);
    } catch {
        throw new HttpError(400, "The file name is invalid.");
    }
    const fileName = safeFileName(requestedName);
    const objectKey = crypto.randomUUID();
    const id = crypto.randomUUID();
    const createdAt = new Date().toISOString();
    const stored = await env.FILES.put(objectKey, request.body, {
        httpMetadata: { contentType: "application/octet-stream" },
    });
    if (stored.size !== announcedSize) {
        await env.FILES.delete(objectKey);
        throw new HttpError(400, "The uploaded file size did not match the request.");
    }
    try {
        await env.DB.prepare(
            `INSERT INTO shares
             (id, user_id, kind, title, object_key, file_name, recipient_email, mime_type, size_bytes, created_at)
             VALUES (?, ?, 'file', ?, ?, ?, ?, ?, ?, ?)`,
        ).bind(
            id, userId, "Encrypted archive", objectKey, fileName, recipientEmail,
            "application/octet-stream", stored.size, createdAt,
        ).run();
    } catch (error) {
        await env.FILES.delete(objectKey);
        throw error;
    }
    return json({
        id,
        kind: "file",
        title: "Encrypted archive",
        recipientEmail,
        fileName,
        sizeBytes: stored.size,
        createdAt,
    }, 201);
}

async function getRecipientShare(env, id, email) {
    const row = await env.DB.prepare(
        `SELECT id, file_name, mime_type, size_bytes, object_key, created_at
         FROM shares WHERE id = ? AND kind = 'file' AND recipient_email = ?`,
    ).bind(id, email).first();
    if (!row) throw new HttpError(404, "This share is not available to this account.");
    return row;
}

async function downloadShare(env, row) {
    const object = await env.FILES.get(row.object_key);
    if (!object) throw new HttpError(404, "The shared file is no longer available.");
    const headers = new Headers(corsHeaders());
    headers.set("Content-Type", "application/octet-stream");
    headers.set("Content-Length", String(object.size));
    headers.set("Content-Disposition", `attachment; filename*=UTF-8''${encodeFileName(row.file_name || "encrypted-share.zip")}`);
    headers.set("Cache-Control", "private, no-store");
    return new Response(object.body, { headers });
}

async function getSharePage(request, env) {
    const id = new URL(request.url).pathname.slice(3);
    const share = await env.DB.prepare("SELECT kind, target_url FROM shares WHERE id = ?")
        .bind(id).first();
    if (!share) throw new HttpError(404, "This share link does not exist.");
    if (share.kind === "link") return Response.redirect(share.target_url, 302);
    if (!env.ASSETS) throw new HttpError(503, "The encrypted share page is unavailable.");
    const page = await env.ASSETS.fetch(new Request(new URL("/share.html", request.url)));
    if (!page.ok) throw new HttpError(503, "The encrypted share page is unavailable.");
    const headers = new Headers(page.headers);
    headers.set("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
    headers.set("Referrer-Policy", "no-referrer");
    headers.set("X-Content-Type-Options", "nosniff");
    headers.set("Cache-Control", "no-store");
    return new Response(page.body, { status: 200, headers });
}

async function route(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders() });

    if (path === "/health" && request.method === "GET") {
        return json({ ok: true });
    }
    if (path === "/api/email/code" && request.method === "POST") return requestEmailCode(request, env);
    if (path === "/api/register" && request.method === "POST") return register(request, env);
    if (path === "/api/login" && request.method === "POST") return login(request, env);
    if (path.startsWith("/s/") && request.method === "GET") {
        const id = path.slice(3);
        if (!/^[0-9a-f-]{36}$/i.test(id)) throw new HttpError(404, "This share link does not exist.");
        return getSharePage(request, env);
    }

    if (path.startsWith("/api/")) {
        const { user, tokenHash } = await requireUser(request, env);
        if (path === "/api/me" && request.method === "GET") return json({ user });
        if (path === "/api/email/attach" && request.method === "POST") {
            if (user.email) throw new HttpError(409, "This account already has a verified email address.");
            const body = await readJson(request);
            const email = normalizeEmail(body.email);
            if (!email) throw new HttpError(400, "Enter a valid @xenohead.com email address.");
            await consumeEmailCode(env, email, body.verificationCode);
            let result;
            try {
                result = await env.DB.prepare(
                    `UPDATE users SET email = ?, email_verified_at = ?
                     WHERE id = ? AND email IS NULL`,
                ).bind(email, new Date().toISOString(), user.id).run();
            } catch (error) {
                if (String(error?.message || error).includes("users.email")) {
                    throw new HttpError(409, "That email address is already registered.");
                }
                throw error;
            }
            if (result.meta?.changes !== 1) {
                throw new HttpError(409, "This account already has a verified email address.");
            }
            return json({ user: { ...user, email, emailVerified: true } });
        }
        if (path === "/api/logout" && request.method === "POST") {
            await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(tokenHash).run();
            return json({ ok: true });
        }
        if (path === "/api/users" && request.method === "GET") {
            const result = await env.DB.prepare(
                "SELECT id, username, created_at, last_seen_at FROM users ORDER BY username COLLATE NOCASE",
            ).all();
            return json({ users: result.results.map(publicUser) });
        }
        if (path === "/api/shares" && request.method === "GET") {
            requireVerifiedEmail(user);
            return json({ shares: await getShares(env, user.id) });
        }
        if (path === "/api/shares/link" && request.method === "POST") {
            requireVerifiedEmail(user);
            return createLink(request, env, user.id);
        }
        if (path === "/api/shares/file" && request.method === "POST") {
            requireVerifiedEmail(user);
            return createFile(request, env, user.id);
        }
        const recipientShareMatch = path.match(/^\/api\/shares\/([0-9a-f-]{36})(?:\/(download))?$/i);
        if (recipientShareMatch && request.method === "GET") {
            requireVerifiedEmail(user);
            const share = await getRecipientShare(env, recipientShareMatch[1], user.email);
            if (recipientShareMatch[2] === "download") return downloadShare(env, share);
            return json({
                id: share.id,
                fileName: share.file_name,
                sizeBytes: share.size_bytes,
                createdAt: share.created_at,
            });
        }
        const shareMatch = path.match(/^\/api\/shares\/([0-9a-f-]{36})$/i);
        if (shareMatch && request.method === "DELETE") {
            const share = await env.DB.prepare(
                "SELECT object_key FROM shares WHERE id = ? AND user_id = ?",
            ).bind(shareMatch[1], user.id).first();
            if (!share) throw new HttpError(404, "Share not found.");
            if (share.object_key && env.FILES) await env.FILES.delete(share.object_key);
            await env.DB.prepare("DELETE FROM shares WHERE id = ? AND user_id = ?")
                .bind(shareMatch[1], user.id).run();
            return json({ ok: true });
        }
    }
    if (env.ASSETS) {
        const asset = await env.ASSETS.fetch(request);
        if (asset.status !== 404) return asset;
    }
    throw new HttpError(404, "Not found.");
}

export default {
    async fetch(request, env) {
        try {
            const response = await route(request, env);
            const headers = new Headers(response.headers);
            for (const [key, value] of Object.entries(corsHeaders())) headers.set(key, value);
            return new Response(response.body, {
                status: response.status,
                statusText: response.statusText,
                headers,
            });
        } catch (error) {
            if (error instanceof HttpError) {
                return json({ error: error.message }, error.status, { ...corsHeaders(), ...error.headers });
            }
            console.error("Share API request failed:", error);
            return json({ error: "The request could not be completed." }, 500, corsHeaders());
        }
    },
};
