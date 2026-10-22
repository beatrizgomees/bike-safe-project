"""Middleware: recebe os eventos do SV e os entrega aos clientes (Dashboard, Mobile, API).

  - assina bikesafe/eventos/acidente;
  - completa o evento com o que o MP já gravou no banco (posição, ciclovia, estação);
  - publica em bikesafe/app/acidente e mantém bikesafe/app/ultimos (retido) com os
    últimos eventos, para quem abrir o dashboard/app já ver algo.

Rodar:  python -m src.middleware.middleware
"""
import threading
from collections import deque

from src.database.banco import Banco
from src.mqtt import topicos
from src.mqtt.cliente import ClienteMQTT


class Middleware:
    def __init__(self, banco_factory=Banco, janela=20, cliente=None):
        self.banco_factory = banco_factory
        self.mqtt = cliente or ClienteMQTT("middleware")
        self.ultimos = deque(maxlen=janela)
        self._banco = None
        self._banco_falhou = False

    def iniciar(self):
        self.mqtt.assinar(topicos.EVENTO_ACIDENTE, self._ao_receber)
        self.mqtt.conectar()
        print("[Middleware] pronto, aguardando eventos em", topicos.EVENTO_ACIDENTE)

    # ----------------------------------------------------------------- eventos
    def _ao_receber(self, topico, mensagem):
        acidente = mensagem["dado"]

        evento = {
            "seq": mensagem.get("seq"),
            "total": mensagem.get("total"),
            "acidente": {k: v for k, v in acidente.items() if not k.startswith("_")},
            "analise": self.enriquecer(acidente.get("protocolo")),
        }

        self.mqtt.publicar(topicos.APP_ACIDENTE, evento)

        self.ultimos.append(evento)
        self.mqtt.publicar(topicos.APP_ULTIMOS, list(self.ultimos), retain=True)

        print(f"[Middleware] acidente {acidente.get('protocolo')} repassado aos clientes")

    def enriquecer(self, protocolo):
        """Posição, ciclovias e estação mais próximas, se o MP já processou esse acidente.
        Sem banco ou sem registro, devolve None (o evento segue sem análise)."""
        if protocolo is None or self._banco_falhou:
            return None

        try:
            if self._banco is None:
                self._banco = self.banco_factory()

            p = (str(protocolo),)

            local = self._banco.consultar(
                "SELECT lat, lon, geo_precisao FROM acidentes_bike WHERE protocolo = %s", p)

            if not local:
                return None

            return {
                "local": local[0],
                "ciclovias": self._banco.consultar(
                    "SELECT rede, rota, tipo, dist_m, na_ciclovia "
                    "FROM acidente_ciclovia WHERE protocolo = %s ORDER BY rede", p),
                "estacao": (self._banco.consultar(
                    "SELECT e.codigo, e.nome, x.dist_m, x.no_raio, x.estacoes_no_raio "
                    "FROM acidente_estacao x LEFT JOIN estacoes_bike e ON e.codigo = x.estacao_codigo "
                    "WHERE x.protocolo = %s", p) or [None])[0],
            }

        except Exception as erro:
            self._banco_falhou = True
            print(f"[Middleware] sem banco, seguindo sem análise ({erro})")
            return None

    def parar(self):
        self.mqtt.desconectar()

        if self._banco is not None:
            self._banco.fechar()


def main():
    mw = Middleware()
    mw.iniciar()

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        mw.parar()


if __name__ == "__main__":
    main()