"""API: lê (e, para reportes, grava) no banco e atende o Dashboard e o Mobile.

  GET  /                          página do dashboard (dashboard/index.html)
  GET  /api/resumo                totais do cruzamento
  GET  /api/acidentes?limite=200  acidentes com bike, com ciclovia e estação mais próximas
  GET  /api/acidentes/<protocolo> um acidente
  GET  /api/ciclovias[?rede=]     trechos de ciclovia/ciclofaixa (GeoJSON)
  GET  /api/estacoes              estações Bike PE com coordenada válida
  GET  /api/reportes?dispositivo= reportes feitos por um aparelho
  POST /api/reportes              novo reporte de acidente feito pelo app

Só usa a biblioteca padrão. Rodar:  python -m src.api.api   (porta API_PORT, padrão 8000)
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.database.banco import Banco
from src.utils.geo import dentro_do_recife

PAGINA = Path(__file__).resolve().parents[2] / "dashboard" / "index.html"

TIPOS_REPORTE = ("colisao", "queda", "atropelamento", "outro")

DDL_REPORTES = (
    """CREATE TABLE IF NOT EXISTS reportes (
        id           BIGSERIAL PRIMARY KEY,
        dispositivo  TEXT NOT NULL,
        criado_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
        tipo         TEXT NOT NULL,
        descricao    TEXT,
        endereco     TEXT,
        lat          DOUBLE PRECISION NOT NULL CHECK (lat BETWEEN -90 AND 90),
        lon          DOUBLE PRECISION NOT NULL CHECK (lon BETWEEN -180 AND 180),
        status       TEXT NOT NULL DEFAULT 'recebido'
    )""",
    "CREATE INDEX IF NOT EXISTS ix_reportes_dispositivo ON reportes (dispositivo, criado_em DESC)",
)

SQL_ACIDENTES = """
SELECT b.protocolo, b.data, b.hora, b.bairro, b.endereco, b.numero, b.natureza,
       b.vitimas, b.vitimas_fatais, b.lat, b.lon, b.geo_precisao,
       (SELECT COALESCE(json_agg(json_build_object(
                  'rede', c.rede, 'rota', c.rota, 'tipo', c.tipo,
                  'dist_m', c.dist_m, 'na_ciclovia', c.na_ciclovia) ORDER BY c.rede), '[]'::json)
          FROM acidente_ciclovia c WHERE c.protocolo = b.protocolo) AS ciclovias,
       (SELECT json_build_object('codigo', e.codigo, 'nome', e.nome, 'dist_m', x.dist_m,
                                 'no_raio', x.no_raio, 'estacoes_no_raio', x.estacoes_no_raio)
          FROM acidente_estacao x JOIN estacoes_bike e ON e.codigo = x.estacao_codigo
         WHERE x.protocolo = b.protocolo) AS estacao
  FROM acidentes_bike b
"""

SQL_RESUMO = """
SELECT (SELECT COUNT(*) FROM acidentes)                                         AS acidentes_total,
       (SELECT COUNT(*) FROM acidentes_bike)                                    AS acidentes_bike,
       (SELECT COUNT(*) FROM acidentes_bike WHERE lat IS NOT NULL)              AS geocodificados,
       (SELECT COUNT(DISTINCT protocolo) FROM acidente_ciclovia WHERE na_ciclovia) AS em_ciclovia,
       (SELECT COUNT(*) FROM acidente_estacao WHERE no_raio)                    AS com_estacao_no_raio
"""

SQL_ESTACOES = """
SELECT codigo, nome, localizacao, bairro, capacidade, lat, lon
  FROM estacoes_bike WHERE coord_valida AND lat IS NOT NULL AND lon IS NOT NULL
 ORDER BY nome
