"""Orquestrador: sobe a infraestrutura e roda a arquitetura inteira.

    Bases (A, E, C) -> SV --MQTT--> MP --> Banco
                          \\--MQTT--> Middleware --MQTT--> Dashboard / Mobile

Cada componente é um processo separado (como seria em produção); este arquivo
só liga tudo para você clicar em executar. Para rodar um componente sozinho:
    python -m src.processing.modulo_processamento
    python -m src.middleware.middleware
    python -m src.sensor.sensor_virtual
"""
import subprocess
import sys
import time

from src.infra.docker_db import RAIZ, preparar_infra

# ---------------------------------------------------------------- ajustes
LIMITE_CRUZAMENTO = None   # acidentes com bike geocodificados/cruzados. None = todos.
LIMITE_EVENTOS = None      # acidentes transmitidos em "tempo real" ao Middleware.
INTERVALO_S = 2.0        # segundos entre um evento e outro.
# -----------------------------------------------------------------------


def iniciar_processo(modulo):
    return subprocess.Popen([sys.executable, "-m", modulo], cwd=RAIZ)


def main():
    preparar_infra()

    # imports depois do preparar_infra: ele ajusta as variáveis de conexão
    from src.sensor.sensor_virtual import SensorVirtual

    processos = [
        iniciar_processo("src.processing.modulo_processamento"),   # MP
        iniciar_processo("src.middleware.middleware"),             # Middleware
    ]

    sv = SensorVirtual.padrao()

    try:
        sv.iniciar()
        sv.mqtt.aguardar_online(["mp", "middleware"])

        # 1) SV -> MP: bases completas; o MP cruza e grava no banco
        resposta = sv.publicar_bases(limite_cruzamento=LIMITE_CRUZAMENTO)

        if "erro" in resposta:
            raise RuntimeError(f"O MP falhou: {resposta['erro']}")

        print("\nMP concluiu:", resposta["resumo"], "\n")

        # 2) SV -> Middleware: acidentes em fluxo, como se fossem de agora
        sv.transmitir_acidentes(limite=LIMITE_EVENTOS, intervalo_s=INTERVALO_S)
        time.sleep(3)   # deixa o Middleware repassar o último evento antes de encerrar

    finally:
        sv.parar()

        for p in processos:
            p.terminate()

        for p in processos:
            p.wait(timeout=10)


if __name__ == "__main__":
    main()