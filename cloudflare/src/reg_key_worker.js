const SESSION_LIFETIME_MS = 30 * 24 * 60 * 60 * 1000;
const PASSWORD_ITERATIONS = 100000;

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
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Max-Age": "86400",
    };
}

function base64Url(bytes) {
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

async function sha256(value) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return base64Url(new Uint8Array(digest));
}

async function readJson(request) {
    try {
        return await request.json();
    } catch {
        throw new HttpError(400, "Request body must be valid JSON.");
    }
}

async function validateRegKey(request, env) {
    if (!env.DB) throw new HttpError(503, "Registration key validation is not configured yet.");
    const body = await readJson(request);
    const key = typeof body.key === "string" ? body.key.trim() : "";
    const keyHash = typeof body.key_hash === "string" && body.key_hash ? body.key_hash : (key ? await sha256(key) : "");
    const machineId = typeof body.machine_id === "string" ? body.machine_id : "";
    if (!keyHash) throw new HttpError(400, "A registration key is required.");

    const row = await env.DB.prepare(
        `SELECT id, label, machine_id, active FROM reg_keys WHERE key_hash = ?`
    ).bind(keyHash).first();
    if (!row || !row.active) throw new HttpError(401, "Invalid registration key.");
    if (row.machine_id && row.machine_id !== machineId) {
        throw new HttpError(403, "This registration key is bound to a different machine.");
    }
    const now = new Date().toISOString();
    if (!row.machine_id) {
        await env.DB.prepare(
            `UPDATE reg_keys SET machine_id = ?, last_used_at = ? WHERE id = ?`
        ).bind(machineId, now, row.id).run();
    } else {
        await env.DB.prepare(`UPDATE reg_keys SET last_used_at = ? WHERE id = ?`)
            .bind(now, row.id).run();
    }
    return json({ ok: true, keyId: row.id, label: row.label });
}

async function route(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders() });

    if (path === "/health" && request.method === "GET") {
        return json({ ok: true });
    }
    if (path === "/api/reg-key/validate" && request.method === "POST") return validateRegKey(request, env);

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
            console.error("Reg key API request failed:", error);
            return json({ error: "The request could not be completed." }, 500, corsHeaders());
        }
    },
};
