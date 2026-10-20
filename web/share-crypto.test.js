import assert from "node:assert/strict";
import test from "node:test";
import { createNestedEncryptedArchive, openNestedEncryptedArchive } from "./share-crypto.js";

test("creates two separately password-protected ZIP layers and restores the file", async () => {
    const content = "XenoPlayer nested archive round-trip test.";
    const source = new File([content], "round-trip.txt", { type: "text/plain" });
    const encrypted = await createNestedEncryptedArchive(source);

    assert.equal(encrypted.firstPassword.length, 20);
    assert.equal(encrypted.secondPassword.length, 20);
    assert.notEqual(encrypted.firstPassword, encrypted.secondPassword);

    const restored = await openNestedEncryptedArchive(
        encrypted.encryptedArchive,
        encrypted.firstPassword,
        encrypted.secondPassword,
    );
    assert.equal(restored.name, source.name);
    assert.equal(await restored.text(), content);
});

test("rejects incorrect passwords for either ZIP layer", async () => {
    const source = new File(["protected payload"], "protected.txt");
    const encrypted = await createNestedEncryptedArchive(source);

    await assert.rejects(
        openNestedEncryptedArchive(encrypted.encryptedArchive, encrypted.firstPassword, "wrong-password"),
    );
    await assert.rejects(
        openNestedEncryptedArchive(encrypted.encryptedArchive, "wrong-password", encrypted.secondPassword),
    );
});
