import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";

const [, , appDir, ...pythonArgs] = process.argv;

if (!appDir || pythonArgs.length === 0) {
  console.error("Usage: node scripts/run-python.mjs <app-dir> <python args...>");
  process.exit(2);
}

const cwd = path.resolve(process.cwd(), appDir);
const venvPython =
  process.platform === "win32"
    ? path.join(cwd, ".venv", "Scripts", "python.exe")
    : path.join(cwd, ".venv", "bin", "python");
const python = existsSync(venvPython) ? venvPython : "python";
const setupScriptByDir = {
  "apps/api": "setup:api",
  "apps/local-bridge": "setup:bridge",
};
const normalizedAppDir = appDir.replaceAll("\\", "/");
const setupScript = setupScriptByDir[normalizedAppDir] ?? `setup:${path.basename(appDir)}`;

if (!existsSync(venvPython)) {
  console.warn(
    `[run-python] ${appDir}/.venv not found; falling back to system Python. ` +
      `Run "npm run ${setupScript}" for an isolated environment.`
  );
}

const child = spawn(python, pythonArgs, {
  cwd,
  stdio: "inherit",
  shell: false,
});

child.on("exit", (code, signal) => {
  if (signal) {
    console.error(`[run-python] stopped by signal ${signal}`);
    process.exit(1);
  }
  process.exit(code ?? 1);
});
