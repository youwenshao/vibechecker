import { readFileSync, writeFileSync } from "node:fs";
import { z } from "zod";
import { AnalyzeRequest, InferenceEvent } from "./src/inference.ts";
for (const [name, schema] of Object.entries({ AnalyzeRequest, InferenceEvent })) {
  const path = new URL(`./${name}.schema.json`, import.meta.url);
  const contents = JSON.stringify({ ...z.toJSONSchema(schema), title: name }, null, 2) + "\n";
  if (process.argv.includes("--check")) {
    if (readFileSync(path, "utf8") !== contents) throw Error(`Regenerate ${name}`);
  } else writeFileSync(path, contents);
}
