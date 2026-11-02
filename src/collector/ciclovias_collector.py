from src.collector.base_collector import BaseCollector

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pip install python-dotenv
    pass
 

class MalhaCicloviariaCollector(BaseCollector):

    def __init__(self):
        super().__init__("MALHA_CICLOVIARIA_ID")

    def _parse_data(self, dados_brutos):
        resultados = []
        for item in dados_brutos:
            resultados.append({
                "rota": item.get("rota"),
                "tipologia": item.get("tipologia"),
                "sentido": item.get("sentido"),
                "percurso": item.get("percurso"),
                "bairros": item.get("bairros"),
                "extensao": item.get("extensao"),
                "inauguracao": item.get("inauguracao"),
            })
        return resultados