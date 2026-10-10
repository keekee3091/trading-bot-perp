"""Pousse la branche courante vers origin APRES un scan de secrets sur ce qui partirait (commits non poussés + index).

Usage: python tools/git_sync.py [--dry-run] [--selftest]
Refuse (code 2) si une ligne ajoutée contient un secret probable ou si un fichier interdit est suivi. Ne commit rien (le commit
reste fait par l'auteur du changement) et ne force jamais. stdlib uniquement. Copie identique dans scripts/ du bot de juin.
"""
import os
import re
import subprocess
import sys

# Motifs de secrets probables dans les lignes AJOUTÉES. Les adresses publiques 0x + 40 hex sont tolérées (publiques sur la chaîne).
PATTERNS = {
    "bloc de clé privée": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    "clé hex de 64 caractères": re.compile(r"\b(?:0x)?[0-9a-fA-F]{64}\b"),
    "affectation de secret": re.compile(r"(?i)(private_key|api_secret|api_passphrase|passphrase|secret|password|token|api_key)\w*\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{16,}"),
    "adresse e-mail personnelle": re.compile(r"[\w.+-]+@(gmail|outlook|hotmail|yahoo|proton)\.[a-z]{2,}", re.I),
}
FORBIDDEN_FILES = re.compile(r"(^|/)(\.env(?!\.(example|sample|template)$)(\..*)?|.*\.pem|id_rsa.*)$")
# Lignes qui MENTIONNENT un motif sans le contenir (tests de non-fuite, exemples de noms de variables sans valeur)
ALLOW = re.compile(r"(\"@gmail\"|'@gmail'|TIINGO_API_KEY\s*$|SEC_USER_AGENT\s*$)")


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")


def scan_lines(lines):
    """[(motif, extrait masqué)] pour les lignes ajoutées suspectes."""
    out = []
    for line in lines:
        if ALLOW.search(line):
            continue
        for name, pat in PATTERNS.items():
            m = pat.search(line)
            if m:
                out.append((name, re.sub(r"[A-Za-z0-9_\-/+=]{6,}", lambda x: x.group(0)[:3] + "***", line.strip())[:100]))
    return out


def added_lines(diff_text):
    return [l[1:] for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++")]


def selftest():
    fake_key = "0x" + "ab12" * 16                               # construit à l'exécution, pas un vrai secret
    assert scan_lines([f"key = {fake_key}"]), "clé hex non détectée"
    assert scan_lines(["POLY_API_SECRET=" + "Zk3_" * 6]), "affectation non détectée"
    assert scan_lines(["contact: " + "jean.dupont" + "@gmail.com"]), "e-mail non détecté"
    assert not scan_lines(["wallet = 0x" + "1" * 40]), "adresse publique à tolérer"
    assert not scan_lines(['for bad in ("@gmail", "x"):']), "ligne de test à tolérer"
    assert FORBIDDEN_FILES.search(".env") and FORBIDDEN_FILES.search("a/b/.env.local") and not FORBIDDEN_FILES.search("docs/env.md")
    assert not FORBIDDEN_FILES.search(".env.example"), "le modèle versionné est autorisé"
    print("selftest ok")


def main():
    if "--selftest" in sys.argv:
        return selftest()
    dry = "--dry-run" in sys.argv
    if run("git", "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        sys.exit("pas un dépôt git")
    branch = run("git", "branch", "--show-current").stdout.strip()
    up = run("git", "rev-parse", "--abbrev-ref", "@{u}")
    rng = "@{u}..HEAD" if up.returncode == 0 else "HEAD"
    diff = run("git", "log", "-p", "--format=", rng).stdout + run("git", "diff", "--cached").stdout
    bad_files = [f for f in run("git", "ls-files").stdout.splitlines() if FORBIDDEN_FILES.search(f)]
    hits = scan_lines(added_lines(diff))
    if bad_files or hits:
        print("REFUS : secrets probables, rien n'est poussé.")
        for f in bad_files:
            print("  fichier interdit suivi :", f)
        for name, ex in hits[:10]:
            print(f"  {name} : {ex}")
        sys.exit(2)
    n = len(run("git", "log", "--oneline", rng).stdout.splitlines())
    print(f"scan propre, {n} commit(s) à pousser sur {branch}")
    if dry or n == 0:
        return
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    p = subprocess.run(["git", "push", "origin", "HEAD"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((p.stdout + p.stderr).strip()[-400:])
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
