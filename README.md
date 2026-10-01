# Codex Account Switcher

A local launcher for multiple ChatGPT accounts in Codex CLI. Automatic mode keeps the native Codex terminal open and reconnects a quota-failed conversation under another connected account. Each account has its own login and state. Multiple terminal sessions can use different accounts simultaneously. No external router, API key, or Python packages are required. The local bridge forwards terminal protocol messages to the official Codex app-server; model traffic goes directly from Codex to OpenAI.

> **Experimental:** simulated failover and offline compatibility checks pass. Live quota failover has not yet been validated.

## Set up native Codex Desktop (macOS)

After installing, run:

```sh
codex-accounts setup
```

This opens a private setup page in your browser:

1. **Add account** opens ChatGPT sign-in. Repeat for each account; labels are optional.
2. **Connect** configures and checks the local SSH connection and background services.
3. Follow the short **Finish in Codex Desktop** card once to link the connection and add a project on it.

The page shows connected account identities, usage, progress, and local connection readiness. It never claims Desktop is linked just because the local services are ready. Codex Desktop still requires its own connection/project selection; there is no supported automatic approval API. Existing chats stay on their current connection.

Setup creates a dedicated localhost SSH key and alias and installs two user LaunchAgents. They start when you log in and restart after a crash. Re-running setup preserves accounts, histories, permissions, keys, and running services. No admin password, macOS Remote Login, external server, or Python packages are needed. Closing the page does not stop your chats. Its local web server exits after 30 minutes without page activity.

For headless use or detailed setup diagnostics, run `codex-accounts setup --terminal`.

```sh
codex-accounts add work             # Browser login for another account
codex-accounts overview --history   # Account usage and chat assignments
codex-accounts desktop status       # Check router and SSH readiness
codex-accounts desktop stop         # Stop managed services and active router work
codex-accounts desktop start        # Start services again
```

For a single install-and-setup command, use `python3 install.py --setup`. Use `setup --account LABEL` to select the initial account explicitly or `--port NUMBER` for a fixed localhost port. To change an existing setup's account or port, stop its services first, then rerun setup with the desired option. `desktop restart` loads updated router code and interrupts active router work; do it between turns. Updates and reinstalls preserve credentials and configuration. After a reboot, log in to start the services, then let Desktop reconnect.

Generated configuration, keys, logs, and settings live under `~/.local/share/codex-accounts/desktop`. Setup adds one Include line to `~/.ssh/config` and retains a backup before its first change. It does not replace existing SSH hosts or native Codex daemons. Only macOS onboarding is packaged today; Linux CLI and manual router usage remain available.

## Continue a chat you already have

```sh
codex-accounts continue
```

Choose a chat by title and project in the full-screen picker. Type to search instantly, use arrow keys to move, and press Enter to open. Tab cycles between this project, all projects, and launcher chats; Esc cancels. If the current directory has chats, the picker starts there. Compact columns show account, project, and date; the selected chat’s details appear below. Terminals without curses support fall back to a numbered picker. The picker includes launcher chats and locally saved chats in `~/.codex`, including local Desktop and ordinary CLI chats. It checks live limits, keeps the current account when available, and selects another account when the current one is blocked. Before opening the terminal it shows the account email, quota, and automatic-switching status.

```sh
codex-accounts continue billing          # Search by title or project
codex-accounts continue --list           # Browse without starting anything
codex-accounts continue billing --account codex2
```

An existing local chat is imported as a separate terminal copy. Its original stays in Desktop or the ordinary CLI; later messages do not sync between copies. After import the picker prefers the launcher copy so it does not repeatedly import the original. Stop/close the original session before importing; Codex's native writer lock may prevent import while the original remains loaded. Credentials, plugins, and account configuration are not copied. Launcher defaults and the chat's saved settings apply as described below.

This does **not** switch the account of an in-place Desktop chat. The Codex Auto SSH connection provides a separate managed backend for native Desktop. A menu-bar account picker is not implemented. Cloud-only ChatGPT chats are not imported.

If limits cannot be verified, the launcher asks you to check status or choose `--account NAME` explicitly instead of silently treating an unknown account as available. Known blocked accounts are rejected. `--source-home PATH` searches another existing Codex home; `--json` lists matches without starting or importing a chat.

## Account and conversation overview

```sh
codex-accounts overview
codex-accounts overview rence --history
codex-accounts overview --account codex2
```

