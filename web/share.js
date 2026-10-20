import { createNestedEncryptedArchive, openNestedEncryptedArchive } from "/share-crypto.bundle.js";

const TOKEN_KEY = "xenoplayer-sharing-hub-token";
const shareId = location.pathname.match(/^\/s\/([0-9a-f-]{36})\/?$/i)?.[1] || null;
const message = document.getElementById("message");
const authPanel = document.getElementById("auth-panel");
const accountPanel = document.getElementById("account-panel");
const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const verifyPanel = document.getElementById("verify-panel");
const createSharePanel = document.getElementById("create-share-panel");
const ownedSharesPanel = document.getElementById("owned-shares-panel");
const recipientSharePanel = document.getElementById("recipient-share-panel");

const state = {
    token: localStorage.getItem(TOKEN_KEY),
    user: null,
};

function showMessage(text, kind = "info") {
    message.textContent = text;
    message.dataset.kind = kind;
}

function clearMessage() {
    message.textContent = "";
    delete message.dataset.kind;
}

async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
    const response = await fetch(path, { ...options, headers });
    if (!response.ok) {
        let error = "The request could not be completed.";
        try {
            const body = await response.json();
            if (typeof body.error === "string") error = body.error;
        } catch {
            error = `The request failed (${response.status}).`;
        }
        throw new Error(error);
    }
    return response;
}

async function apiJson(path, options = {}) {
    return (await api(path, options)).json();
}

function setSession(result) {
    state.token = result.token;
    state.user = result.user;
    localStorage.setItem(TOKEN_KEY, result.token);
}

function resetSession() {
    state.token = null;
    state.user = null;
    localStorage.removeItem(TOKEN_KEY);
}

function setBusy(button, busy, busyText) {
    if (busy) {
        button.dataset.originalText = button.textContent;
        button.textContent = busyText;
        button.disabled = true;
    } else {
        button.textContent = button.dataset.originalText || button.textContent;
        button.disabled = false;
    }
}

async function sendCode(email, button) {
    clearMessage();
    setBusy(button, true, "Sending...");
    try {
        await apiJson("/api/email/code", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email }),
        });
        showMessage("If the address is valid, a verification code will arrive shortly. The code expires in 10 minutes.", "success");
    } finally {
        setBusy(button, false);
    }
}

function renderShareItem(share) {
    const item = document.createElement("div");
    item.className = "share-item";
    const title = document.createElement("strong");
    title.textContent = share.file_name || share.title || "Encrypted share";
    item.appendChild(title);

    const recipient = document.createElement("p");
    recipient.className = "muted";
    recipient.textContent = `Recipient: ${share.recipient_email || "not set"} · ${formatBytes(share.size_bytes)}`;
    item.appendChild(recipient);

    const controls = document.createElement("div");
    controls.className = "row";
    const link = document.createElement("a");
    link.className = "button";
    link.href = `/s/${share.id}`;
    link.textContent = "Share link";
    controls.appendChild(link);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
        if (!window.confirm("Delete this share and its encrypted file?")) return;
        try {
            await apiJson(`/api/shares/${share.id}`, { method: "DELETE" });
            await loadOwnedShares();
            showMessage("Share deleted.", "success");
        } catch (error) {
            showMessage(error.message, "error");
        }
    });
    controls.appendChild(remove);
    item.appendChild(controls);
    return item;
}

function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) return "size unavailable";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function loadOwnedShares() {
    const { shares } = await apiJson("/api/shares");
    const container = document.getElementById("owned-shares");
    container.replaceChildren();
    ownedSharesPanel.classList.remove("hidden");
    if (!shares.length) {
        const empty = document.createElement("p");
        empty.className = "muted";
        empty.textContent = "You have not created any shares yet.";
        container.appendChild(empty);
        return;
    }
    for (const share of shares) container.appendChild(renderShareItem(share));
}

