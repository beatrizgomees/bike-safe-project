import csv
from collections import Counter
from pathlib import Path

from src.utils.geo import dentro_do_recife, distancia_ponto_linha_m, haversine_m
from src.utils.geocodificador import Geocodificador


def _num(valor):
    try:
        return float(str(valor).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _tipo_trecho(trecho):
    """Tipo do trecho; se vier vazio e a rota começar com 'Ciclofaixa', usa 'Ciclofaixa'."""
    tipo = trecho.get("tipo")
    if tipo:
        return tipo
    palavras = (trecho.get("rota") or "").split()
    if palavras and palavras[0].lower() == "ciclofaixa":
        return "Ciclofaixa"
    return None


class CruzamentoAcidentesCiclovias:
    """Cruza acidentes com bicicleta com as redes de ciclovias.

    Passos:
      1. pega os acidentes e fica só com os que têm ciclista;
      2. geocodifica (endereco + numero -> lat/lon);
      3. para cada rede (permanente, operacional...) acha a ciclovia mais
         próxima e a distância em metros;
      4. marca `na_ciclovia_<rede>` se estiver a até `raio_m` metros;
      5. (opcional) acha a estação de bike mais próxima e quantas estações
         existem a até `raio_estacao_m` metros do acidente.

    redes: {"permanente": coletor_geojson, "operacional": coletor_geojson}
    estacoes: EstacoesBikeCollector (opcional)
    """

    def __init__(self, acidentes, redes, geocodificador=None, raio_m=30,
                 estacoes=None, raio_estacao_m=300):
        self.acidentes = acidentes
        self.redes = redes
        self.estacoes = estacoes
        self.raio_estacao_m = raio_estacao_m
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

    def lista_estacoes(self, apenas_validas=True):
        """Estações: [{codigo, nome, localizacao, bairro, capacidade, lat, lon, coord_valida}].

        apenas_validas=True (cruzamento): só as com coordenada dentro do Recife.
        apenas_validas=False (carga completa): todas; lat/lon ficam como vieram.
        """
        if not self.estacoes:
            return []

        resultado = []

        for e in self.estacoes.buscar_dados():
            lat, lon = _num(e.get("latitude")), _num(e.get("longitude"))

            valida = lat is not None and lon is not None and dentro_do_recife(lat, lon)

            if apenas_validas and not valida:
                continue  # coordenada vazia, zerada ou fora do Recife

            resultado.append({
                "codigo": str(e.get("codigo")),
                "nome": e.get("nome"),
                "localizacao": e.get("localizacao"),
                "bairro": e.get("bairro"),
                "capacidade": _num(e.get("capacidade")),
                "lat": lat,
                "lon": lon,
                "coord_valida": valida,
            })

        return resultado

    def _estacao_mais_proxima(self, lat, lon, estacoes):
        melhor, menor, no_raio = None, float("inf"), 0

        for e in estacoes:
            d = haversine_m(lat, lon, e["lat"], e["lon"])

            if d <= self.raio_estacao_m:
                no_raio += 1

            if d < menor:
                melhor, menor = e, d

        return melhor, menor, no_raio

    def _trechos(self):
        # buscar_trechos() tem cache, então chamar várias vezes não rebaixa o arquivo
        return {nome: c.buscar_trechos() for nome, c in self.redes.items()}

    def processar_um(self, acidente, trechos_por_rede=None, estacoes=None):
        """Geocodifica 1 acidente; acha a ciclovia mais próxima de cada rede
        e a estação de bike mais próxima."""
        trechos_por_rede = trechos_por_rede or self._trechos()
        estacoes = self.lista_estacoes() if estacoes is None else estacoes

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
            linha[f"{nome}_tipo"] = _tipo_trecho(trecho) if trecho else None
            linha[f"{nome}_dist_m"] = round(dist, 1) if trecho else None
            linha[f"na_ciclovia_{nome}"] = (
                bool(trecho) and dist <= self.raio_m
            ) if geo else None

        if self.estacoes:
            if geo and estacoes:
                est, dist, qtd = self._estacao_mais_proxima(geo["lat"], geo["lon"], estacoes)
            else:
                est, dist, qtd = None, None, None

            linha["estacao_codigo"] = est["codigo"] if est else None
            linha["estacao_nome"] = est["nome"] if est else None
            linha["estacao_dist_m"] = round(dist, 1) if est else None
            linha["estacao_no_raio"] = (dist <= self.raio_estacao_m) if est else None
            linha["estacoes_no_raio"] = qtd

        return linha

    def gerar(self, limite=None):
        bikes = self.acidentes_com_bike()

        if limite:
            bikes = bikes[:limite]

        trechos_por_rede = self._trechos()
        estacoes = self.lista_estacoes()
        linhas = []

        try:
            for i, acidente in enumerate(bikes, 1):
                linhas.append(self.processar_um(acidente, trechos_por_rede, estacoes))

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
        if self.estacoes:
            # todas (inclusive sem coordenada); antes de acidente_estacao, que referencia
            banco.salvar_estacoes(self.lista_estacoes(apenas_validas=False))

        banco.salvar(linhas, list(self.redes))

        if self.estacoes:
            banco.salvar_acidente_estacao(linhas)

    def salvar_dados_completos(self, banco, malha=None):
        """Grava as bases COMPLETAS (não só o cruzamento) nas tabelas de dados:
        acidentes, estacoes_bike, ciclovia_trechos e, se informada, malha_cicloviaria.

        malha: MalhaCicloviariaCollector (opcional).
        Devolve quantas linhas cada base tem, para conferir com o portal.
        """
        contagem = {}

        acidentes = self.acidentes.buscar_dados()
        banco.salvar_acidentes(acidentes)
        contagem["acidentes_na_origem"] = len(acidentes)
        contagem["acidentes_no_banco"] = banco.consultar(
            "SELECT COUNT(*) AS n FROM acidentes")[0]["n"]

        if self.estacoes:
            estacoes = self.lista_estacoes(apenas_validas=False)
            banco.salvar_estacoes(estacoes)
            contagem["estacoes"] = len(estacoes)

        trechos = self._trechos()
        banco.salvar_trechos(trechos)
        contagem["trechos"] = {rede: len(t) for rede, t in trechos.items()}

        if malha:
            registros = malha.buscar_dados()
            banco.salvar_malha(registros)
            contagem["malha"] = len(registros)

        return contagem

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

        if self.estacoes:
            com_estacao = [l for l in geocodificados if l.get("estacao_no_raio") is not None]
            resultado["raio_estacao_m"] = self.raio_estacao_m
            resultado["com_estacao_no_raio"] = sum(1 for l in com_estacao if l["estacao_no_raio"])

        return resultado