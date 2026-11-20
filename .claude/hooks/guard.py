"""PreToolUse guard. Standard library only.

Reads one tool-call JSON object on stdin. Prints a deny decision on stdout, or
prints nothing and exits 0 to allow. Fails closed: if the input cannot be read
or the guard itself crashes, the call is denied.

What it blocks, and why (see CLAUDE.md, operating rules 1 and 5):
  1. Send attempts in Bash (mail libraries, mail -s, POST to messaging/CRM APIs).
  2. Write/Edit/NotebookEdit to data/accounts.csv, data/signals.csv, data/scored.csv,
     after resolving relative, ./ and .. paths.
  3. Bash writes to those files by redirect, tee, inline python, or a file tool.
  4. Bash network tools: curl, wget, nc, ssh, scp.
  5. Write to any path outside the repo root.
  6. MCP tools whose name is a send action (send, reply, forward, post,
     publish, create_message, or anything containing "send"). Matched on the
     last "__" segment of the tool name, so read tools on the same server
     pass. Registered before any MCP server is connected.

This is a tripwire, not a sandbox. A determined script can still evade string
matching; the permission deny list in settings.json is the second layer.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTECTED_NAMES = ("accounts.csv", "signals.csv", "scored.csv")

# Rule 1: send attempts.
#
# The mail-library names below are stored in pieces and joined at runtime, the
# same way scripts/acceptance.py stores its own C9 patterns, so this blocklist
# does not match itself. guard.py is deliberately NOT excluded from the C9
# never-send scan: a never-send check that skips the file most capable of
# sending is not a check. Keep the split when adding names here.
_MAIL_LIBS = (
    "smtp" + "lib", "send" + "grid", "mail" + "gun",
    "re" + "send", "post" + "mark", "send" + "mail",
)
SEND_RE = re.compile(
    r"\b(" + "|".join(_MAIL_LIBS) + r")\b"
    r"|\bses\.send"
    r"|\bsend_(raw_)?email\b"
    r"|\bmailx?\s+-s\b",
    re.IGNORECASE,
)
MESSAGING_HOSTS = (
    "hooks.slack.com", "slack.com/api", "api.telegram.org", "discord.com/api",
    "discordapp.com/api", "api.twilio.com", "graph.microsoft.com",
    "gmail.googleapis.com", "api.hubapi.com", "api.hubspot.com",
    "salesforce.com", "api.pipedrive.com", "api.intercom.io", "api.apollo.io",
    "api.lemlist.com", "api.instantly.ai", "api.outreach.io", "salesloft.com",
    "api.close.com", "api.attio.com", "zohoapis.com", "api.clay.com",
    "api.smartlead.ai", "api.mailchimp.com", "api.brevo.com",
    "api.sendinblue.com", "api.linkedin.com", "webhook.site", "zapier.com/hooks",
)
POST_RE = re.compile(
    r"-X\s*POST|--request[\s=]*POST|\.post\s*\(|method\s*=\s*['\"]?POST"
    r"|--data\b|--json\b|(?:^|\s)-d\s|(?:^|\s)-F\s|--form\b|-Method\s+Post"
    r"|urlopen\s*\([^)]*data\s*=",
    re.IGNORECASE,
)

# Rule 4: network tools, as a command word (bare, or with a path / .exe).
NET_RE = re.compile(
    r"(?:^|[\s;&|(`$/\\\"'])"
    r"(curl|wget|nc|ncat|ssh|scp|Invoke-WebRequest|Invoke-RestMethod|iwr|irm)"
    r"(?:\.exe)?(?=$|[\s;&|)`\"'])",
    re.IGNORECASE,
)

# Rule 3: Bash writes to protected CSVs.
PROTECTED_RE = re.compile(r"\b(accounts|signals|scored)\.csv\b", re.IGNORECASE)
REDIRECT_RE = re.compile(
    r"(?:^|[^<>])(?:\d*|&)>>?\|?\s*(\"[^\"]*\"|'[^']*'|[^\s;&|<>()]+)"
)
TEE_RE = re.compile(r"\btee\b((?:\s+(?:\"[^\"]*\"|'[^']*'|[^\s;&|<>()]+))*)")
PY_INLINE_RE = re.compile(
    r"\b(?:python[\d.]*|py)(?:\.exe)?\s+(?:-[A-Za-z]*\s+)*(?:-[A-Za-z]*c\b|-(?=\s|$))",
    re.IGNORECASE,
)
UNVERIFIABLE_RE = re.compile(r"[$`*?\[{]")
FILE_WRITERS = {
    "cp", "mv", "rm", "truncate", "dd", "install", "ln",
    "set-content", "add-content", "out-file", "clear-content",
    "copy-item", "move-item", "remove-item",
}
SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|\n]")

# Rule 6: MCP send tools. Exact names, plus send verbs that lead the name
# (post_to_channel, reply_all). A verb mid-name is not matched, so
# get_social_post_analytics stays allowed. "send" anywhere in the name denies.
MCP_SEND_NAMES = {
    "send", "send_message", "send_email", "reply", "forward", "post",
    "post_message", "publish", "create_message",
}
MCP_SEND_VERBS = {"send", "reply", "forward", "post", "publish"}

# Send-capable MCP tools whose names contain no blocked word. Matched exactly
# on the last "__" segment, case-insensitive, with "-" treated as "_".
#
# This denylist is a backstop, not a guarantee. It is name-based, so it goes
# stale the day a vendor adds or renames a tool. The real guarantee is that
# this repo declares no send-capable MCP server (no .mcp.json, no mcpServers
# in settings). Account-level connectors (claude.ai) sit outside the repo;
# disconnect them for this project rather than trusting this list.
MCP_SEND_DENYLIST = {
    "manage_marketing_email",
    "manage_social_posts",
    "create_draft",
    "manage_campaign_objects",
    "import_claude_design_from_url",
}

# File tools and the input key that holds their target path.
FILE_TOOLS = {
    "Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}


def _deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "guard.py: " + reason,
        }
    }


def _norm(path_str, base):
    """Resolve a path the way the OS will see it, then normalise case and separators."""
    p = path_str.strip().strip("\"'")
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])(?:/|$)(.*)$", p)  # Git Bash style /d/dev/...
        if m:
            p = f"{m.group(1)}:/{m.group(2)}"
    p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.join(base, p)
    return os.path.normcase(os.path.realpath(p))


def _is_protected(resolved, root):
    targets = {_norm(os.path.join(str(root), "data", n), str(root)) for n in PROTECTED_NAMES}
    if resolved in targets:
        return True
    # Belt and braces: any data/<protected> path, even in another checkout.
    tail = resolved.replace("\\", "/")
    return any(tail.endswith("/data/" + os.path.normcase(n)) for n in PROTECTED_NAMES)


def _inside(resolved, root):
    root_n = _norm(str(root), str(root))
    try:
        return os.path.commonpath([root_n, resolved]) == root_n
    except ValueError:  # different drives
        return False


def _basename(token):
    t = token.strip().strip("\"'").replace("\\", "/")
    t = t.rsplit("=", 1)[-1]  # dd of=..., --output=...
    return t.rsplit("/", 1)[-1].lower()


def _check_mcp(tool):
    """Deny an MCP tool whose last name segment is a send action."""
    last = tool.rsplit("__", 1)[-1]
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", last).lower().replace("-", "_")
    words = [w for w in snake.split("_") if w]
    if last.lower().replace("-", "_") in MCP_SEND_DENYLIST:
        return (
            f"MCP tool {tool} blocked: '{last}' is on the send-capable denylist. "
            "Rule 1: NEVER SEND."
        )
    if snake in MCP_SEND_NAMES or "send" in snake or (words and words[0] in MCP_SEND_VERBS):
        return (
            f"MCP tool {tool} blocked: '{last}' is a send action. "
            "Rule 1: NEVER SEND. Drafts are files marked DRAFT - NOT SENT."
        )
    return None


def _check_file_tool(tool, tool_input, root, cwd):
    key = FILE_TOOLS[tool]
    path = tool_input.get(key)
    if not isinstance(path, str) or not path.strip():
        return f"{tool} call has no {key}, so its target cannot be verified."
    resolved = _norm(path, cwd)
    if _is_protected(resolved, root):
        return (
            f"{tool} to {path} blocked: it resolves to a protected CSV ({resolved}). "
            "Rule 5: scripts write the CSVs. Write JSON to data/staging/ and run "
            "python scripts/ingest.py."
        )
    if tool == "Write" and not _inside(resolved, root):
        return f"Write to {path} blocked: it resolves outside the repo root ({resolved})."
    return None


def _check_bash(cmd):
    # Rule 1: send attempts.
    m = SEND_RE.search(cmd)
    if m:
        return (
            f"Bash blocked: send attempt detected ('{m.group(0)}'). "
            "Rule 1: NEVER SEND. Drafts are files marked DRAFT - NOT SENT."
        )
    low = cmd.lower()
    host = next((h for h in MESSAGING_HOSTS if h in low), None)
    if host and POST_RE.search(cmd):
        return (
            f"Bash blocked: HTTP POST to messaging/CRM endpoint '{host}'. "
            "Rule 1: NEVER SEND."
        )

    # Rule 4: network tools.
    m = NET_RE.search(cmd)
    if m:
        return (
            f"Bash blocked: network tool '{m.group(1)}' is not allowed. "
            "Use WebFetch for public pages or a script in scripts/."
        )

    # Rule 3: writes to protected CSVs.
    for m in REDIRECT_RE.finditer(cmd):
        target = m.group(1).strip("\"'")
        if UNVERIFIABLE_RE.search(target):
            return (
                f"Bash blocked: redirect target '{target}' uses a variable or glob, "
                "so the guard cannot verify it is not a protected CSV."
            )
        if _basename(target) in PROTECTED_NAMES:
            return (
                f"Bash blocked: redirect into '{target}'. "
                "Rule 5: only scripts/*.py write accounts/signals/scored.csv."
            )
    for m in TEE_RE.finditer(cmd):
        for arg in m.group(1).split():
            arg = arg.strip("\"'")
            if arg.startswith("-"):
                continue
            if UNVERIFIABLE_RE.search(arg) or _basename(arg) in PROTECTED_NAMES:
                return (
                    f"Bash blocked: tee into '{arg}'. "
                    "Rule 5: only scripts/*.py write the protected CSVs."
                )
    if PROTECTED_RE.search(cmd) and PY_INLINE_RE.search(cmd):
        return (
            "Bash blocked: inline python (-c or stdin) that names a protected CSV. "
            "Rule 5: run python scripts/ingest.py instead."
        )
    for seg in SEGMENT_SPLIT_RE.split(cmd):
        if not PROTECTED_RE.search(seg):
            continue
        try:
            tokens = shlex.split(seg, posix=True)
        except ValueError:
            tokens = seg.split()
        tokens = [t for t in tokens if not re.match(r"^[A-Za-z_]\w*=", t)]  # env assignments
        if tokens and tokens[0] == "sudo":
            tokens = tokens[1:]
        if not tokens:
            continue
        word = _basename(tokens[0]).removesuffix(".exe")
        in_place = word in ("sed", "perl") and any(t.startswith("-i") or t == "--in-place" for t in tokens)
        if word in FILE_WRITERS or in_place:
            return (
                f"Bash blocked: '{word}' on a protected CSV. "
                "Rule 5: only scripts/*.py write accounts/signals/scored.csv."
            )
    return None


def decide(payload, repo_root=REPO_ROOT):
    """Return a deny-decision dict, or None to allow."""
    if not isinstance(payload, dict):
        return _deny("hook input is not a JSON object; failing closed.")
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        return _deny("hook input has no tool_name; failing closed.")
    tool_input = payload.get("tool_input")
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) and cwd.strip() else str(repo_root)

    if tool.startswith("mcp__"):
        reason = _check_mcp(tool)
        return _deny(reason) if reason else None

    if tool in FILE_TOOLS or tool == "Bash":
        if not isinstance(tool_input, dict):
            return _deny(f"{tool} call has no tool_input object; failing closed.")

    reason = None
    if tool in FILE_TOOLS:
        reason = _check_file_tool(tool, tool_input, repo_root, cwd)
    elif tool == "Bash":
        cmd = tool_input.get("command")
        if not isinstance(cmd, str):
            return _deny("Bash call has no command string; failing closed.")
        reason = _check_bash(cmd)
    return _deny(reason) if reason else None


def evaluate_raw(raw, repo_root=REPO_ROOT):
    """Parse raw stdin text and decide. Any failure is a deny."""
    try:
        payload = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        return _deny(f"could not parse hook input as JSON ({type(e).__name__}); failing closed.")
    try:
        return decide(payload, repo_root)
    except Exception as e:  # noqa: BLE001
        return _deny(f"guard crashed ({type(e).__name__}: {e}); failing closed.")


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
    except Exception as e:  # noqa: BLE001
        result = _deny(f"could not read stdin ({type(e).__name__}); failing closed.")
    else:
        result = evaluate_raw(raw)
    if result is not None:
        sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
