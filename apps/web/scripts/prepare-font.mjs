import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

// Fetch each installation's own licensed copy from the foundry before self-hosting it.
const font = new URL("../public/fonts/clash-display-semibold.woff2", import.meta.url);
const digest = "e748ea11c49f39ae2375dce4fbda8dc971c5ca8b64ac8a838b5daba96f61a10a";
const matches = (bytes) => createHash("sha256").update(bytes).digest("hex") === digest;
if (!await readFile(font).then(matches, () => false)) {
  const url = "https://cdn.fontshare.com/wf/FPDAZ2S6SW4QMSRIIKNNGTPM6VIXYMKO/5HNPQ453FRLIQWV2FNOBUU3FKTDZQVSG/Z3MGHFHX6DCTLQ55LJYRJ5MDCZPMFZU6.woff2";
  const bytes = execFileSync("curl", ["--fail", "--silent", "--show-error", "--retry", "2", "--max-time", "30", url]);
  if (!matches(bytes)) throw new Error("Unexpected Clash Display font digest.");
  await mkdir(new URL("../public/fonts/", import.meta.url), { recursive: true });
  await writeFile(font, bytes);
}
