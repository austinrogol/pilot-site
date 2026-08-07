#!/usr/bin/env node
import { runAdaptiveRehearsal } from "./rehearsal.mjs";
import { runRedTeamHarness } from "./governor.mjs";
import { systemManifest } from "./status.mjs";

const command = process.argv[2] ?? "status";
let output;
if (command === "rehearsal") output = runAdaptiveRehearsal();
else if (command === "red-team") output = runRedTeamHarness();
else if (command === "status") output = systemManifest();
else {
  console.error("Usage: node runtime/cli.mjs [status|rehearsal|red-team]");
  process.exitCode = 2;
  output = { error: "unknown command" };
}
console.log(JSON.stringify(output, null, 2));
