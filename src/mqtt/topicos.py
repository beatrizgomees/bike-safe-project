

RAIZ = "bikesafe"

# SV -> MP
BASES = f"{RAIZ}/bases"                  # bases/acidentes, bases/estacoes, bases/malha, bases/trechos/<rede>
FIM_CARGA = f"{BASES}/fim"               # avisa o MP que a carga terminou (com as contagens)

# MP -> SV
MP_CONCLUIDO = f"{RAIZ}/mp/concluido"

# SV -> Middleware
EVENTO_ACIDENTE = f"{RAIZ}/eventos/acidente"

# Middleware -> clientes (dashboard, mobile)
APP_ACIDENTE = f"{RAIZ}/app/acidente"
APP_ULTIMOS = f"{RAIZ}/app/ultimos"      # quem entra agora já recebe os últimos eventos


def status(nome):
    return f"{RAIZ}/status/{nome}"