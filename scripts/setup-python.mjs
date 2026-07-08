import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

const [, , appDir] = process.argv;

if (!appDir) {
  console.error("Usage: node scripts/setup-python.mjs <app-dir>");
  process.exit(2);
}

const cwd = path.resolve(process.cwd(), appDir);
const venvPython =
  process.platform === "win32"
    ? path.join(cwd, ".venv", "Scripts", "python.exe")
    : path.join(cwd, ".venv", "bin", "python");
const requirements = path.join(cwd, "requirements.txt");

if (!existsSync(venvPython)) {
  const create = spawnSync("python", ["-m", "venv", ".venv"], {
    cwd,
    stdio: "inherit",
    shell: false,
  });
  if (create.status !== 0) {
    process.exit(create.status ?? 1);
  }
}

if (!existsSync(requirements)) {
  console.error(`[setup-python] Missing requirements.txt in ${appDir}`);
  process.exit(1);
}

const install = spawnSync(
  venvPython,
  ["-m", "pip", "install", "-r", "requirements.txt"],
  {
    cwd,
    stdio: "inherit",
    shell: false,
  }
);

process.exit(install.status ?? 1);
