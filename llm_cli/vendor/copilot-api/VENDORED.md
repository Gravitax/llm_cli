# Vendored copy

Forked from [`ericc-ch/copilot-api`](https://github.com/ericc-ch/copilot-api)
at v0.7.0 (upstream commit `0ea08fe`), then patched. It is vendored rather than
installed from npm because the registry build cannot serve an enterprise tenant
and exposes the Copilot token.

`LOCAL_CHANGES.patch` holds the local commits with their messages and full
diffs — the fork no longer carries git metadata, so this is the record of what
diverges from upstream. Compare against a fresh clone of upstream v0.7.0.

## Local changes

- GitHub Enterprise data residency: the three Copilot hosts are derived from
  the tenant root instead of being hardcoded to github.com.
- The server binds to loopback by default (`--hostname` to override). It
  authenticates no caller, and `/token` answers with the live Copilot bearer.
- CORS is scoped to `/usage` instead of the whole server, so a web page cannot
  read `/token` from loopback.
- The Copilot token refresh no longer rethrows: the rejection was unhandled in
  an async `setInterval` callback and terminated the process on any transient
  network failure.
- Removed from `package.json`: `prepare` (ran `simple-git-hooks`, which needs a
  `.git` this tree no longer has), `prepack` (ran `bun run build`, which would
  make bun a prerequisite of every install) and `release` (published to the
  public npm registry under the upstream name). The git-hook and lint-staged
  configuration went with them.
- Dropped from the tree: upstream CI, Docker packaging, the GitHub Pages usage
  viewer and `AGENTS.md` — none of it is used, and this layer generates files
  named `AGENTS.md` of its own.

## dist/ is committed on purpose

`dist/main.js` is the bundle npm actually installs (`files: ["dist"]`).
Committing it means deploying needs node and npm but no build toolchain — the
devDependencies alone weigh a few hundred megabytes.

**After changing anything under `src/`, rebuild and commit the bundle:**

```sh
npm install          # once, for the build toolchain
npm run build        # regenerates dist/main.js
```

`llm_cli/services/vendored.py` deploys this tree to `~/.llm_cli/copilot-api`
and compares bundle timestamps to decide whether to refresh it;
`copilot_proxy.py` then runs `npm install -g` from there. A source change that
is not rebuilt will therefore never reach the running proxy.
