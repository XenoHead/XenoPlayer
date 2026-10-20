import { BlobReader, BlobWriter, ZipReader, ZipWriter } from "@zip.js/zip.js";

const PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
const MAX_ARCHIVE_SOURCE_BYTES = 90 * 1024 * 1024;

function generatePassword(length = 20) {
    const password = [];
    const limit = 256 - (256 % PASSWORD_ALPHABET.length);
    while (password.length < length) {
        const values = crypto.getRandomValues(new Uint8Array(length - password.length + 8));
        for (const value of values) {
            if (value < limit) password.push(PASSWORD_ALPHABET[value % PASSWORD_ALPHABET.length]);
            if (password.length === length) break;
        }
    }
    return password.join("");
}

function safeName(value) {
    const name = value.replace(/[\\/<>:"|?*\u0000-\u001f]/g, "_").trim();
    return (name || "shared-file").slice(0, 200);
}

async function closeReader(reader) {
    await reader.close();
}

export async function createNestedEncryptedArchive(file) {
    if (!(file instanceof Blob) || file.size === 0) {
        throw new Error("Choose a non-empty file to share.");
    }
    if (file.size > MAX_ARCHIVE_SOURCE_BYTES) {
        throw new Error("Files must be 90 MB or smaller before encryption.");
    }

    const firstPassword = generatePassword();
    const secondPassword = generatePassword();
    const fileName = safeName(file.name || "shared-file");
    const innerWriter = new ZipWriter(new BlobWriter("application/zip"), { useWebWorkers: false });
    await innerWriter.add(fileName, new BlobReader(file), {
        password: firstPassword,
        encryptionStrength: 3,
    });
    const innerArchive = await innerWriter.close();

    const outerWriter = new ZipWriter(new BlobWriter("application/zip"), { useWebWorkers: false });
    await outerWriter.add(`${fileName}.inner.zip`, new BlobReader(innerArchive), {
        password: secondPassword,
        encryptionStrength: 3,
    });
    const encryptedArchive = await outerWriter.close();
    return { encryptedArchive, firstPassword, secondPassword, fileName };
}

export async function openNestedEncryptedArchive(encryptedArchive, firstPassword, secondPassword) {
    const outerReader = new ZipReader(new BlobReader(encryptedArchive), {
        password: secondPassword,
        useWebWorkers: false,
    });
    let innerArchive;
    try {
        const entries = await outerReader.getEntries();
        if (entries.length !== 1 || entries[0].directory) {
            throw new Error("The encrypted share has an invalid outer archive.");
        }
        innerArchive = await entries[0].getData(new BlobWriter("application/zip"), {
            password: secondPassword,
        });
    } finally {
        await closeReader(outerReader);
    }

    const innerReader = new ZipReader(new BlobReader(innerArchive), {
        password: firstPassword,
        useWebWorkers: false,
    });
    try {
        const entries = await innerReader.getEntries();
        if (entries.length !== 1 || entries[0].directory) {
            throw new Error("The encrypted share has an invalid inner archive.");
        }
        const fileData = await entries[0].getData(new BlobWriter());
        return new File([fileData], safeName(entries[0].filename), {
            type: "application/octet-stream",
        });
    } finally {
        await closeReader(innerReader);
    }
}
