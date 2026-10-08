from src.collector.ciclovias_collector import MalhaCicloviariaCollector
from src.collector.estacoes_collector import EstacoesBikeCollector
from src.collector.acidentes_collector import AcidentesCollector
import os
import requests
from collections import Counter
from dotenv import load_dotenv
from src.collector.rotas_collector import RotasPermanentesCollector


def main():

    print("\n===== MALHA CICLOVIÁRIA =====")

    malha = MalhaCicloviariaCollector()

    dados_malha = malha.buscar_dados()

    print(f"Total de registros: {len(dados_malha)}")

    malha_filtrada = malha.filtrar_por_bairro(dados_malha)

    print(f"Registros nos bairros filtrados: {len(malha_filtrada)}")

    for item in malha_filtrada:
        print(item)



    print("\n===== ESTAÇÕES DE BIKE =====")

    estacoes = EstacoesBikeCollector()

    dados_estacoes = estacoes.buscar_dados()

    print(f"Total de estações: {len(dados_estacoes)}")

    estacoes_filtradas = estacoes.filtrar_por_bairro(dados_estacoes)

    print(f"Estações nos bairros filtrados: {len(estacoes_filtradas)}")

    for item in estacoes_filtradas:
        print(item)

    print("\n===== ACIDENTES =====")

    acidentes = AcidentesCollector()

    dados_acidentes = acidentes.buscar_dados()

    print(f"Total de acidentes: {len(dados_acidentes)}")

    # Acidentes envolvendo bicicleta
    acidentes_bike = acidentes.filtrar_acidentes_com_bike(dados_acidentes)

    print(f"Acidentes com bicicleta: {len(acidentes_bike)}")

    acidentes_bike_filtrados = acidentes.filtrar_por_bairro(acidentes_bike)

    print(f"Acidentes com bicicleta nos bairros filtrados: {len(acidentes_bike_filtrados)}")

    for item in acidentes_bike_filtrados:
        print(item)


    print("\n===== ROTAS PERMANENTES (GEOJSON) =====")

    rotas = RotasPermanentesCollector()

    dados_rotas = rotas.buscar_dados()

    print(f"Total de pontos: {len(dados_rotas)}")

    # Rotas diferentes (cada rota tem vários pontos)
    nomes_rotas = {r["rota"] for r in dados_rotas if r["rota"]}
    print(f"Total de rotas: {len(nomes_rotas)}")

    rotas_filtradas = rotas.filtrar_por_bairro(dados_rotas)
    print(f"Pontos nos bairros filtrados: {len(rotas_filtradas)}")

    for item in rotas_filtradas[:5]:
        print(item)

    from src.collector.rotas_collector import RotasOperacionaisCollector

    print("\n===== ROTAS OPERACIONAIS (São rotas operacionais no domingo e feriado) (GEOJSON) =====")

    operacionais = RotasOperacionaisCollector()

    dados_operacionais = operacionais.buscar_dados()

    print(f"Total de pontos: {len(dados_operacionais)}")

    nomes_rotas = {r["rota"] for r in dados_operacionais if r["rota"]}
    print(f"Total de rotas: {len(nomes_rotas)}")

    operacionais_filtradas = operacionais.filtrar_por_bairro(dados_operacionais)
    print(f"Pontos nos bairros filtrados: {len(operacionais_filtradas)}")

    for item in operacionais_filtradas[:5]:
        print(item)

if __name__ == "__main__":
    main()