async function loadRecipientShare() {
    if (!shareId || !state.user?.emailVerified) return;
    recipientSharePanel.classList.remove("hidden");
    try {
        const share = await apiJson(`/api/shares/${shareId}`);
        const details = document.getElementById("recipient-share-info");
        details.textContent = `Encrypted file: ${share.fileName} (${formatBytes(share.sizeBytes)}). Enter both passwords supplied by the sender.`;
    } catch (error) {
        showMessage(error.message, "error");
    }
}

async function renderAccount() {
    authPanel.classList.add("hidden");
    accountPanel.classList.remove("hidden");
    const label = document.getElementById("account-label");
    label.textContent = state.user.emailVerified
        ? `Signed in as ${state.user.username} · ${state.user.email}`
        : `Signed in as ${state.user.username} · email not verified`;
    verifyPanel.classList.toggle("hidden", Boolean(state.user.emailVerified));
    createSharePanel.classList.toggle("hidden", !state.user.emailVerified || Boolean(shareId));
    ownedSharesPanel.classList.toggle("hidden", !state.user.emailVerified || Boolean(shareId));
    recipientSharePanel.classList.toggle("hidden", !shareId || !state.user.emailVerified);

    if (state.user.emailVerified) {
        await Promise.all([
            shareId ? loadRecipientShare() : loadOwnedShares(),
        ]);
    }
}

async function refreshAccount() {
    const result = await apiJson("/api/me");
    state.user = result.user;
    await renderAccount();
}

document.getElementById("show-login").addEventListener("click", () => {
    loginForm.classList.remove("hidden");
    registerForm.classList.add("hidden");
    document.getElementById("show-login").classList.remove("secondary");
    document.getElementById("show-register").classList.add("secondary");
    clearMessage();
});

document.getElementById("show-register").addEventListener("click", () => {
    loginForm.classList.add("hidden");
    registerForm.classList.remove("hidden");
    document.getElementById("show-register").classList.remove("secondary");
    document.getElementById("show-login").classList.add("secondary");
    clearMessage();
});

document.getElementById("send-register-code").addEventListener("click", async event => {
    try {
        await sendCode(document.getElementById("register-email").value, event.currentTarget);
    } catch (error) {
        showMessage(error.message, "error");
    }
});

document.getElementById("send-attach-code").addEventListener("click", async event => {
    try {
        await sendCode(document.getElementById("attach-email").value, event.currentTarget);
    } catch (error) {
        showMessage(error.message, "error");
    }
});

loginForm.addEventListener("submit", async event => {
    event.preventDefault();
    clearMessage();
    const button = loginForm.querySelector('button[type="submit"]');
    setBusy(button, true, "Signing in...");
    try {
        const result = await apiJson("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: document.getElementById("login-username").value,
                password: document.getElementById("login-password").value,
            }),
        });
        setSession(result);
        await renderAccount();
    } catch (error) {
        showMessage(error.message, "error");
    } finally {
        setBusy(button, false);
    }
});

registerForm.addEventListener("submit", async event => {
    event.preventDefault();
    clearMessage();
    const button = registerForm.querySelector('button[type="submit"]');
    setBusy(button, true, "Creating account...");
    try {
        const result = await apiJson("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: document.getElementById("register-email").value,
                verificationCode: document.getElementById("register-code").value,
                username: document.getElementById("register-username").value,
                password: document.getElementById("register-password").value,
            }),
        });
        setSession(result);
        await renderAccount();
        showMessage("Your email is verified and your account is ready.", "success");
    } catch (error) {
        showMessage(error.message, "error");
    } finally {
        setBusy(button, false);
    }
});

document.getElementById("attach-email-form").addEventListener("submit", async event => {
    event.preventDefault();
    clearMessage();
    const button = event.currentTarget.querySelector('button[type="submit"]');
    setBusy(button, true, "Verifying...");
    try {
        const result = await apiJson("/api/email/attach", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: document.getElementById("attach-email").value,
                verificationCode: document.getElementById("attach-code").value,
            }),
        });
        state.user = result.user;
        await renderAccount();
        showMessage("Your email is verified.", "success");
    } catch (error) {
        showMessage(error.message, "error");
    } finally {
        setBusy(button, false);
    }
});

