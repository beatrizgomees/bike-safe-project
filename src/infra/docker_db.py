"""Deixa a infraestrutura pronta (PostgreSQL + Mosquitto) sem você digitar Docker.

preparar_infra():
  1. confere se o Docker está instalado e rodando;
  2. sobe `postgres` e `mosquitto` do docker-compose e espera ficarem saudáveis;
  3. aplica o schema (idempotente: pode rodar sempre);
  4. aponta POSTGRES_HOST/PORT e MQTT_HOST/PORT para o seu PC.

Dentro do container do compose (serviço `app`) não faz nada: tudo já está lá.
"""
import os
import subprocess
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pip install python-dotenv
    load_dotenv = None

RAIZ = Path(__file__).resolve().parents[2]

# onde procurar o script de schema (o primeiro que existir)
CANDIDATOS_SCHEMA = ["sql/schema.sql", "src/utils/init.sql", "init.sql"]


def em_docker():
    return Path("/.dockerenv").exists() or os.getenv("IN_DOCKER") == "1"


def _docker(*args, entrada=None, capturar=True):
    return subprocess.run(
        ["docker", *args],
        cwd=RAIZ,
        input=entrada,
        capture_output=capturar,
    )


def _texto(resultado):
    saida = (resultado.stdout or b"") + (resultado.stderr or b"")

    return saida.decode("utf-8", errors="replace").strip()


def achar_schema():
    for caminho in CANDIDATOS_SCHEMA:
        arquivo = RAIZ / caminho

        if arquivo.is_file():
            return arquivo

    raise FileNotFoundError(
        "Script de schema não encontrado. Procurei em: " + ", ".join(CANDIDATOS_SCHEMA)
    )


def preparar_infra():
    if em_docker():
        return

    if load_dotenv:
        load_dotenv(RAIZ / ".env", encoding="utf-8-sig")

    try:
        info = _docker("info")
    except FileNotFoundError:
        raise RuntimeError(
            "Docker não encontrado. Instale o Docker Desktop e reabra o VS Code."
        )

    if info.returncode != 0:
        raise RuntimeError(
            "O Docker não está rodando. Abra o Docker Desktop, espere ele iniciar "
            "e execute de novo."
        )

    print("Subindo PostgreSQL e Mosquitto (docker compose)...")

    # sem capturar a saída: na primeira vez baixa a imagem e você vê o progresso
    subida = _docker("compose", "up", "-d", "--wait", "postgres", "mosquitto", capturar=False)

    if subida.returncode != 0:
        raise RuntimeError(
            "Não consegui subir os serviços. Veja a mensagem acima. Causas comuns: "
            "porta 5432 ou 1883 ocupada (pare o container antigo ou defina "
            "POSTGRES_PUBLISH_PORT / MQTT_PUBLISH_PORT no .env) ou POSTGRES_PASSWORD "
            "ausente no .env."
        )

    schema = achar_schema()
    usuario = os.getenv("POSTGRES_USER", "admin")

    print(f"Aplicando o schema ({schema.relative_to(RAIZ)})...")

    # -d postgres: o próprio script cria o banco bikesafe se faltar e conecta nele
    aplicado = _docker(
        "compose", "exec", "-T", "postgres",
        "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", usuario, "-d", "postgres",
        entrada=schema.read_bytes(),
    )

    if aplicado.returncode != 0:
        raise RuntimeError("Erro ao aplicar o schema:\n" + _texto(aplicado))

    # o programa roda no seu PC: conecta no banco pela porta publicada
    os.environ["POSTGRES_HOST"] = "localhost"
    os.environ["POSTGRES_PORT"] = os.getenv("POSTGRES_PUBLISH_PORT", "5432")
    os.environ["MQTT_HOST"] = "localhost"
    os.environ["MQTT_PORT"] = os.getenv("MQTT_PUBLISH_PORT", "1883")

    print("Infraestrutura pronta.\n")