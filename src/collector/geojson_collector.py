import json

import requests

from src.collector.base_collector import BaseCollector
from src.utils.text_format import normalizar_texto


class GeoJSONCollector(BaseCollector):
    """Coletor de GeoJSON do portal.

    Cada rota do arquivo é "destrinchada" em um registro por ponto do desenho:

        {"rota": "Av. X", "bairro": "Boa Viagem", "sentido": "Bidirecional",
         "tipo": "Ciclovia", "lat": -8.05, "lon": -34.90}

    Os nomes das propriedades do arquivo podem variar, então cada campo é
    procurado por uma lista de nomes possíveis (sem acento/maiúsculas).
    Para ver as propriedades reais do arquivo: coletor.propriedades()
    """

    campo_bairro = "bairro"

    # campo de saída -> nomes possíveis da propriedade no arquivo
    CAMPOS = {
        "rota": ["rota", "nome", "name", "nome_rota", "logradouro", "via"],
        "bairro": ["bairros", "bairro"],
        "sentido": ["sentido"],
        "tipo": ["tipologia", "tipo"],
    }

    def _baixar_features(self):
        info = requests.get(
            self.url_recurso,
            params={"id": self.resource_id},
            timeout=30
        )

        if info.status_code == 404:
            raise LookupError(
                f"Recurso '{self.resource_id}' não existe no portal. "
                f"Confira o id no .env."
            )

        info.raise_for_status()

        recurso = info.json()["result"]

        if (recurso.get("format") or "").lower() not in ("geojson", "json"):
            raise ValueError(
                f"Recurso '{self.resource_id}' tem formato '{recurso.get('format')}', "
                f"não GeoJSON. Confira o id no .env."
            )

        response = requests.get(recurso["url"], timeout=60)
        response.raise_for_status()

        dados = json.loads(response.content.decode("utf-8-sig"))

        return dados.get("features", [])

    def propriedades(self):
        """Nomes das propriedades da primeira rota (para conferir o arquivo)."""
        features = self._baixar_features()

        return list((features[0].get("properties") or {}).keys()) if features else []

    def _ler(self, filtros=None, busca=None):
        features = self._baixar_features()

        for coluna, valor in (filtros or {}).items():
            features = [
                f for f in features
                if normalizar_texto((f.get("properties") or {}).get(coluna) or "")
                == normalizar_texto(valor)
            ]

        if busca:
            termo = normalizar_texto(busca)
            features = [
                f for f in features
                if termo in normalizar_texto(
                    " ".join(str(v) for v in (f.get("properties") or {}).values())
                )
            ]

        return features

    @staticmethod
    def _pontos(coordenadas):
        """Lista de (lon, lat) de qualquer geometria (linha, multilinha, ponto...)."""
        if not coordenadas:
            return []

        if isinstance(coordenadas[0], (int, float)):
            return [(coordenadas[0], coordenadas[1])]

        pontos = []

        for parte in coordenadas:
            pontos.extend(GeoJSONCollector._pontos(parte))

        return pontos

    @staticmethod
    def _linhas(geometria):
        """Lista de linhas, cada uma uma lista de (lat, lon). Pontos/polígonos são ignorados."""
        tipo = (geometria or {}).get("type")
        coords = (geometria or {}).get("coordinates") or []

        if tipo == "LineString":
            partes = [coords]
        elif tipo == "MultiLineString":
            partes = coords
        else:
            return []

        return [[(p[1], p[0]) for p in parte] for parte in partes if len(parte) >= 2]

    def buscar_trechos(self):
        """Um registro por trecho (linha) da rota, com todos os pontos juntos:

            {"rota", "bairro", "sentido", "tipo", "pontos": [(lat, lon), ...]}

        Usado no cruzamento, que precisa da linha inteira (distância ponto-linha).
        """
        chave = (self.resource_id, "trechos")
        cache = self._get_cache(chave)

        if cache is not None:
            return cache

        trechos = []

        for feature in self._baixar_features():
            propriedades = {
                normalizar_texto(k): v
                for k, v in (feature.get("properties") or {}).items()
            }

            dados_rota = {
                campo: self._pegar(propriedades, nomes)
                for campo, nomes in self.CAMPOS.items()
            }

            for pontos in self._linhas(feature.get("geometry")):
                trechos.append({**dados_rota, "pontos": pontos})

        self._set_cache(chave, trechos)

        return trechos

    def _pegar(self, propriedades, nomes):
        for nome in nomes:
            valor = propriedades.get(normalizar_texto(nome))

            if valor not in (None, ""):
                return valor

        return None

    def _parse_data(self, dados_brutos):
        resultados = []

        for feature in dados_brutos:
            propriedades = {
                normalizar_texto(k): v
                for k, v in (feature.get("properties") or {}).items()
            }

            dados_rota = {
                campo: self._pegar(propriedades, nomes)
                for campo, nomes in self.CAMPOS.items()
            }

            geometria = feature.get("geometry") or {}

            for lon, lat in self._pontos(geometria.get("coordinates")):
                if abs(lon) > 180 or abs(lat) > 90:
                    raise ValueError(
                        "As coordenadas do arquivo não estão em graus (lat/long)."
                    )

                resultados.append({**dados_rota, "lat": lat, "lon": lon})

        return resultados