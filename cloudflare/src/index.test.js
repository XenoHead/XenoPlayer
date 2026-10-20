import assert from "node:assert/strict";
import test from "node:test";
import worker from "./index.js";

const shareId = "123e4567-e89b-42d3-a456-426614174000";
const encryptedBytes = new Uint8Array(64).fill(42);

async function hashToken(token) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
    let binary = "";
    for (const byte of new Uint8Array(digest)) binary += String.fromCharCode(byte);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

class ShareTestDatabase {
    constructor(users, sessions, share) {
        this.users = users;
        this.sessions = sessions;
        this.share = share;
    }

    prepare(sql) {
        const db = this;
        return {
            bind(...values) {
                return {
                    async first() {
                        if (sql.includes("FROM sessions JOIN users")) {
                            const [tokenHash, currentTime] = values;
                            const session = db.sessions.find(row =>
                                row.token_hash === tokenHash && row.expires_at > currentTime,
                            );
                            if (!session) return null;
                            const user = db.users.find(row => row.id === session.user_id);
                            return user ? { ...user } : null;
                        }
                        if (sql.includes("FROM shares WHERE id = ? AND kind = 'file'")) {
                            const [id, email] = values;
                            return db.share.id === id && db.share.recipient_email === email
                                ? { ...db.share }
                                : null;
                        }
                        throw new Error(`Unexpected test query: ${sql}`);
                    },
                    async run() {
                        if (sql.startsWith("UPDATE users SET last_seen_at")) return { meta: { changes: 1 } };
                        throw new Error(`Unexpected test command: ${sql}`);
                    },
                };
            },
        };
    }
}

class VerificationTestDatabase {
    constructor() {
        this.rateLimits = new Map();
        this.codes = new Map();
    }

    prepare(sql) {
        const db = this;
        return {
            bind(...values) {
                return {
                    async first() {
                        if (sql.includes("INSERT INTO auth_rate_limits")) {
                            const [key, windowStart] = values;
                            const current = db.rateLimits.get(key);
                            const attempts = current?.windowStart === windowStart ? current.attempts + 1 : 1;
                            db.rateLimits.set(key, { windowStart, attempts });
                            return { attempts };
                        }
                        throw new Error(`Unexpected test query: ${sql}`);
                    },
                    async run() {
                        if (sql.startsWith("DELETE FROM auth_rate_limits")) return { meta: { changes: 0 } };
                        if (sql.includes("INSERT INTO email_verification_codes")) {
                            const [email, codeHash, expiresAt, createdAt] = values;
                            db.codes.set(email, { codeHash, expiresAt, createdAt });
                            return { meta: { changes: 1 } };
                        }
                        throw new Error(`Unexpected test command: ${sql}`);
                    },
                };
            },
        };
    }
}

async function makeEnvironment() {
    const ownerToken = "O".repeat(48);
    const recipientToken = "R".repeat(48);
    const expiredEmailToken = "U".repeat(48);
    const users = [
        {
            id: "owner-id",
            username: "owner",
            email: "sender@xenohead.com",
            email_verified_at: "2026-01-01T00:00:00.000Z",
            created_at: "2026-01-01T00:00:00.000Z",
            last_seen_at: "2026-01-01T00:00:00.000Z",
        },
        {
            id: "recipient-id",
            username: "recipient",
            email: "recipient@xenohead.com",
            email_verified_at: "2026-01-01T00:00:00.000Z",
            created_at: "2026-01-01T00:00:00.000Z",
            last_seen_at: "2026-01-01T00:00:00.000Z",
        },
        {
            id: "unverified-id",
            username: "unverified",
            email: "unverified@xenohead.com",
            email_verified_at: null,
            created_at: "2026-01-01T00:00:00.000Z",
            last_seen_at: "2026-01-01T00:00:00.000Z",
        },
    ];
    const sessions = [
        { token_hash: await hashToken(ownerToken), user_id: "owner-id", expires_at: "2999-01-01T00:00:00.000Z" },
        { token_hash: await hashToken(recipientToken), user_id: "recipient-id", expires_at: "2999-01-01T00:00:00.000Z" },
        { token_hash: await hashToken(expiredEmailToken), user_id: "unverified-id", expires_at: "2999-01-01T00:00:00.000Z" },
    ];
    const object = new Blob([encryptedBytes]);
    return {
        ownerToken,
        recipientToken,
        expiredEmailToken,
        env: {
            DB: new ShareTestDatabase(users, sessions, {
                id: shareId,
                file_name: "encrypted-share.zip",
                mime_type: "application/octet-stream",
                size_bytes: encryptedBytes.length,
                object_key: "private-object-key",
                created_at: "2026-01-01T00:00:00.000Z",
                recipient_email: "recipient@xenohead.com",
            }),
            FILES: {
                async get(key) {
                    assert.equal(key, "private-object-key");
                    return { body: object.stream(), size: object.size };
                },
            },
        },
    };
}

test("verification code endpoint rejects non-XenoHead domains server-side", async () => {
    let sends = 0;
    const response = await worker.fetch(new Request("https://hub.example/api/email/code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: "person@xenohead.com.evil" }),
    }), {
        EMAIL: { async send() { sends += 1; } },
    });

    assert.equal(response.status, 400);
    assert.equal(sends, 0);
});

test("an email code cannot be issued without the configured Email binding", async () => {
    const response = await worker.fetch(new Request("https://hub.example/api/email/code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: "root@xenohead.com" }),
    }), {});

    assert.equal(response.status, 503);
    assert.match((await response.json()).error, /not configured/i);
});

test("verification codes use the configured root sender and are delivered only through the binding", async () => {
    const messages = [];
    const response = await worker.fetch(new Request("https://hub.example/api/email/code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: "Root@xenohead.com" }),
    }), {
        DB: new VerificationTestDatabase(),
        EMAIL: { async send(message) { messages.push(message); } },
    });

    assert.equal(response.status, 200);
    assert.equal(messages.length, 1);
    assert.equal(messages[0].from, "root@xenohead.com");
    assert.equal(messages[0].to, "root@xenohead.com");
    assert.match(messages[0].text, /\d{6}/);
    assert.equal((await response.json()).expiresInSeconds, 600);
});

test("encrypted file downloads are private and restricted to the verified recipient account", async () => {
    const { env, ownerToken, recipientToken, expiredEmailToken } = await makeEnvironment();
    const fileUrl = `https://hub.example/api/shares/${shareId}/download`;

    const publicResponse = await worker.fetch(new Request(`https://hub.example/api/public-share/${shareId}`), env);
    assert.equal(publicResponse.status, 401);

    const ownerResponse = await worker.fetch(new Request(fileUrl, {
        headers: { Authorization: `Bearer ${ownerToken}` },
    }), env);
    assert.equal(ownerResponse.status, 404);

    const unverifiedResponse = await worker.fetch(new Request(fileUrl, {
        headers: { Authorization: `Bearer ${expiredEmailToken}` },
    }), env);
    assert.equal(unverifiedResponse.status, 403);

    const recipientResponse = await worker.fetch(new Request(fileUrl, {
        headers: { Authorization: `Bearer ${recipientToken}` },
    }), env);
    assert.equal(recipientResponse.status, 200);
    assert.deepEqual(new Uint8Array(await recipientResponse.arrayBuffer()), encryptedBytes);
});
