from src.collector.geojson_collector import GeoJSONCollector


class RotasPermanentesCollector(GeoJSONCollector):
    def __init__(self):
        super().__init__("ROTAS_PERMANENTE_ID")


class RotasOperacionaisCollector(GeoJSONCollector):
    def __init__(self):
        super().__init__("ROTAS_OPERACIONAIS_ID")


class RotasConectaCollector(GeoJSONCollector):
    def __init__(self):
        super().__init__("ROTAS_CONECTA_ID")