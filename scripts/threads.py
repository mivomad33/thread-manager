#!/usr/bin/env python3
"""Threads 공식 API로 글을 올리고 토큰을 관리한다.

사용법:
  python3 scripts/threads.py whoami              # 토큰 확인 (계정 이름 출력)
  python3 scripts/threads.py quota               # 24시간 게시 한도 사용량
  python3 scripts/threads.py exchange <단기토큰>  # 단기 토큰 → 60일 장기 토큰, .env에 저장
  python3 scripts/threads.py refresh             # 장기 토큰 갱신 (발급 후 24시간 이상 지나야 함)
  python3 scripts/threads.py check <초안.md>      # 초안 형식과 글자 수만 검사
  python3 scripts/threads.py post <초안.md>       # 승인된(status: approved) 초안을 올림

.env 항목: THREADS_ACCESS_TOKEN, THREADS_APP_SECRET, THREADS_TOKEN_ISSUED_AT

초안의 `images: a.png,b.png`(drafts/images/ 기준)는 첫 조각에 붙는다. 1장이면 이미지 글,
2장 이상이면 캐러셀. 게시할 때 config.json의 images_repo(공개 GitHub 저장소)에 올린 뒤 그 주소를 넘긴다.
"""
import base64
import json
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
POSTS_LOG = ROOT / "posts.log"
IMAGES_DIR = ROOT / "drafts" / "images"
CONFIG = ROOT / "config.json"
API = "https://graph.threads.com"
VERSION = "v1.0"
MAX_CHARS = 500
PUBLISH_WAIT_SECONDS = 30  # 문서 권장: 컨테이너 생성 후 평균 30초 기다린 뒤 게시
REFRESH_AFTER_DAYS = 30
REQUIRED_META = ("status", "repos", "visibility", "commits", "created", "reason")
LEAK_PATTERNS = ("/Users/", "THREADS_", "access_token", "sk-ant-", "BEGIN PRIVATE KEY")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES = 20
STATUS_TIMEOUT_SECONDS = 300


# ---------- .env ----------

def read_env():
    env = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def write_env(updates):
    env = read_env()
    env.update(updates)
    ENV.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    ENV.chmod(0o600)


def token():
    t = read_env().get("THREADS_ACCESS_TOKEN")
    if not t:
        sys.exit("THREADS_ACCESS_TOKEN이 .env에 없습니다. DEVELOPMENT.md의 토큰 발급 절차를 먼저 진행하세요.")
    return t


# ---------- HTTP ----------

def call(method, path, params):
    url = f"{API}/{path}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"Threads API 오류 {e.code} ({path}): {body}")


# ---------- 토큰 ----------

def exchange(short_token):
    secret = read_env().get("THREADS_APP_SECRET")
    if not secret:
        sys.exit("THREADS_APP_SECRET이 .env에 없습니다.")
    r = call("GET", "access_token", {"grant_type": "th_exchange_token",
                                     "client_secret": secret, "access_token": short_token})
    save_token(r)


def refresh():
    r = call("GET", "refresh_access_token", {"grant_type": "th_refresh_token", "access_token": token()})
    save_token(r)