document.getElementById("create-share-form").addEventListener("submit", async event => {
    event.preventDefault();
    clearMessage();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const file = document.getElementById("share-file").files[0];
    const recipientEmail = document.getElementById("recipient-email").value.trim().toLowerCase();
    if (!file) {
        showMessage("Choose a file first.", "error");
        return;
    }

    setBusy(button, true, "Encrypting and uploading...");
    document.getElementById("new-share-credentials").classList.add("hidden");
    try {
        const encrypted = await createNestedEncryptedArchive(file);
        const response = await api("/api/shares/file", {
            method: "POST",
            headers: {
                "Content-Type": "application/octet-stream",
                "X-File-Name": encodeURIComponent(`${encrypted.fileName}.outer.zip`),
                "X-Recipient-Email": recipientEmail,
            },
            body: encrypted.encryptedArchive,
        });
        const share = await response.json();
        const credentials = document.getElementById("new-share-credentials");
        credentials.replaceChildren();
        const heading = document.createElement("strong");
        heading.textContent = "Share created — copy these passwords now.";
        credentials.appendChild(heading);
        const link = document.createElement("p");
        const anchor = document.createElement("a");
        anchor.href = new URL(`/s/${share.id}`, location.origin).href;
        anchor.textContent = anchor.href;
        anchor.rel = "noreferrer";
        link.append("Recipient link: ", anchor);
        credentials.appendChild(link);
        const first = document.createElement("p");
        first.append("Inner ZIP password: ");
        const firstCode = document.createElement("code");
        firstCode.textContent = encrypted.firstPassword;
        first.appendChild(firstCode);
        credentials.appendChild(first);
        const second = document.createElement("p");
        second.append("Outer ZIP password: ");
        const secondCode = document.createElement("code");
        secondCode.textContent = encrypted.secondPassword;
        second.appendChild(secondCode);
        credentials.appendChild(second);
        const warning = document.createElement("p");
        warning.className = "muted";
        warning.textContent = "The passwords are not stored on the server and cannot be recovered. Send them to the recipient separately from the link.";
        credentials.appendChild(warning);
        credentials.classList.remove("hidden");
        await loadOwnedShares();
        showMessage("The encrypted share was uploaded. The sender and recipient passwords stay in this browser only.", "success");
    } catch (error) {
        showMessage(error.message, "error");
    } finally {
        setBusy(button, false);
    }
});

document.getElementById("download-share-form").addEventListener("submit", async event => {
    event.preventDefault();
    clearMessage();
    const button = event.currentTarget.querySelector('button[type="submit"]');
    setBusy(button, true, "Downloading and decrypting...");
    try {
        const firstPassword = document.getElementById("first-password").value;
        const secondPassword = document.getElementById("second-password").value;
        const response = await api(`/api/shares/${shareId}/download`);
        const encryptedArchive = await response.blob();
        const file = await openNestedEncryptedArchive(encryptedArchive, firstPassword, secondPassword);
        const objectUrl = URL.createObjectURL(file);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = file.name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
        showMessage("The file decrypted successfully.", "success");
    } catch (error) {
        showMessage(error.message, "error");
    } finally {
        setBusy(button, false);
    }
});

document.getElementById("logout").addEventListener("click", async () => {
    let status = "You have signed out.";
    let kind = "success";
    try {
        await apiJson("/api/logout", { method: "POST" });
    } catch (error) {
        status = `Signed out locally. The server session could not be revoked: ${error.message}`;
        kind = "error";
    } finally {
        resetSession();
        accountPanel.classList.add("hidden");
        authPanel.classList.remove("hidden");
        showMessage(status, kind);
    }
});

if (state.token) {
    refreshAccount().catch(error => {
        resetSession();
        authPanel.classList.remove("hidden");
        accountPanel.classList.add("hidden");
        showMessage(error.message, "error");
    });
} else if (shareId) {
    showMessage("Sign in with the recipient's verified @xenohead.com account to open this share.", "info");
}