Shows current connected emails and live quota, saved conversations per account, open launcher sessions, project locations, and recorded account usage. `--history` includes timestamped opens, observed turn starts, imports, and account moves. `--include-local` adds local/Desktop chats whose account history is unknown; `--json` provides structured output, and `--limit N` changes the default 20-chat limit. It is also available in the no-argument menu.

Starting in v0.7.0, activity is stored in the private `activity.sqlite` database and survives process exit and updates. Restart older launcher sessions to enable recording. A stored history file indicates its current location, not which account executed all its old turns. Imported history is not retroactively attributed to the destination account. A move records an assignment; an observed turn start records execution under that account. Exact per-chat quota consumption and activity outside the managed router are unavailable. Emails shown identify accounts currently connected to each label; the audit tracks labels. New manual CLI sessions do not expose a reliable chat ID, so their launches are retained separately in JSON rather than guessed.

Since v0.7.1, temporary helper threads cannot replace the main chat’s tracking or reconnect settings. Unmatched sessions from older launchers appear separately as unverified tracking. Exit and reopen those sessions with `codex-accounts continue` when convenient; updating does not replace code already loaded in running processes.

## Install

Requires macOS or Linux, Python 3.9+, and a Codex CLI supporting `--remote unix://` and the app-server protocol (transport and paginated migration checked against installed Codex 0.159.2). Manual mode also uses `--no-daemon`. Automatic mode depends on an experimental Codex interface, so rerun the tests after CLI upgrades.

```sh
git clone https://github.com/JoRo-Code/codex-account-switcher.git
cd codex-account-switcher
python3 install.py
```

