"""Sensor Virtual (SV): lê as bases A (acidentes), E (estações) e C (ciclovias),
aplica os filtros e transporta os dados por MQTT.

  1) publicar_bases()      -> bikesafe/bases/*       (consumido pelo Módulo de Processamento)
  2) transmitir_acidentes()-> bikesafe/eventos/...   (consumido pelo Middleware)

Rodar sozinho (com MP e Middleware já ligados):  python -m src.sensor.sensor_virtual
"""
import threading
import time

from src.mqtt import topicos
from src.mqtt.cliente import ClienteMQTT
from src.sensor.filtros import filtrar_com_ciclista, tem_ciclista


class SensorVirtual:
    def __init__(self, acidentes, estacoes, redes, malha=None, cliente=None):
        """acidentes/estacoes/malha: collectors com buscar_dados().
        redes: {"permanente": collector_geojson, ...} com buscar_trechos()."""
        self.acidentes = acidentes
        self.estacoes = estacoes
        self.redes = redes
        self.malha = malha

        self.mqtt = cliente or ClienteMQTT("sv")
        self._concluido = threading.Event()
        self._resposta_mp = None

    @classmethod
    def padrao(cls):
        """SV com os collectors do projeto."""
        from src.collector.acidentes_collector import AcidentesCollector
        from src.collector.ciclovias_collector import MalhaCicloviariaCollector
        from src.collector.estacoes_collector import EstacoesBikeCollector
        from src.collector.rotas_collector import (
            RotasOperacionaisCollector,
            RotasPermanentesCollector,
        )

        return cls(
            acidentes=AcidentesCollector(),
            estacoes=EstacoesBikeCollector(),
            redes={
                "permanente": RotasPermanentesCollector(),
                "operacional": RotasOperacionaisCollector(),
            },
            malha=MalhaCicloviariaCollector(),
        )

    # ------------------------------------------------------------- ciclo de vida
    def iniciar(self):
        self.mqtt.conectar()
        self.mqtt.assinar(topicos.MP_CONCLUIDO, self._ao_concluir)

    def parar(self):
        self.mqtt.desconectar()

    def _ao_concluir(self, topico, mensagem):
        self._resposta_mp = mensagem
        self._concluido.set()

    # ------------------------------------------------------------------- filtros
    def marcar_acidentes(self, acidentes):
        """Não descarta nada: marca cada acidente com `_com_bike` (filtro do SV).
        O MP guarda todos e cruza só os marcados."""
        return [{**a, "_com_bike": tem_ciclista(a)} for a in acidentes]

    def acidentes_com_bike(self):
        return filtrar_com_ciclista(self.acidentes.buscar_dados())

    # ----------------------------------------------------------- 1) bases -> MP
    def publicar_bases(self, limite_cruzamento=None, aguardar_mp=True, timeout=3600):
        self._concluido.clear()
        contagens = {}

        acidentes = self.marcar_acidentes(self.acidentes.buscar_dados())
        contagens["acidentes"] = self._publicar_lista("acidentes", acidentes)

        estacoes = self.estacoes.buscar_dados()
        contagens["estacoes"] = self._publicar_lista("estacoes", estacoes)

        contagens["trechos"] = {}

        for rede, coletor in self.redes.items():
            trechos = coletor.buscar_trechos()
            contagens["trechos"][rede] = self._publicar_lista(f"trechos/{rede}", trechos)

        if self.malha is not None:
            malha = self.malha.buscar_dados()
            contagens["malha"] = self._publicar_lista("malha", malha)

        self.mqtt.publicar(topicos.FIM_CARGA, {
            "contagens": contagens,
            "redes": list(self.redes),
            "limite": limite_cruzamento,
        })
        self.mqtt.esperar_envio()

        print(f"[SV] bases enviadas: {contagens}")

        if aguardar_mp:
            print("[SV] aguardando o Módulo de Processamento...")

            if not self._concluido.wait(timeout):
                raise TimeoutError("O MP não respondeu a tempo.")

            return self._resposta_mp

    def _publicar_lista(self, nome, registros):
        for registro in registros:
            self.mqtt.publicar(f"{topicos.BASES}/{nome}", {"dado": registro})

        return len(registros)

    # ------------------------------------------------- 2) eventos -> Middleware
    def transmitir_acidentes(self, limite=None, intervalo_s=2.0):
        """Publica os acidentes com bike um por vez, como se acontecessem agora."""
        acidentes = self.acidentes_com_bike()

        if limite:
            acidentes = acidentes[:limite]

        for i, acidente in enumerate(acidentes, 1):
            self.mqtt.publicar(topicos.EVENTO_ACIDENTE, {
                "seq": i, "total": len(acidentes), "dado": acidente,
            })
            print(f"[SV] evento {i}/{len(acidentes)}: acidente {acidente.get('protocolo')}")

            if intervalo_s and i < len(acidentes):
                time.sleep(intervalo_s)

        self.mqtt.esperar_envio()

        return len(acidentes)


if __name__ == "__main__":
    sv = SensorVirtual.padrao()
    sv.iniciar()

    try:
        sv.mqtt.aguardar_online(["mp", "middleware"])
        print("[SV] resposta do MP:", sv.publicar_bases(limite_cruzamento=50))
        sv.transmitir_acidentes(limite=20)
    finally:
        sv.parar()