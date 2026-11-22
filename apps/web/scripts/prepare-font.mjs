import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

// Fetch each installation's own licensed copy from the foundry before self-hosting it.
const fonts = [
  {
    file: "clash-display-semibold.woff2",
    digest: "e748ea11c49f39ae2375dce4fbda8dc971c5ca8b64ac8a838b5daba96f61a10a",
    url: "https://cdn.fontshare.com/wf/FPDAZ2S6SW4QMSRIIKNNGTPM6VIXYMKO/5HNPQ453FRLIQWV2FNOBUU3FKTDZQVSG/Z3MGHFHX6DCTLQ55LJYRJ5MDCZPMFZU6.woff2",
  },
  {
    file: "panchang-semibold.woff2",
    digest: "47b8dc8711f9ad0a3efe413dddf4fdc956bf7da783bdb4b0fdb536c40fea9ece",
    url: "https://cdn.fontshare.com/wf/VFK4WJ2ASLGVJIGPTOYHEAIT3DW643RW/6EOQ664MDO34ATBE2MF2I4O67G7EU7JM/5CZKGRVOJ2H4RNXBVGN3P4FD5ZWCYM54.woff2",
  },
  {
    file: "panchang-extrabold.woff2",
    digest: "7fb9916f18f4bf516a6a1e0d49230063b06886bf3e5f2e4244a9acd01d1e6881",
    url: "https://cdn.fontshare.com/wf/BBOB5VAX4DF6FK5U27HLFW2VBLISCNKC/MIAKLBXTHJJTUKTXLTZZ76B3RNR3JBSO/BYZ4XKAY33UX3C5BSZV4BEIU2HQF4PD7.woff2",
  },
];
const directory = new URL("../public/fonts/", import.meta.url);
await mkdir(directory, { recursive: true });
for (const { file, digest, url } of fonts) {
  const target = new URL(file, directory);
  const matches = (bytes) => createHash("sha256").update(bytes).digest("hex") === digest;
  if (await readFile(target).then(matches, () => false)) continue;
  const bytes = execFileSync("curl", ["--fail", "--silent", "--show-error", "--retry", "2", "--max-time", "30", url]);
  if (!matches(bytes)) throw new Error(`Unexpected digest for ${file}.`);
  await writeFile(target, bytes);
}
