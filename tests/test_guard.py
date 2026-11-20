"""Self-check for .claude/hooks/guard.py.

Feeds tool-call dicts straight to guard.decide() and asserts allow or deny.
Nothing is written to disk and nothing touches the network: the guard only
resolves paths, it never opens them.
Prints PASS or FAIL per case and exits 1 if any case fails.

    python tests/test_guard.py
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("guard", ROOT / ".claude" / "hooks" / "guard.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

FAILS = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(name)


def call(tool, **tool_input):
    return {"tool_name": tool, "tool_input": tool_input, "cwd": str(ROOT)}


def expect(name, payload, allowed):
    out = guard.decide(payload, ROOT)
    if allowed:
        check(name, out is None, f"denied: {out and out['hookSpecificOutput']['permissionDecisionReason']}")
    else:
        ok = (
            out is not None
            and out["hookSpecificOutput"]["permissionDecision"] == "deny"
            and out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
            and out["hookSpecificOutput"]["permissionDecisionReason"]
        )
        check(name, bool(ok), "was allowed")


# Required cases.
expect("allow: python scripts/ingest.py", call("Bash", command="python scripts/ingest.py"), True)
expect("deny: Write data/accounts.csv", call("Write", file_path="data/accounts.csv", content="x"), False)
expect("deny: Write ./data/accounts.csv", call("Write", file_path="./data/accounts.csv", content="x"), False)
expect("deny: Write out/../data/accounts.csv", call("Write", file_path="out/../data/accounts.csv", content="x"), False)
expect("deny: Bash smtplib import", call("Bash", command='python -c "import smtplib"'), False)
expect("deny: Bash curl", call("Bash", command="curl https://example.com"), False)
expect("deny: echo > data/scored.csv", call("Bash", command="echo x > data/scored.csv"), False)
expect("allow: Write out/briefs/x.md", call("Write", file_path="out/briefs/x.md", content="# DRAFT - NOT SENT"), True)

# Path resolution edges.
expect("deny: absolute .. path", call("Edit", file_path=str(ROOT / "out" / ".." / "data" / "signals.csv"),
                                      old_string="a", new_string="b"), False)
if sys.platform == "win32":  # case-insensitive filesystem: DATA/SCORED.CSV is the same file
    expect("deny: upper-case path", call("Edit", file_path="DATA/SCORED.CSV", old_string="a", new_string="b"), False)
expect("deny: relative from subdir cwd", {"tool_name": "Write", "cwd": str(ROOT / "out"),
                                          "tool_input": {"file_path": "../data/accounts.csv"}}, False)
expect("allow: Write data/staging/x.json", call("Write", file_path="data/staging/x.json", content="{}"), True)
expect("deny: Write outside repo", call("Write", file_path=str(ROOT.parent / "elsewhere.txt"), content="x"), False)
expect("deny: Write via .. escaping repo", call("Write", file_path="../escape.txt", content="x"), False)

# Bash write paths.
expect("deny: >> append", call("Bash", command="printf 'a\\n' >> ./data/signals.csv"), False)
expect("deny: tee", call("Bash", command="cat x | tee -a data/accounts.csv"), False)
expect("deny: python -c names CSV", call("Bash", command="python -c \"open('data/scored.csv','w')\""), False)
expect("deny: cp onto CSV", call("Bash", command="cp /tmp/x.csv data/accounts.csv"), False)
expect("deny: redirect to variable", call("Bash", command='echo x > "$OUT"'), False)
expect("allow: 2>&1 and /dev/null", call("Bash", command="python scripts/score.py 2>&1 > /dev/null"), True)
expect("allow: redirect to out/", call("Bash", command="python scripts/score.py > out/score.log"), True)

# Send and network edges.
expect("deny: mail -s", call("Bash", command='mail -s "hi" a@b.c < draft.md'), False)
expect("deny: POST to Slack via python", call("Bash", command=
       "python -c \"import requests; requests.post('https://hooks.slack.com/services/x', json={})\""), False)
expect("deny: wget", call("Bash", command="wget -q https://example.com"), False)
expect("deny: /usr/bin/ssh", call("Bash", command="/usr/bin/ssh host"), False)
expect("allow: 'sync' is not nc", call("Bash", command="git status && echo sync"), True)

# MCP send tools (rule 1) and NotebookEdit (rule 5).
expect("deny: mcp__gmail__send_message", call("mcp__gmail__send_message", to="a@b.c"), False)
expect("deny: mcp__slack__post_message", call("mcp__slack__post_message", channel="x"), False)
expect("deny: mcp__hubspot__send_email", call("mcp__hubspot__send_email"), False)
expect("allow: mcp__sheets__get_values", call("mcp__sheets__get_values", range="A1"), True)
expect("allow: mcp__hubspot__search_crm_objects", call("mcp__hubspot__search_crm_objects"), True)
expect("deny: NotebookEdit data/accounts.csv", call("NotebookEdit", notebook_path="data/accounts.csv",
                                                    new_source="x"), False)
expect("deny: mcp forward", call("mcp__claude_ai_Gmail__forward"), False)
expect("deny: mcp camelCase sendMessage", call("mcp__x__sendMessage"), False)
expect("allow: mcp post mid-name is a read", call("mcp__hubspot__get_social_post_analytics"), True)
for _name in ("manage_marketing_email", "manage_social_posts", "create_draft",
              "manage_campaign_objects", "import-claude-design-from-url"):
    expect(f"deny: denylist {_name}", call(f"mcp__claude_ai_HubSpot__{_name}"), False)
expect("allow: trash_message is not a send", call("mcp__claude_ai_Gmail__trash_message"), True)
expect("allow: mcp__sheets__get_values (after denylist)", call("mcp__sheets__get_values"), True)
expect("allow: mcp__hubspot__search_crm_objects (after denylist)", call("mcp__hubspot__search_crm_objects"), True)
expect("allow: NotebookEdit out/x.ipynb", call("NotebookEdit", notebook_path="out/x.ipynb", new_source="x"), True)

# Rule 7: interpreter reading its program from stdin (hunt 3 bypass, 2026-11-20).
expect("deny: heredoc into python -I -", call("Bash", command="python -I - a b <<'EOF'\nprint(1)\nEOF"), False)
expect("deny: python - < file", call("Bash", command="python - < x.py"), False)
expect("deny: cat x | python", call("Bash", command="cat x.py | python"), False)
expect("deny: echo | python3 -", call("Bash", command="echo 'print(1)' | python3 -"), False)
expect("deny: curl-less | sh", call("Bash", command="cat install.txt | sh"), False)
expect("deny: | bash -s", call("Bash", command="cat x | bash -s"), False)
expect("deny: node from heredoc", call("Bash", command="node <<'EOF'\nconsole.log(1)\nEOF"), False)
expect("deny: perl from pipe", call("Bash", command="cat x.pl | perl"), False)
expect("deny: cd && python -", call("Bash", command="cd /d/dev && python - <<'EOF'\nx\nEOF"), False)
expect("allow: python script reading data on stdin", call("Bash", command="python scripts/ingest.py < data/staging/x.json"), True)
expect("allow: pipe into python script", call("Bash", command="cat x.json | python scripts/ingest.py --dry-run"), True)
expect("allow: python -m pytest", call("Bash", command="python -m pytest tests"), True)
expect("allow: python --version", call("Bash", command="python --version"), True)
expect("allow: bash script by path", call("Bash", command="bash scripts/run.sh"), True)

# Fail closed.
check("deny: malformed JSON", guard.evaluate_raw("{not json", ROOT) is not None)
check("deny: non-object JSON", guard.evaluate_raw("[1,2]", ROOT) is not None)
check("deny: Bash without command", guard.decide({"tool_name": "Bash", "tool_input": {}}, ROOT) is not None)
check("deny: Write without file_path", guard.decide({"tool_name": "Write", "tool_input": {}}, ROOT) is not None)
check("allow: unrelated tool", guard.evaluate_raw(json.dumps({"tool_name": "Read", "tool_input": {}}), ROOT) is None)

print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
