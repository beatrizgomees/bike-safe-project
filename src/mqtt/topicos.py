"""Nomes dos tópicos MQTT (um lugar só, para SV, MP e Middleware concordarem).

  O broker MQTT (Mosquitto) é o middleware: ninguém fala direto com ninguém.

  SV --bases/*-->   broker --> MP   carga das bases (A, E, C): cruza e grava no banco
  SV --eventos/*--> broker --> MP   fluxo de acidentes, um por vez (tempo real simulado)
  MP --app/*-->     broker --> Dashboard / Mobile (WebSocket)
  status/<nome>                 online/offline de cada componente (retido, com LWT)
"""

RAIZ = "bikesafe"

# SV -> MP
BASES = f"{RAIZ}/bases"                  # bases/acidentes, bases/estacoes, bases/malha, bases/trechos/<rede>
FIM_CARGA = f"{BASES}/fim"               # avisa o MP que a carga terminou (com as contagens)

# MP -> SV
MP_CONCLUIDO = f"{RAIZ}/mp/concluido"

# SV -> MP (um acidente por vez)
EVENTO_ACIDENTE = f"{RAIZ}/eventos/acidente"

# MP -> clientes (dashboard, mobile)
APP_ACIDENTE = f"{RAIZ}/app/acidente"
APP_ULTIMOS = f"{RAIZ}/app/ultimos"      # retido: quem entra agora já recebe os últimos eventos


def status(nome):
    return f"{RAIZ}/status/{nome}"