def save_token(r):
    write_env({"THREADS_ACCESS_TOKEN": r["access_token"],
               "THREADS_TOKEN_ISSUED_AT": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print(f"토큰 저장 완료 (유효 {int(r.get('expires_in', 0)) // 86400}일)")


def refresh_if_old():
    issued = read_env().get("THREADS_TOKEN_ISSUED_AT")
    if issued:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(issued)
        if age.days >= REFRESH_AFTER_DAYS:
            refresh()


# ---------- 초안 ----------

def threads_len(text):
    """Threads 글자 수. 이모지는 UTF-8 바이트 수로 센다(공식 문서 기준)."""
    return sum(len(c.encode()) if unicodedata.category(c) == "So" or ord(c) > 0xFFFF else 1 for c in text)


def parse_draft(path):
    """frontmatter(--- 사이의 key: value)와, '---' 줄로 나뉜 본문 조각들을 돌려준다."""
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        sys.exit(f"{path}: frontmatter가 없습니다.")
    end = lines.index("---", 1)
    meta = {}
    for line in lines[1:end]:
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    parts, cur = [], []
    for line in lines[end + 1:]:
        if line.strip() == "---":
            parts.append("\n".join(cur).strip())
            cur = []
        else:
            cur.append(line)
    parts.append("\n".join(cur).strip())
    return meta, [p for p in parts if p]


def set_meta(path, updates):
    lines = Path(path).read_text().splitlines()
    end = lines.index("---", 1)
    head = lines[1:end]
    for k, v in updates.items():
        for i, line in enumerate(head):
            if line.split(":", 1)[0].strip() == k:
                head[i] = f"{k}: {v}"
                break
        else:
            head.append(f"{k}: {v}")
    Path(path).write_text("\n".join(["---", *head, *lines[end:]]) + "\n")


def draft_images(meta):
    return [IMAGES_DIR / n.strip() for n in meta.get("images", "").split(",") if n.strip()]


def check(path):
    meta, parts = parse_draft(path)
    if not parts:
        sys.exit(f"{path}: 본문이 비어 있습니다.")
    missing = [k for k in REQUIRED_META if not meta.get(k)]
    if missing:
        sys.exit(f"{path}: frontmatter에 빠진 항목이 있습니다: {missing}")
    leaks = [w for w in LEAK_PATTERNS if any(w in p for p in parts)]
    if leaks:
        sys.exit(f"{path}: 본문에 들어가면 안 되는 문자열이 있습니다: {leaks}")
    over = [(i + 1, threads_len(p)) for i, p in enumerate(parts) if threads_len(p) > MAX_CHARS]
    if over:
        sys.exit(f"{path}: {MAX_CHARS}자를 넘는 조각이 있습니다: {over}")
    images = draft_images(meta)
    bad = [f"{i.name}: 없음" for i in images if not i.exists()]
    bad += [f"{i.name}: PNG/JPEG만 가능" for i in images if i.suffix.lower() not in IMAGE_SUFFIXES]
    bad += [f"{i.name}: 8MB 초과" for i in images if i.exists() and i.stat().st_size > MAX_IMAGE_BYTES]
    if len(images) > MAX_IMAGES:
        bad.append(f"이미지는 {MAX_IMAGES}장까지")
    if bad:
        sys.exit(f"{path}: 이미지 문제: {bad}")
    print(f"OK: 조각 {len(parts)}개, 글자 수 {[threads_len(p) for p in parts]}, 이미지 {len(images)}장, status={meta.get('status')}")
    return meta, parts


# ---------- 이미지 업로드 ----------

def upload_image(local, dest):
    """공개 이미지 저장소에 파일을 올리고, Threads가 가져갈 공개 주소를 돌려준다."""
    repo = json.loads(CONFIG.read_text())["images_repo"]
    body = json.dumps({"message": f"Add {dest}", "content": base64.b64encode(local.read_bytes()).decode()})
    r = subprocess.run(["gh", "api", "-X", "PUT", f"repos/{repo}/contents/{dest}", "--input", "-"],
                       input=body, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"이미지 업로드 실패 ({dest}): {r.stderr.strip() or r.stdout.strip()}")
    url = f"https://raw.githubusercontent.com/{repo}/main/{urllib.parse.quote(dest)}"
    for _ in range(30):  # 올린 직후에는 잠깐 404가 날 수 있다
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20):
                return url
        except urllib.error.URLError:
            time.sleep(2)
    sys.exit(f"올린 이미지를 공개 주소에서 열 수 없습니다: {url}")


def upload_images(path, images):
    stem = Path(path).stem
    month = datetime.now().strftime("%Y/%m")
    return [upload_image(img, f"{month}/{stem}/{i + 1:02d}-{img.name}") for i, img in enumerate(images)]


# ---------- 게시 ----------

def create_container(params):
    return call("POST", f"{VERSION}/me/threads", {**params, "access_token": token()})["id"]


def wait_until_ready(container):
    """컨테이너 처리가 끝날 때까지 기다린다. 상태 조회가 안 되면 문서 권장대로 30초 기다린다."""
    deadline = time.time() + STATUS_TIMEOUT_SECONDS
    while time.time() < deadline:
        time.sleep(5)
        try:
            with urllib.request.urlopen(f"{API}/{VERSION}/{container}?" + urllib.parse.urlencode(
                    {"fields": "status,error_message", "access_token": token()}), timeout=30) as r:
                st = json.loads(r.read())
        except urllib.error.URLError:
            time.sleep(PUBLISH_WAIT_SECONDS)
            return
        if st.get("status") == "FINISHED":
            return
        if st.get("status") in ("ERROR", "EXPIRED"):
            sys.exit(f"Threads가 컨테이너를 처리하지 못했습니다: {st}")
    sys.exit(f"컨테이너 처리가 {STATUS_TIMEOUT_SECONDS}초 안에 끝나지 않았습니다: {container}")


def publish(text, reply_to=None, image_urls=()):
    """조각 하나를 올린다. 이미지 0장이면 글, 1장이면 이미지 글, 2장 이상이면 캐러셀."""
    params = {"text": text}
    if reply_to:
        params["reply_to_id"] = reply_to
    if not image_urls:
        container = create_container({**params, "media_type": "TEXT"})
    elif len(image_urls) == 1:
        container = create_container({**params, "media_type": "IMAGE", "image_url": image_urls[0]})
    else:
        children = []
        for url in image_urls:
            child = create_container({"media_type": "IMAGE", "image_url": url, "is_carousel_item": "true"})
            wait_until_ready(child)
            children.append(child)
        container = create_container({**params, "media_type": "CAROUSEL", "children": ",".join(children)})
    wait_until_ready(container)
    return call("POST", f"{VERSION}/me/threads_publish",
                {"creation_id": container, "access_token": token()})["id"]


def post(path):
    meta, parts = check(path)
    if meta.get("status") != "approved":
        sys.exit(f"{path}: status가 approved가 아닙니다 ({meta.get('status')}). 승인된 초안만 올립니다.")
    refresh_if_old()

    image_urls = meta.get("image_urls", "").split(",") if meta.get("image_urls") else []
    images = draft_images(meta)
    if images and not image_urls:
        image_urls = upload_images(path, images)
        set_meta(path, {"image_urls": ",".join(image_urls)})  # 게시가 실패해도 다시 올리지 않게 남긴다

    ids = []
    for i, text in enumerate(parts):
        ids.append(publish(text, reply_to=ids[-1] if ids else None, image_urls=image_urls if i == 0 else ()))
    permalink = call("GET", f"{VERSION}/{ids[0]}", {"fields": "permalink", "access_token": token()}).get("permalink", "")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    set_meta(path, {"status": "posted", "posted_at": now, "post_ids": ",".join(ids), "permalink": permalink})
    with POSTS_LOG.open("a") as f:
        f.write(json.dumps({"draft": Path(path).name, "posted_at": now, "ids": ids, "permalink": permalink,
                            "repos": meta.get("repos", ""), "images": image_urls, "text": parts[0]},
                           ensure_ascii=False) + "\n")
    print(f"게시 완료: {permalink or ids[0]}")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "whoami":
        print(call("GET", f"{VERSION}/me", {"fields": "id,username", "access_token": token()}))
    elif cmd == "quota":
        print(call("GET", f"{VERSION}/me/threads_publishing_limit",
                   {"fields": "quota_usage,config", "access_token": token()}))
    elif cmd == "exchange" and args:
        exchange(args[0])
    elif cmd == "refresh":
        refresh()
    elif cmd == "check" and args:
        check(args[0])
    elif cmd == "post" and args:
        post(args[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
