
from src.collector.base_collector import BaseCollector


class EstacoesBikeCollector(BaseCollector):

    def __init__(self):
        super().__init__(
            "ESTACOES_BIKE_ID"
        )

    def _parse_data(self, dados_brutos):
        resultados = []

        for item in dados_brutos:
            resultados.append({
                "id": item.get("id"),
                "codigo": item.get("codigo"),
                "localizacao": item.get("localizacao"),
                "capacidade": item.get("capacidade"), 
                "bairro": item.get("bairro"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
            })

        return resultados

