import csv
import io
import os
import sys
import time
from pathlib import Path

import requests

from src.utils.text_format import normalizar_texto
from src.utils.text_format import BAIRROS_FILTRO

try:
    from dotenv import load_dotenv
    _DOTENV_OK = True
except ImportError: 
    _DOTENV_OK = False

_ENV = Path(__file__).resolve().parents[2] / ".env"

if _DOTENV_OK:
    load_dotenv(_ENV, encoding="utf-8-sig")  
    load_dotenv()                           


class BaseCollector:

    _cache = {}
    _cache_ttl = 55
    campo_bairro = None

    def __init__(self, chave_env):
        self.resource_id = os.getenv(chave_env)

        if not self.resource_id:
            if not _DOTENV_OK:
                motivo = (
                    
                    f"({sys.executable}). Instale com: "
                    f'"{sys.executable}" -m pip install python-dotenv'
                )
            elif not _ENV.exists():
                motivo = f"o arquivo .env não existe em: {_ENV}"
            else:
                motivo = (
                    f"o arquivo {_ENV} existe, mas não tem uma linha "
                    f"{chave_env}=<id> (confira o nome, sem aspas e sem espaços "
                    f"ao redor do '=')"
                )

            raise ValueError(f"Variável '{chave_env}' não encontrada: {motivo}.")

        self.base_url = os.getenv(
            "BASE_URL",
            "https://dados.recife.pe.gov.br"
        ).rstrip("/")

        self.url = f"{self.base_url}/api/3/action/datastore_search"
        self.url_recurso = f"{self.base_url}/api/3/action/resource_show"

        self.headers = {
            "Content-Type": "application/json"
        }

    def _request(self, limit=100, offset=0, filtros=None, busca=None):
        payload = {
            "resource_id": self.resource_id,
            "limit": limit,
            "offset": offset
        }

        if filtros:
            payload["filters"] = filtros

        if busca:
            payload["q"] = busca

        response = requests.post(
            self.url,
            json=payload,
            headers=self.headers,
            timeout=30
        )

        if response.status_code == 404:
            # O CKAN responde 404 quando o id está errado ou o recurso
            # não tem datastore ativo.
            raise LookupError(
                f"Recurso '{self.resource_id}' não encontrado ou sem datastore "
                f"ativo (POST {self.url})."
            )

        response.raise_for_status()

        corpo = response.json()

        if not corpo.get("success"):
            raise RuntimeError(f"Erro do CKAN: {corpo.get('error')}")

        return corpo

    def _buscar_todos(self, filtros=None, busca=None):
        registros = []
        offset = 0
        limit = 1000

        while True:
            resposta = self._request(
                limit=limit,
                offset=offset,
                filtros=filtros,
                busca=busca
            )

            resultado = resposta["result"]
            pagina = resultado["records"]

            if not pagina:
                break

            registros.extend(pagina)

            offset += len(pagina)

            total = resultado.get("total")

            if total is not None and offset >= total:
                break

        return registros

    def _baixar_csv(self, filtros=None, busca=None):
        """Alternativa quando não há datastore: baixa o CSV do recurso."""
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

        if (recurso.get("format") or "").lower() != "csv":
            raise ValueError(
                f"Recurso '{self.resource_id}' tem formato "
                f"'{recurso.get('format')}', não CSV."
            )

        response = requests.get(recurso["url"], timeout=60)
        response.raise_for_status()

        texto = response.content.decode("utf-8-sig", errors="replace")

        try:
            dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t|")
        except csv.Error:
            dialeto = csv.excel

        registros = list(csv.DictReader(io.StringIO(texto), dialect=dialeto))

        for coluna, valor in (filtros or {}).items():
            registros = [
                r for r in registros
                if normalizar_texto(r.get(coluna) or "") == normalizar_texto(valor)
            ]

        if busca:
            termo = normalizar_texto(busca)
            registros = [
                r for r in registros
                if termo in normalizar_texto(" ".join(str(v) for v in r.values()))
            ]

        return registros

    def _ler(self, filtros=None, busca=None):
        try:
            return self._buscar_todos(filtros=filtros, busca=busca)
        except LookupError:
            # sem datastore: tenta o CSV (falha com mensagem clara se o id não existe)
            return self._baixar_csv(filtros=filtros, busca=busca)

    def _get_cache(self, chave):
        if chave not in self._cache:
            return None

        dados, timestamp = self._cache[chave]

        if time.time() - timestamp > self._cache_ttl:
            del self._cache[chave]
            return None

        return dados

    def _set_cache(self, chave, dados):
        self._cache[chave] = (
            dados,
            time.time()
        )

    def buscar_dados(self, filtros=None, busca=None):
        chave = (
            self.resource_id,
            str(filtros),
            busca
        )

        cache = self._get_cache(chave)

        if cache is not None:
            return cache

        dados_brutos = self._ler(
            filtros=filtros,
            busca=busca
        )

        dados = self._parse_data(dados_brutos)
        self._set_cache(chave, dados)

        return dados

    def filtrar_por_bairro(self, dados, bairro=None, campo=None):
        termos = bairro or BAIRROS_FILTRO
        if isinstance(termos, str):
            termos = [termos]
        termos = [normalizar_texto(t) for t in termos]
        campo = campo or self.campo_bairro

        resultados = []

        for item in dados:
            if campo:
                valor = item.get(campo)
            else:
                valor = item.get("bairro") or item.get("bairros")
            valor = normalizar_texto(valor or "")
            if any(t in valor for t in termos):
                resultados.append(item)
        return resultados

    def _parse_data(self, dados_brutos):
        return dados_brutos