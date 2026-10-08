#!/usr/bin/env python3
"""Valida los comandos de los laboratorios contra la gcloud CLI instalada localmente.

Qué hace, sin crear ni modificar ningún recurso en Google Cloud:
  1. Revisa la sintaxis bash de cada bloque ```bash con `bash -n`.
  2. Extrae cada invocación de `gcloud` de los archivos */laboratorio.md.
  3. Verifica que el comando exista y que cada --flag aparezca en su `--help`.
  4. Ejecuta cada comando contra un proyecto INEXISTENTE (--project=zz-nonexistent-val-000):
     gcloud valida los argumentos localmente y luego la API responde 403/404, de modo que
     solo los errores de sintaxis o de valores (p. ej. "unrecognized arguments") se reportan.

Los comandos con efectos fuera de un proyecto (gcloud config, compute ssh, sql connect,
logging write, builds submit, functions deploy, storage cp) se omiten en el paso 4.

Uso:
    python3 tools/validate_labs.py            # pasos 1 a 4
    python3 tools/validate_labs.py --no-run   # solo pasos 1 a 3 (sin llamadas a la API)

Requisitos: gcloud CLI con los componentes alpha y beta.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE_PROJECT = "zz-nonexistent-val-000"
SEPS = {"|", "||", "&&", ";", "&", ">", ">>", "<", "(", ")"}
SKIP_RUN = ("config", "compute ssh", "sql connect", "logging write", "builds submit",
            "functions deploy", "storage cp")
ENV = dict(os.environ, PAGER="cat", TERM="dumb", CLOUDSDK_CORE_DISABLE_PROMPTS="1")
ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Valores de ejemplo para las variables de entorno que usan los laboratorios.
P = FAKE_PROJECT
VARS = dict(
    PROJECT_ID=P, PROJECT_NUMBER="123456789012", REGION="us-central1", ZONE="us-central1-a",
    REGION_FRONT="us-central1", ZONE_FRONT="us-central1-a", REGION_BACK="us-east1", ZONE_BACK="us-east1-b",
    SA_EMAIL=f"sa-app-backend@{P}.iam.gserviceaccount.com", USER_EMAIL="someone@example.com",
    ACCOUNT="someone@example.com", BUCKET_NAME=f"gs://{P}-b", BUCKET_AUTORIZADO=f"gs://{P}-a",
    BUCKET_CONFIDENCIAL=f"gs://{P}-c", EVENT_BUCKET=f"gs://{P}-e", FRONTEND_STATIC_IP="34.1.2.3",
    FRONTEND_IP="10.10.1.2", BACKEND_IP="10.20.0.2", IMAGE_URI=f"us-central1-docker.pkg.dev/{P}/r/i:v1",
    CLUSTER_NAME="c1", SQL_INSTANCE="sql-tienda-lab07", ROLE_ID="OperadorBovedaSinBorrado_202601010000",
    SINK_SA="serviceAccount:x@y.iam.gserviceaccount.com", VM_IP="34.1.2.3", ROLE="roles/run.invoker",
    COMPUTE_SA="123456789012-compute@developer.gserviceaccount.com",
    GCS_SERVICE_ACCOUNT="service-1@gs-project-accounts.iam.gserviceaccount.com",
    NODO_INICIAL="nodo-web-abcd", UPTIME_ID=f"projects/{P}/uptimeCheckConfigs/abc",
    CHANNEL_ID=f"projects/{P}/notificationChannels/1", PRIMERA_VERSION=f"gs://{P}-b/o#1",
    NEG="k8s1-x", NEG_ZONE="us-central1-a", B="gcf-v2-x",
)


def bash_blocks(text):
    for m in re.finditer(r"```bash\n(.*?)```", text, re.S):
        yield text[: m.start()].count("\n") + 1, m.group(1)


def tokens(src):
    src = src.replace("\\\n", " ")
    src = re.sub(r"(?m)^\s*#.*$", "", src)
    out, quote = [], None
    for ch in src:  # los saltos de línea fuera de comillas separan comandos
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "\n":
            out.append(" ; ")
            continue
        out.append(ch)
    lex = shlex.shlex("".join(out), posix=True, punctuation_chars=";&|<>()")
    lex.whitespace, lex.whitespace_split = " \t\r", True
    try:
        return list(lex)
    except ValueError:
        return []


def invocations(path):
    text = path.read_text()
    for line, body in bash_blocks(text):
        toks = tokens(body)
        for i, tok in enumerate(toks):
            if tok != "gcloud":
                continue
            rest, cmd = toks[i + 1:], []
            for j, u in enumerate(rest):
                if u in SEPS or u.startswith(")"):
                    break
                if u.isdigit() and j + 1 < len(rest) and rest[j + 1] in (">", ">>"):
                    break  # redirección tipo 2>/dev/null
                cmd.append(u)
            if cmd:
                yield line, cmd


def gcloud(args, timeout=90):
    r = subprocess.run(["gcloud", *args], capture_output=True, text=True, env=ENV,
                       timeout=timeout, stdin=subprocess.DEVNULL)
    return ANSI.sub("", r.stdout + r.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-run", action="store_true", help="no ejecutar comandos contra la API")
    args = ap.parse_args()
    labs = sorted(ROOT.glob("*/laboratorio.md"))
    problems = 0

    print("== 1. Sintaxis bash (bash -n)")
    for f in labs:
        for line, body in bash_blocks(f.read_text()):
            if body.lstrip().startswith(">"):
                continue  # bloque dentro de una nota (> ...), no es bash ejecutable
            r = subprocess.run(["bash", "-n"], input=body, capture_output=True, text=True)
            if r.returncode:
                problems += 1
                print(f"  {f.parent.name}:{line}: {r.stderr.strip()}")

    print("== 2-3. Comandos y flags contra la ayuda de gcloud")
    print("  (generando el árbol de comandos de gcloud, puede tardar un par de minutos...)")
    cmds = set(gcloud(["meta", "list-commands"], timeout=900).split("\n"))
    helps, seen, to_run = {}, set(), []
    for f in labs:
        for line, cmd in invocations(f):
            path = "gcloud"
            for a in cmd:
                if a.startswith("-") or f"{path} {a}" not in cmds:
                    break
                path += f" {a}"
            if path.count(" ") < 2:
                continue  # p. ej. gcloud --version o gcloud config get-value
            flags = sorted({a.split("=")[0] for a in cmd if a.startswith("--")})
            key = (path, tuple(flags))
            if key not in seen:
                seen.add(key)
                if path not in helps:
                    helps[path] = gcloud([*path.split()[1:], "--help"])
                for fl in flags:
                    name = re.escape(fl[2:])
                    pats = [rf"--{name}\b", rf"--\[no-\]{name}\b"]
                    if fl.startswith("--no-"):
                        pats.append(rf"--\[no-\]{re.escape(fl[5:])}\b")
                    if not any(re.search(p, helps[path]) for p in pats):
                        print(f"  AVISO {f.parent.name}:{line}: '{path[7:]}' no documenta {fl} "
                              "(puede ser un flag oculto; el paso 4 confirma si es válido)")
            to_run.append((f.parent.name, line, cmd))

    if args.no_run:
        print(f"== 4. Omitido (--no-run). Problemas: {problems}")
        return 1 if problems else 0

    print(f"== 4. Ejecución contra el proyecto inexistente {FAKE_PROJECT}")
    sub = lambda a: re.sub(r"\$\{?(\w+)\}?", lambda m: VARS.get(m.group(1), "dummy"), a)
    done = set()
    for lab, line, cmd in to_run:
        argv = [sub(a) for a in cmd]
        joined = " ".join(argv)
        if joined.startswith(SKIP_RUN) or joined in done:
            continue
        done.add(joined)
        if not any(a.startswith("--project") for a in argv):
            argv.append(f"--project={FAKE_PROJECT}")
        out = gcloud(argv)
        first = next((l for l in out.splitlines() if "ERROR" in l), "")
        # Un rol predefinido (roles/...) no admite --project: falso positivo del propio validador.
        if "only stands for predefined role" in first:
            continue
        if re.search(r"unrecognized arguments|argument --|Invalid value|invalid choice|"
                     r"Bad syntax|must be an integer|expected one argument", first):
            problems += 1
            print(f"  {lab}:{line}: gcloud {' '.join(cmd)[:80]}\n      -> {first.strip()[:200]}")
    print(f"== Resultado: {len(done)} comandos ejecutados, problemas encontrados: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