Or download and extract the source archive from [Releases](https://github.com/JoRo-Code/codex-account-switcher/releases), then run `python3 install.py` inside the extracted directory. GitHub downloads do not require a GitHub account.

If the installer reports that `~/.local/bin` is missing from your PATH, add this to your shell configuration and open a new terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

The installer copies the executable to `~/.local/bin/codex-accounts`. It does not modify shell settings, your existing Codex login, or your default Codex configuration.

## Update without reinstalling

```sh
codex-accounts update                  # Download and replace the installed CLI
codex-accounts update --check          # Check without installing
codex-accounts update policy           # Show the update policy
codex-accounts update policy auto      # Automatic updates (default)
codex-accounts update policy notify    # Report availability without installing
codex-accounts update policy off       # Only update when explicitly requested
codex-accounts update --rollback       # Restore the previous executable
```

Installed copies check GitHub for stable releases when launched, at most once an hour. Available updates are verified, installed, and used for the requested command. There is no update daemon; an already-open conversation is never restarted. Offline update failures do not prevent normal CLI use. `--help` and `--version` do not check for updates. Automatic updates are limited to copies registered by `install.py`, not source checkouts.

Updates download the standalone executable and SHA-256 checksum from this repository's GitHub Releases. The updater verifies the checksum, GitHub's artifact digest when supplied, the embedded version, and a startup check before atomically replacing the executable. This trusts this GitHub repository and HTTPS; checksums are integrity checks, not independent release signatures. A backup supports rollback. Rollback sets the policy to `notify` to avoid immediately reinstalling the same update. Updates do not downgrade; `--prerelease` explicitly includes preview releases for a manual check or update.

Connected accounts, cached credentials, history, and routing settings remain in the data directory. `updates.json` stores the check time and update policy. Conversations already running keep their loaded code until they exit; subsequent launches use the new version.

**One-time bootstrap for versions before 0.4.0:** those versions do not contain an updater. Run `git pull` and `python3 install.py` once. After that, use `codex-accounts update`; no new clone or reinstall is needed. A source checkout is updated with Git rather than overwritten by the executable updater.

## Connect accounts

```sh
codex-accounts add personal
codex-accounts add work
codex-accounts list
```

Each `add` runs the official Codex browser login. Select the correct ChatGPT account in the browser; signing into the same account twice does not give separate quotas. If browser login is inconvenient, use `add NAME --device-auth` (requires device login enabled for your account). Use `login NAME` to reconnect later.

`list` asks each account’s Codex backend for its cached email and plan, so you can identify which ChatGPT login each label represents. It does not refresh tokens or verify remaining quota. If an identity cannot be read, that row says `identity unavailable`; other accounts still appear.

Credentials remain local under `~/.local/share/codex-accounts/accounts/NAME/auth.json`. They are stored with private permissions, and Codex performs its own token refresh. Account names are labels you choose; they do not verify the identity you select in the browser. `status NAME` fetches live usage limits and shows launcher sessions for that account; `status` without a name shows all accounts.

## Account dashboard

```sh
codex-accounts status               # Live snapshot of all accounts
codex-accounts status --watch       # Keep open; refresh every 30 seconds
codex-accounts status codex1        # One account
codex-accounts status --json        # Structured snapshot for your own tools
```

Each account shows:

- Its label, signed-in email, and cached plan.
- Quota windows returned by Codex, including remaining/used percentages and reset times in your local timezone.
- Backend-reported usage blocks, spending limits, workspace credits, and earned resets when available.
- Launcher sessions: project path, conversation ID, title, model, process ID, and time open.
- Automatic-session activity: starting, working, waiting for input, idle, failed, or switching accounts.
- Account routing cooldowns.

`--watch --interval 60` changes the refresh interval (minimum 10 seconds). Press Ctrl-C to close the dashboard; running conversations keep going. If a lookup fails, that account shows limits unavailable while the others remain visible. Unknown limits are never reported as zero usage. Displayed reset times do not establish that backend access has recovered. The dashboard does not redeem resets, buy credits, send notifications, or change routing state.

Limits come from OpenAI's account endpoint and can reflect usage outside the launcher. Session locations cover only launcher processes on this computer; desktop sessions and ordinary `codex` processes are not inventoried. Manual mode reports the CLI as open because it cannot observe turn activity. Restart older launcher processes to get the new project/title/activity tracking. Workspace credit balances can be shared across accounts and should not be summed as independent allowances.

## Daily use: automatic mode

```sh
cd /path/to/project
codex-accounts auto
```

Open as many terminals as you need and run the same command. The launcher chooses a connected account using active-session counts and least-recent selection, skipping accounts in cooldown. You keep the normal Codex terminal UI, approvals, and tool interactions.

```sh
codex-accounts auto --account personal    # Choose the starting account
codex-accounts auto --resume SESSION_ID  # Continue an existing saved conversation
codex-accounts auto --cd /path/to/project --prompt "Fix the login page"
codex-accounts sessions
codex-accounts list                      # Labels, emails, plans, running sessions, cooldowns
```

When Codex reports that a turn has completed with a structured `usageLimitExceeded` or `rateLimitExceeded` error, automatic mode:

1. Marks that account unavailable for the reported exhausted quota window, or briefly cools it down when no reset time is known (five minutes for usage limits, one minute for rate limits).
2. Stops that conversation's backend so its tools and history writer have stopped.
3. Copies its saved history to another connected account and remembers the new owner.
4. Reconnects the same terminal to a fresh official Codex backend under that account.
5. Starts a continuation turn instructing Codex to inspect preserved work and avoid repeating completed side effects.

You do not need to close the terminal, find the session ID, move the history, or type another prompt. The native UI may briefly show the original quota error before the continuation starts. Other conversations have their own backends and continue independently. Shared cooldowns also guide new launches.

Exiting the terminal also stops this launcher's backend. Codex may print a generic remote-mode message saying work continues and suggesting a temporary socket reconnect command; that does not apply to this launcher. Use the `codex-accounts auto --resume SESSION_ID` command printed afterward to reopen a saved chat. Starting `auto --account NAME` again creates a new chat.

Only structured quota errors trigger this behavior, after Codex's own retries have ended. Generic errors, authentication failures, and subagent notifications do not trigger account switching. The model and permission choices are carried forward. This is a new continuation turn with the existing history, not resumption of an interrupted network response. The launcher does not rerun tool commands itself; model continuation cannot guarantee exactly-once external side effects.

Each account is tried at most once per failed-turn chain. If every connected account is exhausted, the terminal stays open with the failure and saved history; it does not spin or wait indefinitely. You can submit a new turn later, resume later, or connect another account. A cooldown expiring only makes an account eligible for another attempt; it does not establish that quota recovered.

## Manual mode

Run `codex-accounts` for an interactive menu, or explicitly pin a terminal to an account:

```sh
codex-accounts run personal
codex-accounts run work
codex-accounts resume SESSION_ID
```

`run` without an account offers a picker. Manual `resume` uses the current owner and returns to the saved project directory. Session IDs accept unambiguous prefixes. `--cd` and `--model` can override saved values. Use `auto --resume SESSION_ID` to enable failover while resuming.

Multiple sessions on the same account share that account's quota. Manual mode uses `--no-daemon`; automatic mode connects to a dedicated private Unix socket. Both avoid the shared default server. Ambient API keys and known alternate authentication variables are removed from child processes, and the launcher requires ChatGPT authentication with the OpenAI provider.

## Optional manual move

1. Exit that CLI conversation normally. Moving does not interrupt or retry a running turn.
2. Find its ID with `codex-accounts sessions`.
3. Move and resume:

```sh
codex-accounts switch SESSION_ID --to work
codex-accounts resume SESSION_ID
```

The launcher copies the complete saved legacy or paginated JSONL history to the destination account, records the new owner, and retains the original. Moving back replaces the destination's older copy after backing it up. Existing project files stay in place. The target account must already be connected.

Use the launcher's `resume` after moving, rather than a native `/resume` picker inside another running Codex session. Native pickers may still expose retained old copies. The launcher tracks only processes launched through it; it cannot detect a session opened outside it or a different session selected through native `/resume`. Close those before moving. A known running conversation blocks its own move; other resumed conversations can continue. A newly started CLI session has no registered ID yet, so moving from that account conservatively requires closing its new-session processes first.

History transfer is a local, version-sensitive mechanism, not a built-in OpenAI account-switch feature. Paginated history stays paginated: the destination’s derived history index is cleared only for this chat, and Codex rebuilds it from the copied log on resume. Native Codex writer locks prevent copying active histories. Unknown database versions or schemas fail before replacing history. Subagent sessions are separate histories and are not moved automatically. Automatic mode uses the same history transfer after a structured quota failure. It does not fetch remaining quota in advance or automatically migrate subagent histories.

## Configuration and scope

Account homes start fresh. Your existing `~/.codex` configuration, plugins, MCP authentication, and desktop history are not copied. Configure account-specific settings in `~/.local/share/codex-accounts/accounts/NAME/config.toml`; project-level settings continue to load normally. The launcher forces file-based ChatGPT credentials and the OpenAI provider. Managed authentication restrictions still apply.

### Shared permissions and model defaults

Set these once for every existing and future launcher account:

```sh
codex-accounts permissions yolo
codex-accounts defaults --model gpt-6-astra --effort medium
codex-accounts permissions                 # Show permission mode
codex-accounts defaults                    # Show model defaults
```

YOLO sets `approval_policy="never"` and `sandbox_mode="danger-full-access"`: unrestricted filesystem and network access without command approval prompts. It is opt-in. These shared settings apply to manual starts, resumes, the automatic terminal, and replacement backends after account switching. Explicit `--model` and in-chat choices override model defaults; automatic continuation preserves the current chat’s model and permission choices. Organization requirements still apply, and this does not grant OS permissions or authenticate plugins.

Restart existing launcher sessions to apply new defaults. Settings are stored separately from the executable in `permissions.json` and `defaults.json` under the launcher data root, survive updates/reinstallation, and apply to accounts added later. They are independent of `~/.codex/config.toml`; changes there are not automatically synchronized. Use `codex-accounts permissions default` and `codex-accounts defaults --clear` to return to account-specific configuration.

Run launcher commands in your shell, not as a prompt inside another Codex chat. An outer Codex session has its own permissions and may ask for approval before it can launch the command.

This controls the CLI only. It does not change the desktop app, IDE extension, or existing ordinary `codex` processes. Avoid editing the same project files concurrently unless you intend to coordinate that work.

`CODEX_ACCOUNTS_HOME` overrides launcher storage. `CODEX_ACCOUNTS_BINARY` selects a Codex executable. Uninstall the command by removing `~/.local/bin/codex-accounts`; account data remains in the storage directory until you separately remove it.

## Validation

```sh
python3 test_launcher.py
python3 test_auto.py
python3 test_status.py
python3 test_update.py
python3 test_native_history.py
python3 test_native_paginated_history.py
python3 test_continue.py
python3 test_overview.py
```

Tests cover isolated credentials/environment, concurrent account locks, duplicate-resume protection, active-session move protection, complete history preservation and round trips, unsupported-format rejection, argument forwarding, and account-name validation. The paginated native check verifies A → B → A migration with a stale destination index, two preserved turns, pagination, and native writer locks. The legacy offline native check verifies that the installed Codex app server discovers the moved history and reads its user and assistant messages, without making a model request. Additional tests simulate quota failover, exhaustion of all accounts, concurrent-session routing, cooldowns, preservation of model/approval settings, isolation of subagent events, pending RPC handling, and WebSocket framing. The real native terminal was also connected through the bridge up to its authentication check. Live identity and quota retrieval have been checked with connected accounts. Model requests and real quota failover are not exercised by the tests. Automatic failover is implemented but has not yet been validated against a live account quota failure.

Official building blocks: [authentication](https://learn.chatgpt.com/docs/auth) and [configuration/state locations](https://learn.chatgpt.com/docs/config-file/config-advanced).

## Development and license

The launcher uses only the Python standard library. Unit tests run without a Codex installation; the optional native history tests require Codex. GitHub Actions runs the unit tests on macOS and Linux.

Report bugs in [GitHub Issues](https://github.com/JoRo-Code/codex-account-switcher/issues). Include the CLI versions and error text, but never attach `auth.json`, tokens, or private conversation histories.

Released under the [MIT license](LICENSE). This is an independent project, not an official OpenAI product.

### Publishing a new version

Update `VERSION`, commit the changes, run the tests, and push the matching version tag. Then publish with:

```sh
python3 scripts/publish_release.py --notes-file /path/to/release-notes.md
```

The publisher uploads a standalone CLI, its checksum, and a source archive to a draft release, then publishes it only after all assets are present. Use `--prerelease` for preview releases; automatic updaters ignore previews. Keep CLI/data compatibility so rollback remains possible. The GitHub CLI must be authenticated with permission to publish releases.

## Experimental native Desktop / multi-session router

Version 0.8 adds a persistent local protocol router. Each loaded root chat owns a separate Codex app-server process, account, writer lock, and request queue. A quota failure migrates only that chat's saved history, then resumes its unfinished request on an eligible account. Other chat backends keep running. Disconnecting a client leaves its chats running until the router is stopped. This uses more memory than a single shared backend.

Start the router in a private, short-path directory:

```sh
codex-accounts serve --socket /tmp/codex-accounts-$UID/router.sock
```

Optionally add `--account codex2` to prefer that account for new chats. Resume requests retain their current account until a structured quota failure triggers rotation. Eligibility uses cached login presence and shared quota cooldowns; it is not a guarantee of current quota or valid credentials. When all alternatives are exhausted, the chat pauses with an error instead of retrying endlessly. After quota resets, retry the chat. Models and permissions use launcher defaults plus saved/client-selected settings.

Connect an independent protocol client using the native CLI:

```sh
codex app-server proxy --sock /tmp/codex-accounts-$UID/router.sock
```

Native terminal clients can connect with `codex --remote unix:///tmp/codex-accounts-$UID/router.sock`. The socket accepts both native newline-JSON proxy traffic and WebSockets, and is accessible only to your OS user. Do not expose it over a public network.

For Desktop, the SSH host's Codex entry point must forward its app-server/proxy requests to this socket. Merely adding an ordinary SSH host does **not** enable rotation. The macOS `setup` command installs this adapter and its background services; Desktop still requires a connection/project selection. Existing Desktop connections need reconnecting to use a changed adapter; do so between turns. Do not replace a live native daemon or its socket. Use `codex-accounts overview --history` to see account assignments and moves.

The native account indicator describes the router's primary control account, not every chat's execution account or combined quota. Manage authentication with `codex-accounts add/login`; authentication changes from connected protocol clients are rejected. Chat history lists combine connected accounts and deduplicate moved histories. Pending approval request IDs are isolated between backends and replayed after reconnect. Settings/plugins that are not thread-scoped still belong to the primary account's backend; full Desktop plugin/browser/automation parity has not been verified.

Validation includes native proxy connections, two chats, client reconnect, combined history, and an injected quota failure that migrates history through real Codex backends while another chat remains accessible. The injection sends no model request. Actual quota exhaustion and seamless native Desktop UI recovery after rotation still require a live test. Automatic continuation is a new turn and does not guarantee exactly-once tool side effects.

Stopping `serve` stops its managed backends and tools. Saved histories and account assignments remain available for a later start. Running `serve` directly does not install a launch-at-login service; use `setup` for managed startup on macOS. Run the optional compatibility test after upgrading Codex:

```sh
python3 test_native_router.py
```