"""

COLUNAS_REPORTE = "id, dispositivo, criado_em, tipo, descricao, endereco, lat, lon, status"


class ErroRequisicao(Exception):
    """Pedido inválido: vira resposta 400 com a mensagem."""


def ciclovias_geojson(banco, rede=None):
    sql = "SELECT rede, rota, bairro, tipo, sentido, extensao_m, geometria FROM ciclovia_trechos"
    linhas = banco.consultar(sql + (" WHERE rede = %s" if rede else ""), (rede,) if rede else ())

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": l["geometria"],
                "properties": {k: l[k] for k in ("rede", "rota", "bairro", "tipo", "sentido", "extensao_m")},
            }
            for l in linhas
        ],
    }


def validar_reporte(dados):
    """Confere o corpo do POST e devolve os campos limpos."""
    if not isinstance(dados, dict):
        raise ErroRequisicao("corpo deve ser um objeto JSON")

    dispositivo = str(dados.get("dispositivo") or "").strip()

    if not 8 <= len(dispositivo) <= 64:
        raise ErroRequisicao("dispositivo inválido")

    tipo = str(dados.get("tipo") or "").strip().lower()

    if tipo not in TIPOS_REPORTE:
        raise ErroRequisicao(f"tipo deve ser um de: {', '.join(TIPOS_REPORTE)}")

    try:
        lat, lon = float(dados["lat"]), float(dados["lon"])
    except (KeyError, TypeError, ValueError):
        raise ErroRequisicao("lat e lon são obrigatórios e numéricos")

    if not dentro_do_recife(lat, lon):
        raise ErroRequisicao("a localização precisa estar no Recife")

    descricao = str(dados.get("descricao") or "").strip()[:500] or None
    endereco = str(dados.get("endereco") or "").strip()[:200] or None

    return dispositivo, tipo, descricao, endereco, lat, lon


class Handler(BaseHTTPRequestHandler):
    def _responder(self, corpo, tipo="application/json; charset=utf-8", status=200):
        if not isinstance(corpo, bytes):
            corpo = json.dumps(corpo, ensure_ascii=False, default=str).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Access-Control-Allow-Origin", "*")  # o app pode estar em outra origem
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        # pré-voo do CORS: o navegador pergunta antes de enviar um POST com JSON
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        caminho = url.path.rstrip("/") or "/"
        consulta = parse_qs(url.query)

        try:
            if caminho == "/":
                return self._responder(PAGINA.read_bytes(), "text/html; charset=utf-8")

            banco = Banco()

            try:
                if caminho == "/api/resumo":
                    return self._responder(banco.consultar(SQL_RESUMO)[0])

                if caminho == "/api/ciclovias":
                    return self._responder(ciclovias_geojson(banco, consulta.get("rede", [None])[0]))

                if caminho == "/api/estacoes":
                    return self._responder(banco.consultar(SQL_ESTACOES))

                if caminho == "/api/reportes":
                    dispositivo = consulta.get("dispositivo", [""])[0].strip()

                    if not dispositivo:
                        raise ErroRequisicao("informe ?dispositivo=")

                    return self._responder(banco.consultar(
                        f"SELECT {COLUNAS_REPORTE} FROM reportes WHERE dispositivo = %s "
                        "ORDER BY criado_em DESC LIMIT 200", (dispositivo,)))

                if caminho == "/api/acidentes":
                    limite = min(int(consulta.get("limite", ["200"])[0]), 2000)
                    return self._responder(banco.consultar(
                        SQL_ACIDENTES + " ORDER BY b.data DESC, b.hora DESC LIMIT %s", (limite,)))

                if caminho.startswith("/api/acidentes/"):
                    protocolo = caminho.rsplit("/", 1)[1]
                    achados = banco.consultar(SQL_ACIDENTES + " WHERE b.protocolo = %s", (protocolo,))

                    if achados:
                        return self._responder(achados[0])
            finally:
                banco.fechar()

            self._responder({"erro": "não encontrado"}, status=404)

        except ErroRequisicao as erro:
            self._responder({"erro": str(erro)}, status=400)
        except Exception as erro:
            self._responder({"erro": f"{type(erro).__name__}: {erro}"}, status=500)

    def do_POST(self):
        caminho = urlparse(self.path).path.rstrip("/")

        try:
            if caminho != "/api/reportes":
                return self._responder({"erro": "não encontrado"}, status=404)

            tamanho = int(self.headers.get("Content-Length") or 0)

            if not 0 < tamanho <= 10_000:
                raise ErroRequisicao("corpo ausente ou grande demais")

            try:
                dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            except ValueError:
                raise ErroRequisicao("JSON inválido")

            campos = validar_reporte(dados)
            banco = Banco()

            try:
                criado = banco.consultar(
                    "INSERT INTO reportes (dispositivo, tipo, descricao, endereco, lat, lon) "
                    f"VALUES (%s,%s,%s,%s,%s,%s) RETURNING {COLUNAS_REPORTE}", campos)[0]
            finally:
                banco.fechar()

            self._responder(criado, status=201)

        except ErroRequisicao as erro:
            self._responder({"erro": str(erro)}, status=400)
        except Exception as erro:
            self._responder({"erro": f"{type(erro).__name__}: {erro}"}, status=500)

    def log_message(self, formato, *args):
        pass  # sem uma linha de log por requisição


def garantir_tabelas():
    """Cria a tabela de reportes se ainda não existir (não mexe nas demais)."""
    banco = Banco()

    try:
        for comando in DDL_REPORTES:
            banco.con.execute(comando)
    finally:
        banco.fechar()


def criar_servidor(porta=None, host="0.0.0.0"):
    return ThreadingHTTPServer((host, porta or int(os.getenv("API_PORT", "8000"))), Handler)


def main():
    garantir_tabelas()
    servidor = criar_servidor()
    print(f"[API] http://localhost:{servidor.server_port}  (dashboard em /)")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
