import csv
from collections import Counter
from pathlib import Path

from src.utils.geo import distancia_ponto_linha_m
from src.utils.geocodificador import Geocodificador


class CruzamentoAcidentesCiclovias:
    """Cruza acidentes com bicicleta com as redes de ciclovias.

    Passos:
      1. pega os acidentes e fica só com os que têm ciclista;
      2. geocodifica (endereco + numero -> lat/lon);
      3. para cada rede (permanente, operacional...) acha a ciclovia mais
         próxima e a distância em metros;
      4. marca `na_ciclovia_<rede>` se estiver a até `raio_m` metros.

    redes: {"permanente": coletor_geojson, "operacional": coletor_geojson}
    """

    def __init__(self, acidentes, redes, geocodificador=None, raio_m=30):
        self.acidentes = acidentes
        self.redes = redes
        self.geocodificador = geocodificador or Geocodificador()
        self.raio_m = raio_m

    # ---------------------------------------------------------------- passos
    def acidentes_com_bike(self):
        dados = self.acidentes.buscar_dados()

        return self.acidentes.filtrar_acidentes_com_bike(dados)

    def _mais_proxima(self, lat, lon, trechos):
        melhor, menor = None, float("inf")

        for trecho in trechos:
            d = distancia_ponto_linha_m(lat, lon, trecho["pontos"])

            if d < menor:
                melhor, menor = trecho, d

        return melhor, menor

    def gerar(self, limite=None):
        bikes = self.acidentes_com_bike()

        if limite:
            bikes = bikes[:limite]

        trechos_por_rede = {
            nome: coletor.buscar_trechos() for nome, coletor in self.redes.items()
        }

        linhas = []

        try:
            for i, acidente in enumerate(bikes, 1):
                geo = self.geocodificador.geocodificar(
                    acidente.get("endereco"), acidente.get("numero")
                )

                linha = {
                    "protocolo": acidente.get("protocolo"),
                    "data": acidente.get("data"),
                    "hora": acidente.get("hora"),
                    "bairro": acidente.get("bairro"),
                    "endereco": acidente.get("endereco"),
                    "numero": acidente.get("numero"),
                    "natureza": acidente.get("natureza"),
                    "vitimas": acidente.get("vitimas"),
                    "vitimas_fatais": acidente.get("vitimas_fatais"),
                    "lat": geo["lat"] if geo else None,
                    "lon": geo["lon"] if geo else None,
                    "geo_precisao": geo["precisao"] if geo else "nao_encontrado",
                }

                for nome, trechos in trechos_por_rede.items():
                    if geo:
                        trecho, dist = self._mais_proxima(geo["lat"], geo["lon"], trechos)
                    else:
                        trecho, dist = None, None

                    linha[f"{nome}_rota"] = trecho["rota"] if trecho else None
                    linha[f"{nome}_tipo"] = trecho["tipo"] if trecho else None
                    linha[f"{nome}_dist_m"] = round(dist, 1) if trecho else None
                    linha[f"na_ciclovia_{nome}"] = (
                        bool(trecho) and dist <= self.raio_m
                    ) if geo else None

                linhas.append(linha)

                if i % 10 == 0:
                    print(f"  {i}/{len(bikes)} acidentes processados")
        finally:
            self.geocodificador.salvar()  # guarda o cache mesmo se interromper (Ctrl+C)

        return linhas

    # ---------------------------------------------------------------- saída
    def salvar_csv(self, linhas, caminho="data/acidentes_bike_x_ciclovias.csv"):
        if not linhas:
            raise ValueError("Nada para salvar.")

        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)

        with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            escritor.writeheader()
            escritor.writerows(linhas)

        return caminho

    def salvar_banco(self, linhas, banco):
        """Grava no banco (src.database.banco.Banco). Pode rodar várias vezes."""
        banco.salvar(linhas, list(self.redes))

    def resumo(self, linhas):
        total = len(linhas)
        geocodificados = [l for l in linhas if l["lat"] is not None]

        resultado = {
            "acidentes_com_bike": total,
            "geocodificados": len(geocodificados),
            "precisao": dict(Counter(l["geo_precisao"] for l in linhas)),
            "raio_m": self.raio_m,
        }

        for nome in self.redes:
            resultado[f"na_ciclovia_{nome}"] = sum(
                1 for l in geocodificados if l[f"na_ciclovia_{nome}"]
            )

        return resultado