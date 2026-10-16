import json
import os
import re
import time
from pathlib import Path

import requests

from src.utils.geo import dentro_do_recife, RECIFE_BBOX


class Geocodificador:
    """Endereço + número -> lat/lon, usando o Nominatim (OpenStreetMap).

    - Respeita a política do Nominatim: 1 requisição por segundo e User-Agent
      identificado (defina GEOCODER_CONTATO no .env, ex.: seu e-mail).
    - Guarda tudo num cache em disco (JSON). Se o programa for interrompido,
      ao rodar de novo ele continua de onde parou e não repete consultas.
    - Resultado: {"lat", "lon", "precisao"} ou None.
        precisao = "endereco"  -> achou a rua com o número
                   "rua"       -> achou só a rua (número não existe no mapa)
    """

    URL = "https://nominatim.openstreetmap.org/search"
    INTERVALO_S = 1.1

    def __init__(self, arquivo_cache="data/cache_geocodificacao.json", cidade="Recife"):
        contato = os.getenv("GEOCODER_CONTATO", "")

        self.headers = {
            "User-Agent": f"bike-safe-project (estudo; {contato or 'sem contato'})"
        }
        self.cidade = cidade
        self.arquivo = Path(arquivo_cache)
        self.cache = self._carregar()
        self._ultima = 0.0
        self.consultas = 0

    # ---------------------------------------------------------------- cache
    def _carregar(self):
        try:
            return json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def salvar(self):
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(
            json.dumps(self.cache, ensure_ascii=False, indent=0),
            encoding="utf-8"
        )

    # ---------------------------------------------------------------- consulta
    @staticmethod
    def _numero_valido(numero):
        numero = str(numero or "").strip()

        return numero if re.fullmatch(r"\d+", numero) and int(numero) > 0 else None

    def _consultar(self, params):
        espera = self.INTERVALO_S - (time.time() - self._ultima)

        if espera > 0:
            time.sleep(espera)

        lat_min, lat_max, lon_min, lon_max = RECIFE_BBOX

        base = {
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "br",
            "viewbox": f"{lon_min},{lat_max},{lon_max},{lat_min}",
            "bounded": 1,
        }

        resposta = requests.get(
            self.URL,
            params={**base, **params},
            headers=self.headers,
            timeout=30
        )
        self._ultima = time.time()
        self.consultas += 1

        resposta.raise_for_status()

        for item in resposta.json():
            lat, lon = float(item["lat"]), float(item["lon"])

            if dentro_do_recife(lat, lon):
                return lat, lon

        return None

    def geocodificar(self, endereco, numero=None):
        endereco = re.sub(r"\s+", " ", str(endereco or "")).strip()

        if not endereco:
            return None

        num = self._numero_valido(numero)
        chave = f"{endereco.upper()}|{num or ''}"

        if chave in self.cache:
            return self.cache[chave]

        resultado = None

        if num:
            achou = self._consultar({
                "street": f"{num} {endereco}",
                "city": self.cidade,
                "state": "Pernambuco",
            })

            if achou:
                resultado = {"lat": achou[0], "lon": achou[1], "precisao": "endereco"}

        if resultado is None:
            achou = self._consultar({
                "street": endereco,
                "city": self.cidade,
                "state": "Pernambuco",
            })

            if achou:
                resultado = {"lat": achou[0], "lon": achou[1], "precisao": "rua"}

        self.cache[chave] = resultado  # None também é guardado: não repete a consulta

        if self.consultas % 20 == 0:
            self.salvar()

        return resultado