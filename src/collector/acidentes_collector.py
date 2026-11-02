from src.collector.base_collector import BaseCollector
from src.sensor.filtros import filtrar_com_ciclista


class AcidentesCollector(BaseCollector):
    campo_bairro = "bairro"

    def __init__(self):
        super().__init__("ACIDENTES_ID")

    def _parse_data(self, dados_brutos):
        # a base traz "Protocolo" com maiúscula; padroniza todas as chaves
        return [
            {str(chave).strip().lower(): valor for chave, valor in item.items()}
            for item in dados_brutos
        ]

    def filtrar_acidentes_com_bike(self, dados):
        return filtrar_com_ciclista(dados)