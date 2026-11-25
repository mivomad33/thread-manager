#!/usr/bin/env python3
"""GitHub 계정(github_owner)의 저장소(보관·fork·exclude 제외)에서 마지막 확인 이후의 커밋을 모아 JSON으로 출력한다.

저장소 목록은 실행할 때마다 gh로 새로 받는다. 저장소마다 repos/<이름>에 clone을 두고
기본 브랜치를 받아 와 그 브랜치의 커밋만 본다. clone은 읽기 전용 사본이다.

사용법:
  python3 scripts/collect.py          # 새 커밋 출력 (상태는 바꾸지 않음)
  python3 scripts/collect.py --save   # 직전 수집 때 본 기본 브랜치 끝을 확인 지점으로 저장
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
STATE = ROOT / "state.json"

SEEN = ROOT / ".collect_seen.json"  # 수집 때 본 브랜치 끝. --save가 이것을 저장해 그 사이 커밋을 놓치지 않는다
CLONES = ROOT / "repos"

DOC_SUFFIXES = (".md", ".mdx", ".txt")
MAX_DOC_DIFF_CHARS = 12000
MAX_FILES = 60


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def empty_tree(repo):
    """빈 트리의 해시. /dev/null 없이 구해 윈도우에서도 같게 동작한다."""
    r = subprocess.run(["git", "-C", str(repo), "hash-object", "-t", "tree", "--stdin"],
                       input="", capture_output=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def discover(owner, exclude):
    """owner의 저장소 목록. 보관된 저장소, fork, 빈 저장소, exclude는 뺀다. 실행할 때마다 새로 받는다."""
    r = subprocess.run(["gh", "repo", "list", owner, "--limit", "1000", "--no-archived", "--source",
                        "--json", "name,visibility,defaultBranchRef,isEmpty,url"], capture_output=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"gh repo list 실패: {r.stderr.strip()}")
    listed = json.loads(r.stdout)
    if not listed:
        raise RuntimeError(f"{owner} 계정에서 저장소를 찾지 못했습니다. config.json의 github_owner를 확인하세요.")
    repos = []
    for x in listed:
        branch = (x.get("defaultBranchRef") or {}).get("name")
        if x["name"] in exclude or x.get("isEmpty") or not branch:
            continue
        vis = (x.get("visibility") or "").lower() or "unknown"
        repos.append({"name": x["name"], "branch": branch, "visibility": vis,
                      "repo_url": x["url"] if vis == "public" else ""})
    return sorted(repos, key=lambda x: x["name"])


def sync(owner, info):
    """repos/<이름>을 기본 브랜치의 최신 상태로 맞추고 그 브랜치의 ref를 돌려준다."""
    path = CLONES / info["name"]
    url = f"https://github.com/{owner}/{info['name']}.git"
    if not (path / ".git").exists():
        CLONES.mkdir(exist_ok=True)
        r = subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", url, str(path)],
                           capture_output=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"clone 실패: {r.stderr.strip()}")
    git(path, "fetch", "--quiet", "--prune", "origin")
    ref = f"refs/remotes/origin/{info['branch']}"
    # 파일을 읽을 수 있게 기본 브랜치를 펼쳐 둔다. 이 clone은 사본이라, 실행 중 생긴 변경은 덮어쓴다.
    git(path, "checkout", "--quiet", "--force", "--detach", ref)
    return path, ref


def commit_range(repo, ref, entry, cfg):
    """새 커밋을 고를 git log 인자. 이전 확인 지점이 사라졌으면 날짜로 대신한다."""
    last = entry.get("last")
    if last:
        r = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", last, ref],
                           capture_output=True)
        if r.returncode == 0:
            return [f"{last}..{ref}"]
        return [f"--since={entry.get('checked_at', cfg['first_run_since'])}", ref]
    return [f"--since={cfg['first_run_since']}", ref]


def collect_repo(repo, ref, entry, cfg):
    rng = commit_range(repo, ref, entry, cfg)
    out = git(repo, "log", "--no-merges", f"-n{cfg['max_commits_per_repo']}",
              "--format=%H%x1f%cI%x1f%s%x1f%b%x1e", *rng)
    commits = []
    for record in out.split("\x1e"):
        if "\x1f" not in record:
            continue
        h, date, subject, body = record.strip("\n").split("\x1f", 3)  # strip()은 \x1f도 공백으로 지운다
        commits.append({
            "hash": h[:10],
            "date": date,
            "subject": subject,
            "body": "\n".join(l for l in body.strip().splitlines() if not l.startswith("Co-Authored-By:")).strip(),
            "stat": git(repo, "show", "--shortstat", "--format=", h).strip(),
        })
    if not commits:
        return None

    # 가장 오래된 새 커밋의 부모부터 기본 브랜치 끝까지 비교한다. 첫 커밋이면 빈 트리와 비교한다.
    parents = git(repo, "rev-list", "--parents", "-n1", commits[-1]["hash"]).split()
    diff_base = parents[1] if len(parents) > 1 else empty_tree(repo)
    files = git(repo, "diff", "--stat=120", diff_base, ref).strip().splitlines()
    if len(files) > MAX_FILES:
        files = files[:MAX_FILES - 1] + [f"... (파일 {len(files) - MAX_FILES} 개 생략)", files[-1]]
    doc_files = [f for f in git(repo, "diff", "--name-only", diff_base, ref).split() if f.endswith(DOC_SUFFIXES)]
    doc_diff = git(repo, "diff", diff_base, ref, "--", *doc_files) if doc_files else ""

    readme = repo / "README.md"
    return {
        "repo": repo.name,
        "commit_count": len(commits),
        "commits": commits,
        "head": git(repo, "rev-parse", ref).strip(),
        "files_changed": files,
        "doc_diff": doc_diff[:MAX_DOC_DIFF_CHARS],
        "doc_diff_truncated": len(doc_diff) > MAX_DOC_DIFF_CHARS,
        "readme_head": readme.read_text(encoding="utf-8", errors="replace")[:1500] if readme.exists() else "",
    }


def main():
    for stream in (sys.stdout, sys.stderr):  # 윈도우 기본 인코딩(cp949)이 아니라 UTF-8로 출력한다
        stream.reconfigure(encoding="utf-8")
    cfg = load_json(CONFIG, None)
    state = load_json(STATE, {})
    owner = cfg["github_owner"]
    save = "--save" in sys.argv[1:]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if save:
        # 수집 때 본 브랜치 끝만 저장한다. 그 사이 생긴 커밋과 저장소는 다음 수집 때 본다.
        seen = load_json(SEEN, None)
        if seen is None:
            sys.exit("저장할 수집 결과가 없습니다. 먼저 python3 scripts/collect.py를 실행하세요.")
        for name, head in seen.items():
            state[name] = {"last": head, "checked_at": now}
        STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        SEEN.unlink()
        print(json.dumps({"saved": list(seen), "errors": []}, ensure_ascii=False))
        return

    seen, results, errors = {}, [], []
    try:
        repos = discover(owner, cfg.get("exclude", []))
    except RuntimeError as e:
        repos, errors = [], [{"repo": "*", "error": str(e)}]
    for info in repos:
        name = info["name"]
        try:
            repo, ref = sync(owner, info)
            seen[name] = git(repo, "rev-parse", ref).strip()
            r = collect_repo(repo, ref, state.get(name, {}), cfg)
            if r:
                r.update({"branch": info["branch"], "path": f"repos/{name}",
                          "visibility": info["visibility"], "repo_url": info["repo_url"]})
                results.append(r)
        except (RuntimeError, FileNotFoundError) as e:
            errors.append({"repo": name, "error": str(e)})

    SEEN.write_text(json.dumps(seen, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"collected_at": now, "repos": results, "errors": errors}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
