#!/usr/bin/env python3
"""Fail-closed, local-only sync.json guard (Python 3.9+, Unix).

Candidate must resolve to a regular file directly in the invocation's cwd.
JSON numbers are compared exactly; duplicate keys/non-JSON constants are refused.
Fields are literal top-level names, except YYYY-MM-DD.child (one date child).
A selected field can be added, but not deleted. _revision is guard-owned.
manualTasks is immutable, even inside a selected parent. Existing work IDs
cannot disappear or be reclassified. TODAY.tpl's 37 resident rows are frozen
from the baseline; historical tpl nodes preserve existing IDs and manual rows.

Only sync.json is replaced. The expressly permitted .git lock persists.
All payload staging files start in the invocation's cwd, outside the repository,
are fsynced, and are retained on error. Cross-filesystem replacement fails rather
than creating a staging file in production. No fetch, Git writes, or cleanup occurs.
flock coordinates cooperating writers; non-cooperating writers cannot be given
an atomic compare-and-swap guarantee by os.replace, so a final SHA check is used.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time

MAX_SAFE_INTEGER = 2**53 - 1
LOCK_NAME = "sync-guard.lock"
WS = re.compile(r"[ \t\r\n]*")
DATE_CHILD = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(.+)$")
MISSING = object()


class GuardError(Exception):
    """An unsafe input or repository state; sync.json must not be overwritten."""


def require(condition, message):
    if not condition:
        raise GuardError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _constant(value):
    raise GuardError(f"not a JSON number: {value}")


DECODER = json.JSONDecoder(object_pairs_hook=_pairs, parse_float=Decimal,
                           parse_constant=_constant)


@dataclass(frozen=True)
class Member:
    key_start: int
    key_end: int
    start: int
    end: int


@dataclass(frozen=True)
class Document:
    text: str
    data: dict
    members: dict[str, Member]
    opening: int
    closing: int


def decode_document(raw):
    text = raw.decode("utf-8")
    pos = WS.match(text, 1 if text.startswith("\ufeff") else 0).end()
    require(pos < len(text) and text[pos] == "{", "JSON root must be an object")
    opening = pos
    pos = WS.match(text, pos + 1).end()
    data, members = {}, {}
    if pos < len(text) and text[pos] != "}":
        while True:
            key_start = pos
            key, key_end = DECODER.raw_decode(text, pos)
            require(isinstance(key, str), "JSON object key must be a string")
            require(key not in data, f"duplicate JSON key: {key!r}")
            pos = WS.match(text, key_end).end()
            require(pos < len(text) and text[pos] == ":", "missing JSON colon")
            start = WS.match(text, pos + 1).end()
            value, end = DECODER.raw_decode(text, start)
            data[key] = value
            members[key] = Member(key_start, key_end, start, end)
            pos = WS.match(text, end).end()
            require(pos < len(text), "unterminated JSON object")
            if text[pos] == "}":
                break
            require(text[pos] == ",", "missing JSON comma")
            pos = WS.match(text, pos + 1).end()
    require(pos < len(text) and text[pos] == "}", "missing closing JSON brace")
    require(WS.match(text, pos + 1).end() == len(text), "trailing JSON content")
    return Document(text, data, members, opening, pos)


def equal(left, right):
    if left is MISSING or right is MISSING:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, Decimal)) and isinstance(right, (int, Decimal)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    return left == right


def encode_value(value):
    """Compact JSON without converting exact Decimal values into floats."""
    if isinstance(value, dict):
        return "{" + ", ".join(json.dumps(k, ensure_ascii=False) + ": " + encode_value(v)
                                 for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(encode_value(v) for v in value) + "]"
    if isinstance(value, Decimal):
        require(value.is_finite(), "non-finite JSON number")
        return str(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def revision(data, label):
    value = data.get("_revision", MISSING)
    if value is MISSING:
        return 0
    require(type(value) is int and 1 <= value <= MAX_SAFE_INTEGER,
            f"{label}._revision must be a positive safe integer")
    return value


def selections(fields, old, candidate):
    require(bool(fields), "at least one --field is required")
    top, children = set(), {}
    for field in fields:
        require(bool(field) and field != "_revision", "--field cannot be empty or _revision")
        match = DATE_CHILD.fullmatch(field)
        if match:
            date, child = match.groups()
            children.setdefault(date, set()).add(child)
        else:
            top.add(field)
    require(not top.intersection(children), "overlapping parent and date-child --field")
    for key in top:
        require(key in candidate, f"selected field missing in candidate: {key!r}")
    for date, keys in children.items():
        require(isinstance(candidate.get(date), dict), f"candidate date must be an object: {date}")
        require(date not in old or isinstance(old[date], dict), f"baseline date is not an object: {date}")
        for key in keys:
            require(key in candidate[date], f"selected field missing in candidate: {date}.{key}")
    return top, children


def validate_changes(old, candidate, top, children):
    for key in old.keys() | candidate.keys():
        if key == "_revision" or key in top:
            continue
        if key in children:
            a, b = old.get(key, {}), candidate[key]
            for child in a.keys() | b.keys():
                if child not in children[key]:
                    require(equal(a.get(child, MISSING), b.get(child, MISSING)),
                            f"non-target field differs: {key}.{child}")
        else:
            require(equal(old.get(key, MISSING), candidate.get(key, MISSING)),
                    f"non-target field differs: {key!r}")


def manual_lines(value, label):
    require(isinstance(value, list), f"{label} must be a list")
    lines = []
    for item in value:
        line = item if isinstance(item, str) else item.get("line") if isinstance(item, dict) else None
        require(isinstance(line, str) and bool(line.strip()) and len(line.splitlines()) == 1,
                f"{label} contains a missing/empty/multiline original row")
        lines.append(line)
    return lines


def task_rows(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label} must have non-empty rows")
    rows = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        require(len(parts) >= 4 and all(parts), f"{label} contains an empty/malformed row")
        require(parts[0] not in rows, f"{label} contains duplicate task ID: {parts[0]}")
        rows[parts[0]] = (line, parts)
    return rows


def protect_template(old_tpl, new_tpl, manual, label, residents):
    old_rows, new_rows = task_rows(old_tpl, label + " baseline"), task_rows(new_tpl, label + " candidate")
    old_work = {key for key, (_, parts) in old_rows.items() if parts[1] == "工作线"}
    new_work = {key for key, (_, parts) in new_rows.items() if parts[1] == "工作线"}
    require(old_work <= new_work, f"old work IDs disappeared/reclassified in {label}: {sorted(old_work - new_work)}")
    if not residents:
        require(old_rows.keys() <= new_rows.keys(), f"old task IDs disappeared in {label}")
    old_counts, new_counts = Counter(old_tpl.splitlines()), Counter(new_tpl.splitlines())
    require(all(old_counts[line] >= count and new_counts[line] >= count
                for line, count in Counter(manual).items()),
            f"manualTasks original rows missing in {label}")
    if residents:
        manual_ids = {line.split("|", 1)[0].strip() for line in manual}
        resident = {key: row for key, row in old_rows.items()
                    if row[1][1] != "工作线" and key not in manual_ids}
        require(len(resident) == 37, f"{label} baseline must contain exactly 37 resident rows")
        for key, (line, parts) in resident.items():
            require(len(parts) == 6 and all(parts), f"resident row must have six populated values: {key}")
            require(key in new_rows and new_rows[key][0] == line,
                    f"resident row changed/missing: {key}")
        new_resident = {key for key, (_, parts) in new_rows.items()
                        if parts[1] != "工作线" and key not in manual_ids}
        require(new_resident == resident.keys(),
                f"{label} candidate must contain exactly the same 37 resident rows")


def protect_tasks(old, candidate, path="root"):
    """Check both trees, including additions and container-type replacements."""
    if isinstance(old, dict) or isinstance(candidate, dict):
        before = old if isinstance(old, dict) else {}
        after = candidate if isinstance(candidate, dict) else {}
        if "manualTasks" in before or "manualTasks" in after:
            require(equal(before.get("manualTasks", MISSING), after.get("manualTasks", MISSING)),
                    f"manualTasks must remain completely unchanged at {path}")
        for key in ("TODAY.tpl", "tpl"):
            residents = path == "root" and key == "TODAY.tpl"
            if key in before and (residents or not equal(before[key], after.get(key, MISSING))):
                manual = manual_lines(before.get("manualTasks", []), path + ".manualTasks")
                protect_template(before[key], after.get(key, MISSING), manual,
                                 path + "." + key, residents=residents)
        for key in before.keys() | after.keys():
            protect_tasks(before.get(key, MISSING), after.get(key, MISSING), path + "." + key)
    if isinstance(old, list) or isinstance(candidate, list):
        before = old if isinstance(old, list) else []
        after = candidate if isinstance(candidate, list) else []
        for index in range(max(len(before), len(after))):
            protect_tasks(before[index] if index < len(before) else MISSING,
                          after[index] if index < len(after) else MISSING, f"{path}[{index}]")


def patch_document(document, values):
    """Change only existing top-level value spans; add new members locally."""
    edits, additions = [], []
    for key, value_text in values.items():
        if key in document.members:
            member = document.members[key]
            edits.append((member.start, member.end, value_text))
        else:
            additions.append((key, value_text))
    if additions:
        if document.members:
            last = next(reversed(document.members.values()))
            first = next(iter(document.members.values()))
            gap = document.text[document.opening + 1:first.key_start]
            line_start = document.text.rfind("\n", 0, last.key_start) + 1
            indent = document.text[line_start:last.key_start]
            if "\n" in gap and not indent.strip():
                separator = ("\r\n" if "\r\n" in gap else "\n") + indent
            else:
                separator = gap if not gap.strip() else " "
            colon = document.text[last.key_end:last.start]
            at = last.end
            prefix = "," + separator
        else:
            gap = document.text[document.opening + 1:document.closing]
            separator = "\r\n" if "\r\n" in gap else "\n" if "\n" in gap else " " if gap else ""
            colon, at, prefix = ": ", document.opening + 1, separator
        body = ("," + separator).join(json.dumps(k, ensure_ascii=False) + colon + v for k, v in additions)
        edits.append((at, at, prefix + body))
    text = document.text
    # Insertions at a replaced value's end are applied before that replacement.
    for start, end, replacement in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        text = text[:start] + replacement + text[end:]
    return text.encode("utf-8")


def prepare(baseline, candidate_raw, fields):
    old_doc, candidate_doc = decode_document(baseline), decode_document(candidate_raw)
    old, candidate = old_doc.data, candidate_doc.data
    old_revision = revision(old, "baseline")
    revision(candidate, "candidate")  # validate only; candidate versions never drive writes
    top, children = selections(fields, old, candidate)
    validate_changes(old, candidate, top, children)
    protect_tasks(old, candidate)
    changed = not equal({k: v for k, v in old.items() if k != "_revision"},
                        {k: v for k, v in candidate.items() if k != "_revision"})
    if not changed and "_revision" in old:
        return None, old_revision
    new_revision = max(time.time_ns() // 1_000_000, old_revision + 1)
    require(1 <= new_revision <= MAX_SAFE_INTEGER, "new _revision exceeds the safe integer range")
    replacements = {}
    for key in old.keys() | candidate.keys():
        if key in top and not equal(old.get(key, MISSING), candidate[key]):
            member = candidate_doc.members[key]
            replacements[key] = candidate_doc.text[member.start:member.end]
        elif key in children and not equal(old.get(key, MISSING), candidate[key]):
            member = old_doc.members.get(key)
            node = decode_document(old_doc.text[member.start:member.end].encode("utf-8")
                                   if member else b"{}")
            member = candidate_doc.members[key]
            proposed = decode_document(candidate_doc.text[member.start:member.end].encode("utf-8"))
            child_values = {}
            for child in sorted(children[key]):
                if not equal(node.data.get(child, MISSING), proposed.data[child]):
                    span = proposed.members[child]
                    child_values[child] = proposed.text[span.start:span.end]
            replacements[key] = patch_document(node, child_values).decode("utf-8")
    replacements["_revision"] = str(new_revision)
    output = patch_document(old_doc, replacements)
    rendered = decode_document(output).data
    expected = dict(candidate, _revision=new_revision)
    require(equal(rendered, expected), "internal error: patched JSON differs from approved candidate")
    protect_tasks(old, rendered)
    return output, new_revision


def git(repo, *args):
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"  # status must not refresh/write the index
    # Do not let ambient repository/index overrides redirect a -C operation.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(key, None)
    result = subprocess.run(["git", "--no-pager", "-C", str(repo), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                            check=False)
    require(result.returncode == 0,
            "git " + " ".join(args) + " failed: " + result.stderr.decode("utf-8", "replace").strip())
    return result.stdout.strip()


def check_git(repo):
    for flag, label in (("-v", "assume-unchanged"), ("-t", "skip-worktree")):
        for entry in git(repo, "ls-files", flag, "-z").split(b"\0"):
            if not entry:
                continue
            require(len(entry) > 2 and entry[1:2] == b" ", "invalid git ls-files tag record")
            hidden = entry[:1].islower() if flag == "-v" else entry[:1] == b"S"
            require(not hidden, f"tracked {label} flag is forbidden")
    require(git(repo, "status", "--porcelain", "--untracked-files=no") == b"",
            "tracked working tree/index is dirty")
    require(git(repo, "symbolic-ref", "--short", "HEAD") == b"main", "branch must be main")
    require(git(repo, "rev-parse", "--verify", "HEAD") ==
            git(repo, "rev-parse", "--verify", "refs/remotes/origin/main"),
            "HEAD must equal origin/main (no fetch is performed)")
    require(Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel"))).resolve() == repo,
            "--repo must be the repository root")
    require(git(repo, "ls-files", "--error-unmatch", "--", "sync.json") == b"sync.json",
            "sync.json must be a tracked repository-root file")


def read_regular(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), f"not a regular file: {path}")
        return stream.read()


def current_directory():
    return Path.cwd().resolve()


def outside_repository(path, repo, label):
    result = Path(path).resolve(strict=True)
    require(result != repo and repo not in result.parents,
            f"{label} must be outside the repository (including its subdirectories)")
    return result


def candidate_path(path, target):
    raw_path = Path(path).absolute()
    require(not raw_path.is_symlink(), "candidate symlinks are not allowed")
    result = raw_path.resolve(strict=True)
    require(result.parent == current_directory(), "candidate must be directly in the current working directory")
    outside_repository(result, target.parent, "candidate")
    require(not os.path.samefile(result, target), "candidate cannot be production sync.json")
    return result


def check_baseline(target, expected):
    data = read_regular(target)
    require(sha256(data) == expected, "baseline SHA mismatch; stale/concurrent snapshot refused")
    return data


@contextmanager
def exclusive_lock(repo):
    directory = repo / ".git"
    require(directory.is_dir() and not directory.is_symlink(),
            "a real repo/.git directory is required (external Git dirs/worktrees refused)")
    require(Path(os.fsdecode(git(repo, "rev-parse", "--absolute-git-dir"))).resolve() == directory,
            "Git directory must be repo/.git")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(directory / LOCK_NAME, flags, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "lock must be a private regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing releases flock; never unlink the lock


def write_atomic(repo, target, output, baseline_sha):
    staging_directory = outside_repository(current_directory(), repo, "staging directory")
    fd, name = tempfile.mkstemp(prefix="sync-guard-", suffix=".tmp", dir=staging_directory)
    staging = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(target.stat().st_mode))
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        check_git(repo)
        check_baseline(target, baseline_sha)  # last operation before replacement
        os.replace(staging, target)
        directory_fd = os.open(repo, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception as exc:
        state = f"staging retained: {staging}" if staging.exists() else "replacement occurred; verify sync.json durability"
        raise GuardError(f"write failed ({state}): {exc}") from exc


def run_guard(repo_path, candidate, baseline_sha, fields, check_only=False):
    require(re.fullmatch(r"[0-9a-fA-F]{64}", baseline_sha) is not None,
            "--baseline-sha must be a SHA-256 hex digest")
    baseline_sha = baseline_sha.lower()
    repo = Path(repo_path).resolve(strict=True)
    outside_repository(current_directory(), repo, "current working directory")
    target = repo / "sync.json"
    require(not target.is_symlink(), "sync.json symlinks are not allowed")
    baseline = check_baseline(target, baseline_sha)  # frozen production bytes
    check_git(repo)
    candidate_file = candidate_path(candidate, target)
    candidate_raw = read_regular(candidate_file)  # freeze candidate too
    output, new_revision = prepare(baseline, candidate_raw, fields)
    if check_only or output is None:
        check_git(repo)
        check_baseline(target, baseline_sha)
        if output is None:
            return "no-op (check-only)" if check_only else "no-op"
        return f"check-only: would-write _revision={new_revision} sha256={sha256(output)}"
    with exclusive_lock(repo):
        check_baseline(target, baseline_sha)
        check_git(repo)
        # A waiter stamps its revision after acquiring the lock, not before waiting.
        output, new_revision = prepare(baseline, candidate_raw, fields)
        write_atomic(repo, target, output, baseline_sha)
    return f"written: _revision={new_revision} sha256={sha256(output)}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="repository root containing tracked sync.json")
    parser.add_argument("--candidate", required=True, help="candidate JSON directly in cwd")
    parser.add_argument("--baseline-sha", required=True, help="SHA-256 of frozen production sync.json bytes")
    parser.add_argument("--field", action="append", required=True, help="repeatable top-level KEY or YYYY-MM-DD.child")
    parser.add_argument("--check-only", action="store_true", help="validate only; no lock or payload files are created")
    args = parser.parse_args(argv)
    try:
        print(run_guard(args.repo, args.candidate, args.baseline_sha, args.field, args.check_only))
    except (GuardError, OSError, ValueError, RecursionError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
