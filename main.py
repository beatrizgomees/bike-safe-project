"""Orquestrador: sobe a infraestrutura e roda a arquitetura inteira.

    Bases (A, E, C) -> SV --MQTT--> Broker --> MP --> Banco --> API --> Dashboard / Mobile
                                              \\--MQTT (app/*)--------> Dashboard / Mobile

O Broker (Mosquitto, no Docker) é o middleware: SV e MP só falam com ele.
Cada componente é um processo separado; este arquivo só liga tudo para você clicar
em executar. Para rodar um componente sozinho:
    python -m src.processing.modulo_processamento
    python -m src.api.api
    python -m src.sensor.sensor_virtual
"""
import os
import subprocess
import sys
import time

from src.infra.docker_db import RAIZ, preparar_infra

# ---------------------------------------------------------------- ajustes
LIMITE_CRUZAMENTO = 50   # acidentes com bike geocodificados/cruzados. None = todos.
LIMITE_EVENTOS = 20      # acidentes transmitidos em "tempo real" ao dashboard.
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
        iniciar_processo("src.api.api"),                           # API + dashboard
    ]

    sv = SensorVirtual.padrao()

    try:
        sv.iniciar()
        sv.mqtt.aguardar_online(["mp"])

        # 1) SV -> MP: bases completas; o MP cruza e grava no banco
        resposta = sv.publicar_bases(limite_cruzamento=LIMITE_CRUZAMENTO)

        if "erro" in resposta:
            raise RuntimeError(f"O MP falhou: {resposta['erro']}")

        print("\nMP concluiu:", resposta["resumo"], "\n")

        # 2) SV -> Broker -> MP -> Dashboard: acidentes em fluxo, como se fossem de agora
        porta = os.getenv("API_PORT", "8000")
        print(f"Dashboard: http://localhost:{porta}")

        if sys.stdin.isatty():
            input("Abra o dashboard e tecle Enter para transmitir os acidentes... ")

        sv.transmitir_acidentes(limite=LIMITE_EVENTOS, intervalo_s=INTERVALO_S)
        time.sleep(5)   # deixa o MP tratar e enviar o último evento

        if sys.stdin.isatty():
            input("Tudo enviado. Tecle Enter para encerrar (o dashboard fica no ar até lá)... ")

    finally:
        sv.parar()

        for p in processos:
            p.terminate()

        for p in processos:
            p.wait(timeout=10)


if __name__ == "__main__":
    main()
