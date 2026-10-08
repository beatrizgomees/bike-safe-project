
from src.collector.base_collector import BaseCollector


class AcidentesCollector(BaseCollector):

    def __init__(self):
        super().__init__(
            "ACIDENTES_ID"
        )

    def _parse_data(self, dados_brutos):
        resultados = []

        for item in dados_brutos:
            resultados.append({
                "protocolo": item.get("Protocolo"),
                "data": item.get("data"),
                "hora": item.get("hora"),
                "natureza": item.get("natureza"),
                "situacao": item.get("situacao"),
                "bairro": item.get("bairro"),
                "endereco": item.get("endereco"),
                "numero": item.get("numero"),
                "detalhe_endereco": item.get(
                    "detalhe_endereco_acidente"
                ),
                "complemento": item.get("complemento"),
                "bairro_cruzamento": item.get(
                    "bairro_cruzamento"
                ),
                "sentido_via": item.get("sentido_via"),
                "tipo": item.get("tipo"),
                "auto": item.get("auto"),
                "moto": item.get("moto"),
                "ciclom": item.get("ciclom"),
                "ciclista": item.get("ciclista"),
                "pedestre": item.get("pedestre"),
                "onibus": item.get("onibus"),
                "caminhao": item.get("caminhao"),
                "viatura": item.get("viatura"),
                "outros": item.get("outros"),
                "vitimas": item.get("vitimas"),
                "vitimas_fatais": item.get(
                    "vitimasfatais"
                ),
                "acidente_verificado": item.get(
                    "acidente_verificado"
                ),
                "tempo_clima": item.get("tempo_clima"),
                "situacao_semaforo": item.get(
                    "situacao_semaforo"
                ),
                "sinalizacao": item.get("sinalizacao"),
                "condicao_via": item.get("condicao_via"),
                "conservacao_via": item.get(
                    "conservacao_via"
                ),
                "ponto_controle": item.get(
                    "ponto_controle"
                ),
                "situacao_placa": item.get(
                    "situacao_placa"
                ),
                "velocidade_max_via": item.get(
                    "velocidade_max_via"
                ),
                "mao_direcao": item.get("mao_direcao"),
                "divisao_via1": item.get("divisao_via1"),
                "divisao_via2": item.get("divisao_via2"),
            })

        return resultados

    def filtrar_acidentes_com_bike(self, dados):
        resultados = []

        for item in dados:
            ciclista = item.get("ciclista")

            try:
                ciclista = float(str(ciclista or 0).replace(",", "."))
            except (ValueError, TypeError):
                ciclista = 0

            if ciclista > 0:
                resultados.append(item)

        return resultados