"""
Bases:
  1) Malha Cicloviária do Recife
  2) Estações de Bikes (Bike PE)
  3) Sinistros de Trânsito (ano mais recente)

Requer: pip install requests
"""
import csv
import io
import time
from datetime import datetime

import requests

BASE_URL = "https://dados.recife.pe.gov.br"

DATASETS = {
    "ciclovias": f"{BASE_URL}/dataset/malha-cicloviaria-do-recife",
    "estacoes": f"{BASE_URL}/dataset/ciclovias-ciclofaixas-estacoes-de-aluguel-de-bikes-e-rotas",
    "acidentes": f"{BASE_URL}/dataset/acidentes-de-transito-com-e-sem-vitimas",
}

INTERVALO_SLEEP = 60 


def _slug(url_dataset):
    return url_dataset.rstrip("/").split("/")[-1]


def listar_recursos(url_dataset):
   
    resp = requests.get(
        f"{BASE_URL}/api/3/action/package_show",
        params={"id": _slug(url_dataset)},
        timeout=15,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"Dataset não encontrado: {url_dataset}")
    return payload["result"]["resources"]


def escolher_recurso(recursos, *preferencias):
    for alvo in preferencias:
        alvo = alvo.lower()
        for r in recursos:
            nome = (r.get("name") or "").lower()
            formato = (r.get("format") or "").lower()
            if alvo in nome or alvo == formato:
                return r
    return recursos[0] if recursos else None

def buscar_registros(url_dataset, *preferencias, limit=5000):

    recursos = listar_recursos(url_dataset)
    recurso = escolher_recurso(recursos, *preferencias)
    if recurso is None:
        return []
 
    resp = requests.get(
        f"{BASE_URL}/api/3/action/datastore_search",
        params={"resource_id": recurso["id"], "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    resultado = resp.json()["result"]
    campos = [f["id"] for f in resultado["fields"]]
    return [dict(zip(campos, linha)) for linha in resultado["records"]]


def fetch_payload(recurso, limit=2000):
    
    try:
        if recurso.get("datastore_active"):
            resp = requests.get(
                f"{BASE_URL}/api/3/action/datastore_search",
                params={"resource_id": recurso["id"], "limit": limit},
                timeout=30,
            )
            resp.raise_for_status()
            resultado = resp.json()["result"]
            campos = [f["id"] for f in resultado["fields"]]
            return [dict(zip(campos, linha)) for linha in resultado["records"]]

        resp = requests.get(recurso["url"], timeout=30)
        resp.raise_for_status()
        formato = (recurso.get("format") or "").upper()
        if formato in ("JSON", "GEOJSON"):
            return resp.json()
        if formato == "CSV":
            return list(csv.DictReader(io.StringIO(resp.text)))
        return resp.text
    except requests.RequestException:
        return None

def buscar_ciclovias():
    return buscar_registros(DATASETS["ciclovias"], "detalhes da implantação", "csv")
 
 
def buscar_estacoes():
    return buscar_registros(DATASETS["estacoes"], "bike pe", "csv")
 
 
def buscar_acidentes():
    return buscar_registros(DATASETS["acidentes"], "2024", "csv")

# def buscar_ciclovias():
#     recursos = listar_recursos(DATASETS["ciclovias"])
#     recurso = escolher_recurso(recursos, "detalhes da implantação", "csv")
#     return fetch_payload(recurso)


# def buscar_estacoes():
#     recursos = listar_recursos(DATASETS["estacoes"])
#     recurso = escolher_recurso(recursos, "bike pe", "csv")
#     return fetch_payload(recurso)


# def buscar_acidentes(ano=2024):
#     recursos = listar_recursos(DATASETS["acidentes"])
#     recurso = escolher_recurso(recursos, str(ano))
#     return fetch_payload(recurso)



def _para_float(valor):
    if valor in (None, ""):
        return 0.0
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return 0.0

def filtrar_acidentes_com_bicicleta(registros):
    return [r for r in registros if _para_float(r.get("ciclista")) > 0]


def processar_ciclovias(registros):
    km_total = sum(_para_float(r.get("extensao")) for r in registros)
    return {"total_rotas": len(registros), "km_total": round(km_total, 1)}


def processar_estacoes(registros):
    capacidade_total = sum(_para_float(r.get("capacidade")) for r in registros)
    return {"total_estacoes": len(registros), "capacidade_total": int(capacidade_total)}


# def processar_acidentes(registros):
#     com_vitima = sum(1 for r in registros if (r.get("natureza") or "").strip().upper() == "COM VÍTIMA")
#     vitimas_fatais = sum(_para_float(r.get("vitimasfatais")) for r in registros)
#     return {
#         "total_acidentes": len(registros),
#         "acidentes_com_vitima": com_vitima,
#         "vitimas_fatais": int(vitimas_fatais),
#     }

def processar_acidentes(registros):
    com_vitima = sum(1 for r in registros if (r.get("natureza") or "").strip().upper() == "COM VÍTIMA")
    vitimas_fatais = sum(_para_float(r.get("vitimasfatais")) for r in registros)
    com_bicicleta = filtrar_acidentes_com_bicicleta(registros)
    return {
        "total_acidentes": len(registros),
        "acidentes_com_vitima": com_vitima,
        "vitimas_fatais": int(vitimas_fatais),
        "acidentes_com_bicicleta": len(com_bicicleta),
    }


def montar_dashboard():
    """Equivalente ao calcular_media_recife() em C — só que consolidando
    3 fontes (ciclovias, estações, acidentes) em vez de uma."""
    ciclovias = buscar_ciclovias()
    estacoes = buscar_estacoes()
    acidentes = buscar_acidentes()

    if ciclovias is None or estacoes is None or acidentes is None:
        return None 

    dados = {}
    dados.update(processar_ciclovias(ciclovias))
    dados.update(processar_estacoes(estacoes))
    dados.update(processar_acidentes(acidentes))
    dados["timestamp"] = datetime.now().isoformat(timespec="seconds")
    return dados


def imprimir_dashboard(dados):
    print("\n--- CONSOLIDADO DASHBOARD ---")
    print("Cidade:              RECIFE")
    print(f"Malha cicloviária:   {dados['total_rotas']} rotas ({dados['km_total']} km)")
    print(f"Estações Bike PE:    {dados['total_estacoes']} ({dados['capacidade_total']} vagas)")
    print(
        f"Acidentes (ano):     {dados['total_acidentes']} "
        f"({dados['acidentes_com_vitima']} com vítima, {dados['vitimas_fatais']} fatais)"
    )
    print(f"Timestamp:           {dados['timestamp']}")
    print("-----------------------------")



def ciclo_de_leitura():
    agora = datetime.now()
    print(f"\n[{agora:%H:%M:%S}] >> Acordando middleware...")

    dados = montar_dashboard()  # Coleta (rede) + Processamento (aplicação)
    if dados:
        imprimir_dashboard(dados)
        print(">> Ciclo finalizado. Entrando em modo sleep.")
    else:
        print("(!) Erro na coleta. Tentando novamente no próximo ciclo...")


def main():
    print("INICIANDO MIDDLEWARE VIRTUAL (RECIFE)")
    print(f"Configurado para ciclos de {INTERVALO_SLEEP} segundos.")

    while True:
        ciclo_de_leitura()
        time.sleep(INTERVALO_SLEEP)


if __name__ == "__main__":
    main()