import { existsSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";

const repoRoot = process.cwd();
const runtimeDir = path.join(repoRoot, ".runtime-logs");
const manifestPath = path.join(runtimeDir, "dev-stack-manifest.json");
const npmCliPath =
  process.platform === "win32"
    ? path.join(path.dirname(process.execPath), "node_modules", "npm", "bin", "npm-cli.js")
    : null;
const npmCommand =
  process.platform === "win32" && npmCliPath && existsSync(npmCliPath)
    ? process.execPath
    : "npm";
const npmArgsPrefix =
  process.platform === "win32" && npmCliPath && existsSync(npmCliPath)
    ? [npmCliPath]
    : [];

const services = [
  {
    name: "api",
    port: 8000,
    command: process.execPath,
    args: [
      "scripts/run-python.mjs",
      "apps/api",
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8000",
    ],
  },
  {
    name: "bridge",
    port: 8010,
    command: process.execPath,
    args: [
      "scripts/run-python.mjs",
      "apps/local-bridge",
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8010",
    ],
  },
  {
    name: "web",
    port: 3000,
    command: npmCommand,
    args: [...npmArgsPrefix, "--workspace", "@kane/web", "run", "dev"],
  },
];

mkdirSync(runtimeDir, { recursive: true });

const children = [];
let shuttingDown = false;

function writeManifest() {
  writeFileSync(
    manifestPath,
    JSON.stringify(
      {
        repoRoot,
        startedAt: new Date().toISOString(),
        launcherPid: process.pid,
        services: children.map(({ service, child }) => ({
          name: service.name,
          port: service.port,
          pid: child.pid,
          command: service.command,
          args: service.args,
        })),
      },
      null,
      2
    )
  );
}

function stopChildren() {
  shuttingDown = true;
  for (const { child } of [...children].reverse()) {
    if (!child.killed) {
      child.kill();
    }
  }
}

for (const service of services) {
  const child = spawn(service.command, service.args, {
    cwd: repoRoot,
    stdio: "inherit",
    shell: false,
    env: process.env,
  });
  children.push({ service, child });
  child.on("exit", (code, signal) => {
    if (shuttingDown) {
      return;
    }
    console.error(
      `[dev:stack] ${service.name} exited unexpectedly` +
        (signal ? ` by signal ${signal}` : ` with code ${code}`)
    );
    stopChildren();
    process.exitCode = code ?? 1;
  });
}

writeManifest();
console.log(`[dev:stack] manifest: ${manifestPath}`);

process.on("SIGINT", () => {
  stopChildren();
});
process.on("SIGTERM", () => {
  stopChildren();
});
process.on("exit", () => {
  if (shuttingDown) {
    try {
      rmSync(manifestPath, { force: true });
    } catch {
      // Best-effort cleanup only.
    }
  }
});
