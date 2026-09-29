# Codex Account Switcher

A local launcher for multiple ChatGPT accounts in Codex CLI. Automatic mode keeps the native Codex terminal open and reconnects a quota-failed conversation under another connected account. Each account has its own login and state. Multiple terminal sessions can use different accounts simultaneously. No external router, API key, or Python packages are required. The local bridge forwards terminal protocol messages to the official Codex app-server; model traffic goes directly from Codex to OpenAI.

> **Experimental:** simulated failover and offline compatibility checks pass. Live quota failover has not yet been validated.

## Install

Requires macOS or Linux, Python 3.9+, and a Codex CLI supporting `--remote unix://` and the app-server protocol (transport checked against installed Codex 0.158.0). Manual mode also uses `--no-daemon`. Automatic mode depends on an experimental Codex interface, so rerun the tests after CLI upgrades.

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

## Connect accounts

```sh
codex-accounts add personal
codex-accounts add work
codex-accounts list
```

Each `add` runs the official Codex browser login. Select the correct ChatGPT account in the browser; signing into the same account twice does not give separate quotas. If browser login is inconvenient, use `add NAME --device-auth` (requires device login enabled for your account). Use `login NAME` to reconnect later.

Credentials remain local under `~/.local/share/codex-accounts/accounts/NAME/auth.json`. They are stored with private permissions, and Codex performs its own token refresh. Account names are labels you choose; they do not verify the identity you select in the browser. `status NAME` asks Codex for cached login status; it does not fetch quota or guarantee token validity.

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
codex-accounts list                      # Accounts, running sessions, cooldowns
```

When Codex reports that a turn has completed with a structured `usageLimitExceeded` or `rateLimitExceeded` error, automatic mode:

1. Marks that account unavailable for the reported exhausted quota window, or briefly cools it down when no reset time is known (five minutes for usage limits, one minute for rate limits).
2. Stops that conversation's backend so its tools and history writer have stopped.
3. Copies its saved history to another connected account and remembers the new owner.
4. Reconnects the same terminal to a fresh official Codex backend under that account.
5. Starts a continuation turn instructing Codex to inspect preserved work and avoid repeating completed side effects.

You do not need to close the terminal, find the session ID, move the history, or type another prompt. The native UI may briefly show the original quota error before the continuation starts. Other conversations have their own backends and continue independently. Shared cooldowns also guide new launches.

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

The launcher copies the complete saved legacy JSONL history to the destination account, records the new owner, and retains the original. Moving back replaces the destination's older copy after backing it up. Existing project files stay in place. The target account must already be connected.

Use the launcher's `resume` after moving, rather than a native `/resume` picker inside another running Codex session. Native pickers may still expose retained old copies. The launcher tracks only processes launched through it; it cannot detect a session opened outside it or a different session selected through native `/resume`. Close those before moving. A known running conversation blocks its own move; other resumed conversations can continue. A newly started CLI session has no registered ID yet, so moving from that account conservatively requires closing its new-session processes first.

History transfer is a local, version-sensitive mechanism, not a built-in OpenAI account-switch feature. Paginated history is rejected. Subagent sessions are separate histories and are not moved automatically. Automatic mode uses the same history transfer after a structured quota failure. It does not fetch remaining quota in advance or automatically migrate paginated/subagent histories.

## Configuration and scope

Account homes start fresh. Your existing `~/.codex` configuration, plugins, MCP authentication, and desktop history are not copied. Configure account-specific settings in `~/.local/share/codex-accounts/accounts/NAME/config.toml`; project-level settings continue to load normally. The launcher forces file-based ChatGPT credentials and the OpenAI provider. Managed authentication restrictions still apply.

This controls the CLI only. It does not change the desktop app, IDE extension, or existing ordinary `codex` processes. Avoid editing the same project files concurrently unless you intend to coordinate that work.

`CODEX_ACCOUNTS_HOME` overrides launcher storage. `CODEX_ACCOUNTS_BINARY` selects a Codex executable. Uninstall the command by removing `~/.local/bin/codex-accounts`; account data remains in the storage directory until you separately remove it.

## Validation

```sh
python3 test_launcher.py
python3 test_auto.py
python3 test_native_history.py
```

Tests cover isolated credentials/environment, concurrent account locks, duplicate-resume protection, active-session move protection, complete history preservation and round trips, unsupported-format rejection, argument forwarding, and account-name validation. The offline native check verifies that the installed Codex app server discovers the moved history and reads its user and assistant messages, without making a model request. Additional tests simulate quota failover, exhaustion of all accounts, concurrent-session routing, cooldowns, preservation of model/approval settings, isolation of subagent events, pending RPC handling, and WebSocket framing. The real native terminal was also connected through the bridge up to its authentication check. Live multi-account authentication and model requests require the user's browser sign-ins and are not exercised by the tests. Automatic failover is implemented but has not yet been validated against a live account quota failure.

Official building blocks: [authentication](https://learn.chatgpt.com/docs/auth) and [configuration/state locations](https://learn.chatgpt.com/docs/config-file/config-advanced).

## Development and license

The launcher uses only the Python standard library. Unit tests run without a Codex installation; the optional native history test requires Codex. GitHub Actions runs the unit tests on macOS and Linux.

Report bugs in [GitHub Issues](https://github.com/JoRo-Code/codex-account-switcher/issues). Include the CLI versions and error text, but never attach `auth.json`, tokens, or private conversation histories.

Released under the [MIT license](LICENSE). This is an independent project, not an official OpenAI product.
