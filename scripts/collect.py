#!/usr/bin/env python3
"""projects_root 아래의 git 저장소(exclude 제외)에서 마지막 확인 이후의 커밋을 모아 JSON으로 출력한다.

사용법:
  python3 scripts/collect.py          # 새 커밋 출력 (상태는 바꾸지 않음)
  python3 scripts/collect.py --save   # 각 저장소의 현재 HEAD를 확인 지점으로 저장
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
STATE = ROOT / "state.json"

SEEN = ROOT / ".collect_seen.json"  # 수집 때 본 HEAD. --save가 이것을 저장해 그 사이 커밋을 놓치지 않는다

DOC_SUFFIXES = (".md", ".mdx", ".txt")
MAX_DOC_DIFF_CHARS = 12000
MAX_FILES = 60


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def discover(root, exclude):
    """projects_root 바로 아래의 git 저장소 이름들. 실행할 때마다 새로 찾는다."""
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and (p / ".git").exists() and p.name not in exclude)


def visibility(repo):
    """공개 여부: public / private / no-remote / unknown. 공개 저장소만 링크 주소를 준다."""
    r = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True)
    url = r.stdout.strip()
    if r.returncode != 0 or not url:
        return {"visibility": "no-remote", "repo_url": ""}
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        return {"visibility": "unknown", "repo_url": ""}
    gh = subprocess.run(["gh", "repo", "view", m.group(1), "--json", "visibility", "-q", ".visibility"],
                        capture_output=True, text=True)
    vis = gh.stdout.strip().lower() if gh.returncode == 0 else ""
    if vis not in ("public", "private", "internal"):
        return {"visibility": "unknown", "repo_url": ""}
    return {"visibility": vis, "repo_url": f"https://github.com/{m.group(1)}" if vis == "public" else ""}


def commit_range(repo, entry, cfg):
    """새 커밋을 고를 git log 인자. 이전 확인 지점이 사라졌으면 날짜로 대신한다."""
    last = entry.get("last")
    if last:
        r = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", last, "HEAD"],
                           capture_output=True)
        if r.returncode == 0:
            return [f"{last}..HEAD"]
        return [f"--since={entry.get('checked_at', cfg['first_run_since'])}", "HEAD"]
    return [f"--since={cfg['first_run_since']}", "HEAD"]


def collect_repo(repo, entry, cfg):
    rng = commit_range(repo, entry, cfg)
    out = git(repo, "log", "--no-merges", f"-n{cfg['max_commits_per_repo']}",
              "--format=%H%x1f%cI%x1f%s%x1f%b%x1e", *rng)
    commits = []
    for record in out.split("\x1e"):
        if "\x1f" not in record:
            continue
        h, date, subject, body = record.strip().split("\x1f", 3)
        commits.append({
            "hash": h[:10],
            "date": date,
            "subject": subject,
            "body": "\n".join(l for l in body.strip().splitlines() if not l.startswith("Co-Authored-By:")).strip(),
            "stat": git(repo, "show", "--shortstat", "--format=", h).strip(),
        })
    if not commits:
        return None

    # 가장 오래된 새 커밋의 부모부터 HEAD까지 비교한다. 첫 커밋이면 빈 트리와 비교한다.
    parents = git(repo, "rev-list", "--parents", "-n1", commits[-1]["hash"]).split()
    diff_base = parents[1] if len(parents) > 1 else git(repo, "hash-object", "-t", "tree", "/dev/null").strip()
    files = git(repo, "diff", "--stat=120", diff_base, "HEAD").strip().splitlines()
    if len(files) > MAX_FILES:
        files = files[:MAX_FILES - 1] + [f"... (파일 {len(files) - MAX_FILES} 개 생략)", files[-1]]
    doc_files = [f for f in git(repo, "diff", "--name-only", diff_base, "HEAD").split() if f.endswith(DOC_SUFFIXES)]
    doc_diff = git(repo, "diff", diff_base, "HEAD", "--", *doc_files) if doc_files else ""

    readme = repo / "README.md"
    return {
        "repo": repo.name,
        "commit_count": len(commits),
        "commits": commits,
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "files_changed": files,
        "doc_diff": doc_diff[:MAX_DOC_DIFF_CHARS],
        "doc_diff_truncated": len(doc_diff) > MAX_DOC_DIFF_CHARS,
        "readme_head": readme.read_text()[:1500] if readme.exists() else "",
    }


def main():
    cfg = load_json(CONFIG, None)
    state = load_json(STATE, {})
    root = (ROOT / cfg["projects_root"]).resolve()  # 상대 경로는 이 저장소 기준
    save = "--save" in sys.argv[1:]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    seen = load_json(SEEN, {})
    results, errors = [], []
    # --save는 수집 때 본 저장소만 저장한다. 그 사이 새로 생긴 저장소는 다음 수집 때 처음부터 본다.
    names = list(seen) if save and seen else discover(root, cfg.get("exclude", []))
    for name in names:
        repo = root / name
        try:
            if save:
                head = seen.get(name) or git(repo, "rev-parse", "HEAD").strip()
                state[name] = {"last": head, "checked_at": now}
            else:
                seen[name] = git(repo, "rev-parse", "HEAD").strip()
                r = collect_repo(repo, state.get(name, {}), cfg)
                if r:
                    r.update(visibility(repo))
                    results.append(r)
        except (RuntimeError, FileNotFoundError) as e:
            errors.append({"repo": name, "error": str(e)})

    if save:
        STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
        SEEN.unlink(missing_ok=True)
        print(json.dumps({"saved": list(state), "errors": errors}, ensure_ascii=False))
    else:
        SEEN.write_text(json.dumps(seen, indent=2) + "\n")
        print(json.dumps({"collected_at": now, "repos": results, "errors": errors}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
