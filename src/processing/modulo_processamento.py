"""Módulo de Processamento (MP): recebe as bases do SV pelo MQTT, faz o cruzamento
(geocodificação, ciclovias, estações) e grava tudo no banco de dados.

Rodar:  python -m src.processing.modulo_processamento
"""
import threading
import traceback

from src.database.banco import Banco
from src.mqtt import topicos
from src.mqtt.cliente import ClienteMQTT
from src.processing.acidentes_ciclovias import CruzamentoAcidentesCiclovias
from src.processing.fontes_memoria import FonteAcidentes, FonteLista, FonteRede


class ModuloProcessamento:
    def __init__(self, raio_m=30, raio_estacao_m=300, banco_factory=Banco,
                 geocodificador=None, cliente=None):
        self.raio_m = raio_m
        self.raio_estacao_m = raio_estacao_m
        self.banco_factory = banco_factory
        self.geocodificador = geocodificador

        self.mqtt = cliente or ClienteMQTT("mp")

        self._trava = threading.Lock()
        self._buffers = {}
        self._fim = None
        self._processando = False

    def iniciar(self):
        self.mqtt.assinar(f"{topicos.BASES}/#", self._receber)
        self.mqtt.conectar()
        print("[MP] pronto, aguardando as bases do SV em", topicos.BASES)

    # ------------------------------------------------------------------ recepção
    def _receber(self, topico, mensagem):
        parte = topico[len(topicos.BASES) + 1:]

        with self._trava:
            if parte == "fim":
                self._fim = mensagem
            else:
                self._buffers.setdefault(parte, []).append(mensagem["dado"])

            if self._processando or not self._carga_completa():
                return

            self._processando = True
            fim, buffers = self._fim, self._buffers
            self._fim, self._buffers = None, {}

        # fora do callback do MQTT: o cruzamento demora (geocodificação) e não pode
        # travar a conexão com o broker
        threading.Thread(target=self._processar, args=(fim, buffers), daemon=True).start()

    def _carga_completa(self):
        if self._fim is None:
            return False

        c = self._fim["contagens"]
        esperado = {"acidentes": c["acidentes"], "estacoes": c["estacoes"]}
        esperado.update({f"trechos/{r}": n for r, n in c["trechos"].items()})

        if "malha" in c:
            esperado["malha"] = c["malha"]

        return all(len(self._buffers.get(k, [])) >= n for k, n in esperado.items())

    # --------------------------------------------------------------- processamento
    def _processar(self, fim, buffers):
        print("[MP] carga completa recebida, processando...")

        try:
            redes = {
                r: FonteRede(buffers.get(f"trechos/{r}", [])) for r in fim["redes"]
            }

            cruzamento = CruzamentoAcidentesCiclovias(
                acidentes=FonteAcidentes(buffers.get("acidentes", [])),
                redes=redes,
                geocodificador=self.geocodificador,
                raio_m=self.raio_m,
                estacoes=FonteLista(buffers.get("estacoes", [])),
                raio_estacao_m=self.raio_estacao_m,
            )

            linhas = cruzamento.gerar(limite=fim.get("limite"))

            banco = self.banco_factory()

            try:
                malha = FonteLista(buffers["malha"]) if buffers.get("malha") else None
                contagem = cruzamento.salvar_dados_completos(banco, malha=malha)
                cruzamento.salvar_banco(linhas, banco)
            finally:
                banco.fechar()

            resposta = {"resumo": cruzamento.resumo(linhas), "contagem": contagem}
            print("[MP] concluído:", resposta["resumo"])

        except Exception as erro:  # avisa o SV em vez de deixá-lo esperando
            traceback.print_exc()
            resposta = {"erro": f"{type(erro).__name__}: {erro}"}

        finally:
            self._processando = False

        self.mqtt.publicar(topicos.MP_CONCLUIDO, resposta)

    def parar(self):
        self.mqtt.desconectar()


def main():
    mp = ModuloProcessamento()
    mp.iniciar()

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        mp.parar()


if __name__ == "__main__":
    main()