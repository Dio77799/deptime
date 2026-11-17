<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/cschmertz/deptime/main/docs/assets/deptime-wordmark-dark.svg">
    <img alt="DepTime" src="https://raw.githubusercontent.com/cschmertz/deptime/main/docs/assets/deptime-wordmark-light.svg" width="340">
  </picture>
</h1>

<p align="center"><b>An API time machine for Python libraries, built for coding agents.</b></p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/deptime)](https://pypi.org/project/deptime/)
[![Python](https://img.shields.io/pypi/pyversions/deptime)](https://pypi.org/project/deptime/)
[![CI](https://github.com/cschmertz/deptime/actions/workflows/ci.yml/badge.svg)](https://github.com/cschmertz/deptime/actions/workflows/ci.yml)
[![Index build](https://github.com/cschmertz/deptime/actions/workflows/build-index.yml/badge.svg)](https://github.com/cschmertz/deptime/actions/workflows/build-index.yml)
[![License: MIT](https://img.shields.io/github/license/cschmertz/deptime)](https://github.com/cschmertz/deptime/blob/main/LICENSE)
[![Glama](https://glama.ai/mcp/servers/cschmertz/deptime/badges/score.svg)](https://glama.ai/mcp/servers/cschmertz/deptime)

</div>

Python libraries rename and remove things between releases. Code that worked last year, or code an AI model learned from, then fails with an `ImportError`, an `AttributeError` or "unexpected keyword argument". DepTime tells a coding agent **what changed, in which release, and what to use instead**, in one call. It also checks a dependency update against your code and names **each line the new version breaks**: on a pull request, from a terminal, or in one call.

<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/cschmertz/deptime/main/docs/assets/demo-dark.svg">
  <img alt="A terminal. The error is: TypeError: Client.__init__() got an unexpected keyword argument 'proxies'. The command deptime explain --installed httpx==0.28.1 answers that httpx.Client.__init__(proxies) was removed: the last release with it is 0.27.2, the first without it 0.28.0, and it was deprecated in 0.26.0. Use proxy or mounts instead, or pin httpx<=0.27.2." src="https://raw.githubusercontent.com/cschmertz/deptime/main/docs/assets/demo-light.svg" width="760">
</picture>
</p>

- **Computed, not remembered.** Each answer comes from comparing the library's own source across its releases, not from docs or a model's memory, and it quotes the evidence it found.
- **Local and free.** Open source (MIT). Your code and errors never leave your machine.
- **Says when it doesn't know.** For a package it doesn't cover, or a name it can't follow, the answer is "not covered" or `unknown`, never a guess.

> **Status:** 1.0. Tool names, parameters, result fields and CLI options only grow from here: [what 1.x promises](https://github.com/cschmertz/deptime/blob/main/CHANGELOG.md#versioning). The index rebuilds itself twice a day, and fixes follow [reported wrong answers](https://github.com/cschmertz/deptime/issues/new/choose). Known gaps are listed in [BACKLOG.md](https://github.com/cschmertz/deptime/blob/main/BACKLOG.md).

## Check a dependency update

On a pull request from Dependabot, Renovate or a person, the GitHub Action finds the lines of your Python code the new versions break, annotates each one, and fails the check only on a confirmed break ([docs](https://github.com/cschmertz/deptime/blob/main/docs/github-action.md)):

```yaml
# .github/workflows/upgrade-check.yml
on:
  pull_request:
    paths: ["**/uv.lock", "**/poetry.lock", "pyproject.toml", "**/requirements*.txt", "**/requirements/**"]
permissions:
  contents: read
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7 # pin to a commit in your own workflows
      - uses: cschmertz/deptime@v1.0.0
```

From a terminal, `uvx deptime check-upgrade` compares the pinned versions at `HEAD` with your working tree, or `--package httpx --to 0.28.1` checks one update. An agent can call the `check_upgrade` tool with the code instead, and the Claude Code plugin's `/deptime:fix-upgrade` runs the check and has Claude fix the lines it reports as broken and check the ones it can't tell about. A break is a use the index shows failing at the new version and not at the old one; the report ends with a block a coding agent can act on.

**On 264 real Dependabot and Renovate update pull requests** (247 projects, scored once before any fix, [results](https://github.com/cschmertz/deptime/blob/main/bench/upgrade-check/prs/results-2026-11-16.md)), the check failed all 13 whose update breaks the project's code, found 46 of the 48 breaking uses, and flagged 1 of 3,291 uses that still work. 2 of the 264 failed with no real break.

**An agent fixing the breaks** (Claude Code on Sonnet 5.5, 25 real broken updates, [results](https://github.com/cschmertz/deptime/blob/main/bench/agent-fix/results-2026-11-16.md)): alone it left the code working in 80% of sessions; with `/deptime:fix-upgrade` in 64%, in a third of the turns; with the plugin installed and not named, 80%. On 66 new broken updates ([results](https://github.com/cschmertz/deptime/blob/main/bench/agent-fix/qa26/results-2026-11-16.md)), the reworked command: 72.7% against 69.7% alone, in about half the turns. After fixing what lost it, on 60 broken updates neither had seen ([results](https://github.com/cschmertz/deptime/blob/main/bench/agent-fix/qa27/results-2026-11-17.md)): 86.7% against 76.7% alone, with fewer new breaks, in about half the turns.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
# Claude Code. Cursor, Codex, VS Code and Claude Desktop take the same
# command (uvx deptime mcp) in their MCP config.
claude mcp add deptime -- uvx deptime mcp
```

On first launch DepTime downloads its prebuilt index (one file from this repo's GitHub Releases) in the background, then checks for a newer one at most once a day. Set `DEPTIME_OFFLINE=1` to never touch the network. Each index carries a signed record of the CI run that built it; `deptime index pull --verify` checks it ([SECURITY.md](https://github.com/cschmertz/deptime/blob/main/SECURITY.md#verifying-the-index)).

Claude Code users can also install the plugin in [`integrations/claude-code`](https://github.com/cschmertz/deptime/tree/main/integrations/claude-code) with `/plugin marketplace add cschmertz/deptime`, then `/plugin install deptime@deptime`. It adds a skill, the `/deptime:fix-upgrade` command, and a local hook that suggests DepTime when a Python version-change error appears in a command's output.

**First launch timing out?** `uvx` installs DepTime the first time a client starts it. On macOS with an x86_64 `uv` (an Intel Mac, or Intel Homebrew on Apple silicon), one dependency, `cryptography`, has no prebuilt wheel and is compiled: about 3 minutes on GitHub's Intel macOS runner, longer than a client waits for a server to start. Run `uvx deptime --help` once beforehand.

### Client compatibility

Checked 2026-11-05 with `deptime` 0.1.4 ([details](https://github.com/cschmertz/deptime/tree/main/bench/s5)):

| Client | Result |
|---|---|
| Claude Code 2.1.318 | ✅ |
| Codex CLI 0.166.0 | ✅ |
| MCP Python SDK clients 1.0–1.30 and TypeScript SDK clients 1.0–1.32 (protocols 2024-11-05 to 2025-11-25), over stdio and against `deptime serve` | ✅ |
| Cursor, VS Code, Claude Desktop | not checked yet; they take the same `uvx deptime mcp` command |

First launch, from nothing to the right answer (2026-11-17, 0.2.3, [details](https://github.com/cschmertz/deptime/tree/main/bench/s7)): 8 s on Linux, 10 s on Apple-silicon macOS, 20 s on Windows. Runs on Python 3.12 to 3.15.

## What an answer looks like

An agent that hits this error:

```text
TypeError: Client.__init__() got an unexpected keyword argument 'proxies'
```

passes it to `explain_error` and gets:

```json
{
  "symbol": "httpx.Client.__init__(proxies)",
  "issue": "param_removed",
  "installed_version": "0.28.1",
  "last_version_with": "0.27.2",
  "first_version_without": "0.28.0",
  "deprecated_in": "0.26.0",
  "replacements": [
    {"target": "proxy", "confidence": 0.8, "source": "deprecation_message"},
    {"target": "mounts", "confidence": 0.79, "source": "deprecation_message"}
  ],
  "pin_to_restore": "httpx<=0.27.2",
  "confidence": "high"
}
```

That's the real answer from the published index, trimmed. The full answer also quotes the deprecation message DepTime found in httpx's own source, and adds a one-sentence explanation for the agent to pass on:

> httpx.Client.__init__ accepted `proxies` up to httpx 0.27.2; it is gone from 0.28.0 onward. Deprecated in 0.26.0 ("The 'proxies' argument is now deprecated. Use 'proxy' or 'mounts' instead."). Use `proxy` or `mounts` instead, or pin httpx<=0.27.2.

## Tools

| Tool | Use it when |
|---|---|
| `explain_error(traceback, installed_versions?, pip_freeze?)` | An import or call into a library just failed |
| `symbol_history(package, path)` | Before trusting an API you remember |
| `check_symbols(package, version, symbols[{path, kwargs}])` | Pre-flight check of the symbols and kwargs you're about to use |
| `diff_versions(package, from_version \| date, to_version?, used_symbols?)` | Upgrading, or "what changed since my training cutoff?" |
| `check_upgrade(package, from_version, to_version?, code? \| files?)` | Updating a dependency: the lines of your code the new version breaks |
| `coverage()` | What's indexed (53 fast-moving packages: AI/agent stack + libraries with known breaking changes; [list](https://github.com/cschmertz/deptime/blob/main/docs/coverage.md)) |

Every answer carries evidence and a confidence level. The contracts are in [docs/03-product-spec.md](https://github.com/cschmertz/deptime/blob/main/docs/03-product-spec.md).

## How well it works

Every DepTime number in the table is a **first run**: the cases and their right answers were collected and committed before DepTime ever ran on them.

| How often does it… | First run | Measured on |
|---|---|---|
| find the right package, name and breaking release from a real traceback? | **87%** (166 of 191) | Tracebacks from GitHub issues and Stack Overflow, in six sets |
| *…and a language model alone, answering the same tracebacks from memory with no tools?* | *82% to 84%* (Claude Sonnet 5.5 and Opus 5.5), *66% to 69%* (Haiku 5.5), *59%* (DeepSeek V4.1 Flash), *19%* (Qwen3.5 9B) | The same 191, [scored the same way](https://github.com/cschmertz/deptime/blob/main/bench/model-alone/results-2026-11-15.md). The larger models name the change and its replacement more often than DepTime, and the release less often |
| offer the right replacement among its first three suggestions? | **48%** (41 of 85) | The same tracebacks, where a replacement is known |
| flag code that still works after an upgrade? (lower is better) | **0.1%** (2 of 2,047) | Uses of covered packages in real projects, labelled by running them. Newest of six sets; the oldest scored 3.8% |
| find the code that an upgrade breaks? | **100%** (147 of 147) | The same projects. Newest set; the six range from 95.9% to 100% |
| *…and a language model alone, judging the same uses from memory?* | Breaks found and working code flagged: *91% and 0.2%* (Sonnet 5.5), *74% and 0.3%* (Haiku 5.5), *81% and 2.7%* (DeepSeek V4.1 Flash), *31% and 15%* (Qwen3.5 9B) | The same 2,265 uses, one run per model, [scored the same way](https://github.com/cschmertz/deptime/blob/main/bench/model-alone/upgrades/results-2026-11-15.md), counting `unknown` as not flagged; counted that way, DepTime finds 96.7% |

- **The upgrade checks are the strong part.** The last two rows are `check_symbols`. On the same set, `diff_versions` found 96.7% of the breaks (147 of 152) and flagged 0.1% of working code (2 of 2,113).
- **The smaller the model, the more DepTime adds.** Claude Opus and Sonnet alone come within a few points of it.
  Haiku, DeepSeek V4.1 Flash and Qwen3.5 9B fall 18 to 68 points behind on the tracebacks, and on the upgrade checks the
  two cheaper ones flag 2.7% and 15% of working code, against DepTime's 0.1%. Given DepTime's tools, Qwen3.5 9B
  still flags 3.5% to 4.5% ([results](https://github.com/cschmertz/deptime/blob/main/bench/model-alone/check-upgrade/results-2026-11-16.md)):
  to get DepTime's precision, run its check rather than have a small model judge each use.
- **Replacements are the weak part.** On unseen errors the right one is offered about half the time, where the Claude models in the second row offer it 87% to 99% of the time. A suggestion at confidence 0.75 or more is usually right: 11 of 11 on the first run over 50 documented migrations, 42 of 45 now.
- **The same cases score higher today** (97.2% of all 393 real tracebacks in the benchmark), because fixes were designed from their misses. That is why the first run is the number to trust.
- **Where it can't tell, it says so.** `check_symbols` answered `unknown`, with the reason, for 66 working uses and 5 breaks of the newest set, which are left out of its rates above.

Every set, every later re-run and each miss is in [bench/README.md](https://github.com/cschmertz/deptime/blob/main/bench/README.md#results-every-check-first-run-and-now). CI re-scores all of it on every code change and every published index, and fails on a drop of more than 2 points.

## What it doesn't do

- **It covers the packages on its [list](https://github.com/cschmertz/deptime/blob/main/docs/coverage.md), not all of PyPI,** and every release of each minor series active since 2023. For anything else the answer is "not covered".
- **It reads source without running it.** A name that only exists once the library is running (built by compiled code, or computed at import time) can read as `unknown`, or occasionally as missing.
- **It sees names, parameters and deprecations, not behaviour.** A function that keeps its signature but changes what it does is invisible to it, so a clean upgrade check doesn't replace your tests.
- **Python only.**

## How it works

<p>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/cschmertz/deptime/main/docs/assets/how-it-works-dark.svg">
  <img alt="How DepTime works. Built on GitHub: new PyPI releases are read statically and diffed release to release; packages are never imported or run. The only thing that crosses to your machine is one file, index.sqlite.xz. Answered on your machine: deptime mcp answers your agent locally, and your code and errors stay there." src="https://raw.githubusercontent.com/cschmertz/deptime/main/docs/assets/how-it-works-light.svg">
</picture>
</p>

Twice a day, GitHub Actions reads each new release's public API with [griffe](https://mkdocstrings.github.io/griffe/), which parses the source without running it, diffs it against the previous release, and publishes the result as one file, `index.sqlite.xz`, on this repo's Releases. On your machine, `deptime mcp` checks that file's sha256 and schema before swapping it in, then answers every question locally in milliseconds. The full design is in [docs/04-architecture.md](https://github.com/cschmertz/deptime/blob/main/docs/04-architecture.md), and the decisions are in [docs/adr/](https://github.com/cschmertz/deptime/tree/main/docs/adr).

## CLI

```bash
uvx deptime explain --installed httpx==0.28.1 < traceback.txt
uvx deptime history httpx Client.__init__
uvx deptime check httpx 0.28.1 'httpx.Client:proxies,proxy'
uvx deptime diff httpx 0.27.2 0.28.1
uvx deptime diff pydantic 2024-06-01              # everything since a date
uvx deptime check-upgrade                         # what the lockfile change breaks; exit 1 on a break
uvx deptime index status | pull
```

## Hosting (optional)

Local mode covers coding agents. For web clients that only accept a URL, run `deptime serve` (MCP at `/mcp`, JSON at `/v1/*`) on any container host. The repo includes a `Dockerfile` and `fly.toml`, and the server applies anonymous rate limits. See [docs/05-self-hosting.md](https://github.com/cschmertz/deptime/blob/main/docs/05-self-hosting.md).

## Prior art and credits

- [griffe](https://github.com/mkdocstrings/griffe) does the static analysis.
- [since-cutoff](https://github.com/MohammadHijjawi97/since-cutoff) diffs your pinned dependencies against a model's training cutoff, locally and on demand. DepTime differs by shipping a prebuilt cross-version index and starting from a traceback.
- [Context7](https://context7.com) and [Ref](https://ref.tools) serve version-specific docs. DepTime answers symbol-level "when and what replaced it" questions.

## Contributing

The most useful contributions are wrong-answer reports, which become benchmark cases. See [CONTRIBUTING.md](https://github.com/cschmertz/deptime/blob/main/CONTRIBUTING.md). Development setup:

```bash
uv sync && uv run pytest
# build a small local index from real PyPI wheels
uv run deptime ingest httpx --versions 0.27.2 0.28.1
```

## Docs

[Product spec](https://github.com/cschmertz/deptime/blob/main/docs/03-product-spec.md) · [Architecture](https://github.com/cschmertz/deptime/blob/main/docs/04-architecture.md) · [Self-hosting](https://github.com/cschmertz/deptime/blob/main/docs/05-self-hosting.md) · [Risks & spikes](https://github.com/cschmertz/deptime/blob/main/docs/07-risks-and-spikes.md) · [Privacy & security](https://github.com/cschmertz/deptime/blob/main/docs/08-privacy-and-security.md) · [Benchmark](https://github.com/cschmertz/deptime/blob/main/bench/README.md) · [Changelog](https://github.com/cschmertz/deptime/blob/main/CHANGELOG.md)

## License

[MIT](https://github.com/cschmertz/deptime/blob/main/LICENSE)

<!-- mcp-name: io.github.cschmertz/deptime -->
