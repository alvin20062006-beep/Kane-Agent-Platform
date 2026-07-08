# Safe Stop And Data Restore

Use this guide before restoring `apps/data` or `apps/local-bridge/data` from a local test backup.

## Stop The Dev Stack

From the repo root:

```powershell
npm run stop:stack
```

On Windows, API and Bridge usually run through `uvicorn --reload`, which can expose a parent/child process pair. The stop script now performs multiple safe passes so newly exposed reload children can be stopped when they are recognized as Kane dev processes.

The stop script only stops processes that:

- listen on Kane dev ports: `3000`, `8000`, `8010`, or `8011`
- look like this repo's dev stack from their command line

Unknown processes are skipped and reported. Inspect them manually before stopping anything else. A skipped unknown process is not treated as stopped.

If the script still reports a listener after all passes, do not restore data yet. Close the dev terminal that owns the process, or inspect the reported PID and command line before taking any stronger action.

## Confirm Ports Are Down

```powershell
netstat -ano | findstr ":3000 :8000 :8010 :8011"
```

No listening rows should remain for Kane-owned API, Web, Bridge, or secondary Bridge processes.

If a row remains, re-run:

```powershell
npm run stop:stack
```

Only proceed when the relevant ports are down and HTTP probes to those ports fail. Do not restore data while any API or Bridge listener is still reachable.

## Restore Data Safely

Only restore data while API and Bridge are stopped and no Kane-owned listener remains on `8000`, `8010`, or `8011`.

Do not copy backup files into these directories while services are running:

- `apps/data`
- `apps/local-bridge/data`

Recommended restore flow:

1. Run `npm run stop:stack`.
2. Confirm ports `3000`, `8000`, `8010`, and `8011` are down.
3. Make a safety copy of the current post-test data.
4. Restore the backup into `apps/data` and/or `apps/local-bridge/data`.
5. Start the stack again.
6. Run `npm run wait:stack` and the relevant smoke checks.

Keep the safety copy until the restored stack has been verified.
