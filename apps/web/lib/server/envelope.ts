import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { env } from "./security";

function keyEncryptionKey() {
  const key = Buffer.from(env("ESSAY_KEK"), "base64");
  if (key.length !== 32) throw Error("Invalid essay key");
  return key;
}

function seal(bytes: Buffer, key: Buffer, context: string) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  cipher.setAAD(Buffer.from(context));
  const ciphertext = Buffer.concat([cipher.update(bytes), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), ciphertext]).toString("base64");
}
function open(encoded: string, key: Buffer, context: string) {
  const packed = Buffer.from(encoded, "base64");
  const cipher = createDecipheriv("aes-256-gcm", key, packed.subarray(0, 12));
  cipher.setAuthTag(packed.subarray(12, 28));
  cipher.setAAD(Buffer.from(context));
  return Buffer.concat([cipher.update(packed.subarray(28)), cipher.final()]);
}
export type Envelope = { v: 1; wrapped: string; ciphertext: string };
export function encryptEssay(text: string, id: string, owner: string): Envelope {
  const dataKey = randomBytes(32);
  const context = owner + "/" + id;
  return {
    v: 1,
    wrapped: seal(dataKey, keyEncryptionKey(), "key/" + context),
    ciphertext: seal(Buffer.from(text), dataKey, "essay/" + context),
  };
}
export function decryptEssay(value: Envelope, id: string, owner: string) {
  if (value.v !== 1) throw Error("Unknown envelope");
  const context = owner + "/" + id;
  return open(
    value.ciphertext,
    open(value.wrapped, keyEncryptionKey(), "key/" + context),
    "essay/" + context,
  ).toString("utf8");
}
