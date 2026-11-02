import queue
import threading
import traceback
from collections import deque

from src.database.banco import Banco
from src.mqtt import topicos
from src.mqtt.cliente import ClienteMQTT
from src.processing.acidentes_ciclovias import CruzamentoAcidentesCiclovias
from src.processing.fontes_memoria import FonteAcidentes, FonteLista, FonteRede


class ModuloProcessamento:
    def __init__(self, raio_m=30, raio_estacao_m=300, banco_factory=Banco,
                 geocodificador=None, cliente=None, janela=20):
        self.raio_m = raio_m
        self.raio_estacao_m = raio_estacao_m
        self.banco_factory = banco_factory
        self.geocodificador = geocodificador

        self.mqtt = cliente or ClienteMQTT("mp")

        self._trava = threading.Lock()
        self._buffers = {}
        self._fim = None
        self._processando = False

        # referências para tratar acidentes avulsos (preenchidas pela carga ou pelo banco)
        self._cruz = None
        self._trechos = None
        self._estacoes = None
        self._trava_ref = threading.Lock()

        self._eventos = queue.Queue()
        self._ultimos = deque(maxlen=janela)

    def iniciar(self):
        self.mqtt.assinar(f"{topicos.BASES}/#", self._receber)
        self.mqtt.assinar(topicos.EVENTO_ACIDENTE, lambda topico, mensagem: self._eventos.put(mensagem))
        self.mqtt.conectar()

        # fora do callback do MQTT: geocodificar demora e não pode travar a conexão
        threading.Thread(target=self._trabalhar_eventos, daemon=True).start()

        print("[MP] pronto. Bases em", topicos.BASES, "| eventos em", topicos.EVENTO_ACIDENTE)

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

            with self._trava_ref:  # a partir daqui o MP já sabe tratar acidentes avulsos
                self._cruz = cruzamento
                self._trechos = cruzamento._trechos()
                self._estacoes = cruzamento.lista_estacoes()

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

    # ------------------------------------------------- acidente a acidente -> dashboard
    def _trabalhar_eventos(self):
        while True:
            mensagem = self._eventos.get()

            try:
                self._tratar_evento(mensagem)
            except Exception:
                traceback.print_exc()

    def _tratar_evento(self, mensagem):
        acidente = mensagem["dado"]
        self._garantir_referencias()

        linha = self._cruz.processar_um(acidente, self._trechos, self._estacoes)
        self._cruz.geocodificador.salvar()

        banco = self.banco_factory()

        try:
            banco.salvar_acidentes([acidente])
            banco.salvar([linha], list(self._trechos))
            banco.salvar_acidente_estacao([linha])
        finally:
            banco.fechar()

        evento = self._montar_evento(mensagem, acidente, linha)
        self.mqtt.publicar(topicos.APP_ACIDENTE, evento)

        self._ultimos.append(evento)
        self.mqtt.publicar(topicos.APP_ULTIMOS, list(self._ultimos), retain=True)

        print(f"[MP] acidente {linha['protocolo']} tratado e enviado ao dashboard")

    def _montar_evento(self, mensagem, acidente, linha):
        estacao = None

        if linha.get("estacao_codigo"):
            estacao = {
                "codigo": linha["estacao_codigo"],
                "nome": linha["estacao_nome"],
                "dist_m": linha["estacao_dist_m"],
                "no_raio": linha["estacao_no_raio"],
                "estacoes_no_raio": linha["estacoes_no_raio"],
            }

        return {
            "seq": mensagem.get("seq"),
            "total": mensagem.get("total"),
            "acidente": {k: v for k, v in acidente.items() if not k.startswith("_")},
            "analise": {
                "local": {k: linha[k] for k in ("lat", "lon", "geo_precisao")},
                "ciclovias": [
                    {"rede": rede, "rota": linha[f"{rede}_rota"], "tipo": linha[f"{rede}_tipo"],
                     "dist_m": linha[f"{rede}_dist_m"], "na_ciclovia": linha[f"na_ciclovia_{rede}"]}
                    for rede in self._trechos
                ],
                "estacao": estacao,
            },
        }

    def _garantir_referencias(self):
        """Ciclovias e estações vêm da última carga; se o MP reiniciou, lê do banco."""
        with self._trava_ref:
            if self._cruz is not None:
                return

            banco = self.banco_factory()

            try:
                trechos = {}

                for r in banco.consultar("SELECT rede, rota, tipo, geometria FROM ciclovia_trechos"):
                    pontos = [(lat, lon) for lon, lat in r["geometria"]["coordinates"]]
                    trechos.setdefault(r["rede"], []).append(
                        {"rota": r["rota"], "tipo": r["tipo"], "pontos": pontos})

                estacoes = banco.consultar(
                    "SELECT codigo, nome, lat, lon FROM estacoes_bike WHERE coord_valida")
            finally:
                banco.fechar()

            if not trechos:
                raise RuntimeError("Sem ciclovias no banco: o SV precisa publicar as bases antes.")

            self._cruz = CruzamentoAcidentesCiclovias(
                acidentes=FonteLista([]),
                redes={r: FonteRede(t) for r, t in trechos.items()},
                geocodificador=self.geocodificador,
                raio_m=self.raio_m,
                estacoes=FonteLista([]),
                raio_estacao_m=self.raio_estacao_m,
            )
            self._trechos, self._estacoes = trechos, estacoes

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
