import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.utils.geo import haversine_m

# Colunas da base de acidentes (dicionário de dados do portal) -> tabela `acidentes`
COLUNAS_ACIDENTES = [
    "protocolo", "data", "hora", "natureza", "situacao", "bairro", "endereco",
    "numero", "detalhe_endereco_acidente", "complemento", "bairro_cruzamento",
    "num_semaforo", "sentido_via", "tipo", "auto", "moto", "ciclom", "ciclista",
    "pedestre", "onibus", "caminhao", "viatura", "outros", "vitimas",
    "vitimas_fatais", "acidente_verificado", "tempo_clima", "situacao_semaforo",
    "sinalizacao", "condicao_via", "conservacao_via", "ponto_controle",
    "situacao_placa", "velocidade_max_via", "mao_direcao", "divisao_via1",
    "divisao_via2",
]
COLUNAS_NUMERICAS = {
    "auto", "moto", "ciclom", "ciclista", "pedestre", "onibus", "caminhao",
    "viatura", "outros", "vitimas", "vitimas_fatais",
}


def _chave(nome):
    """Nome de coluna comparável: minúsculo e sem espaços nas pontas."""
    return str(nome).strip().lower()


def _num(valor):
    try:
        return float(str(valor).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _conexao_do_env():
    """DATABASE_URL, ou monta a partir das variáveis POSTGRES_* do .env."""
    url = os.getenv("DATABASE_URL")

    if url:
        return url

    return (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'bikesafe')} "
        f"user={os.getenv('POSTGRES_USER', 'postgres')} "
        f"password={os.getenv('POSTGRES_PASSWORD', '')}"
    )


class Banco:
    """Grava e consulta o resultado do cruzamento no PostgreSQL.

    As tabelas NÃO são criadas aqui: rode antes o sql/schema.sql (setup.sh).
    Gravar de novo o mesmo registro atualiza a linha (não duplica).
    """

    def __init__(self, url=None):
        self.con = psycopg.connect(
            url or _conexao_do_env(), row_factory=dict_row, autocommit=True
        )

    # ------------------------------------------------------ bases completas
    def salvar_acidentes(self, registros):
        """Todos os acidentes da base (não só os com bicicleta). Chave: protocolo."""
        colunas = ", ".join(COLUNAS_ACIDENTES)
        marcadores = ", ".join(["%s"] * len(COLUNAS_ACIDENTES))
        atualiza = ", ".join(
            f"{c}=EXCLUDED.{c}" for c in COLUNAS_ACIDENTES if c != "protocolo"
        )
        sql = (f"INSERT INTO acidentes ({colunas}) VALUES ({marcadores}) "
               f"ON CONFLICT (protocolo) DO UPDATE SET {atualiza}")

        linhas = []

        for r in registros:
            r = {_chave(k): v for k, v in r.items()}

            if r.get("protocolo") in (None, ""):
                continue  # sem protocolo não há chave

            linha = []

            for c in COLUNAS_ACIDENTES:
                v = r.get(c)
                v = _num(v) if c in COLUNAS_NUMERICAS else (None if v in (None, "") else str(v))
                linha.append(str(r[c]) if c == "protocolo" else v)

            linhas.append(linha)

        with self.con.transaction():
            self.con.cursor().executemany(sql, linhas)

    def salvar_estacoes(self, estacoes):
        """estacoes: [{codigo, nome, localizacao, bairro, capacidade, lat, lon, coord_valida}].
        lat/lon podem ser None (estação sem coordenada)."""
        with self.con.transaction():
            for e in estacoes:
                self.con.execute(
                    """INSERT INTO estacoes_bike
                         (codigo, nome, localizacao, bairro, capacidade, lat, lon, coord_valida)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (codigo) DO UPDATE SET
                         nome=EXCLUDED.nome, localizacao=EXCLUDED.localizacao,
                         bairro=EXCLUDED.bairro, capacidade=EXCLUDED.capacidade,
                         lat=EXCLUDED.lat, lon=EXCLUDED.lon,
                         coord_valida=EXCLUDED.coord_valida""",
                    (str(e["codigo"]), e["nome"], e["localizacao"], e["bairro"],
                     e["capacidade"], e["lat"], e["lon"], e.get("coord_valida", True)),
                )

    def salvar_trechos(self, trechos_por_rede):
        """{rede: [trecho]} do GeoJSON. Substitui todos os trechos de cada rede informada."""
        with self.con.transaction():
            for rede, trechos in trechos_por_rede.items():
                self.con.execute("DELETE FROM ciclovia_trechos WHERE rede = %s", (rede,))

                for t in trechos:
                    pontos = t["pontos"]  # [(lat, lon), ...]
                    extensao = sum(
                        haversine_m(*pontos[i], *pontos[i + 1])
                        for i in range(len(pontos) - 1)
                    )
                    geometria = {
                        "type": "LineString",
                        "coordinates": [[lon, lat] for lat, lon in pontos],
                    }

                    self.con.execute(
                        """INSERT INTO ciclovia_trechos
                             (rede, rota, bairro, sentido, tipo, extensao_m, n_pontos,
                              geometria, propriedades)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (rede, t.get("rota"), t.get("bairro"), t.get("sentido"),
                         t.get("tipo"), round(extensao, 1), len(pontos),
                         Jsonb(geometria), Jsonb(t.get("propriedades"))),
                    )

    def salvar_malha(self, registros):
        """Malha cicloviária (CSV 'Detalhes da implantação'). Substitui a tabela inteira."""
        with self.con.transaction():
            self.con.execute("TRUNCATE malha_cicloviaria RESTART IDENTITY")

            for r in registros:
                self.con.execute(
                    """INSERT INTO malha_cicloviaria
                         (rota, tipologia, sentido, percurso, bairros, extensao, inauguracao)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (r.get("rota"), r.get("tipologia"), r.get("sentido"),
                     r.get("percurso"), r.get("bairros"), _num(r.get("extensao")),
                     None if r.get("inauguracao") in (None, "") else str(r.get("inauguracao"))),
                )

    # ------------------------------------------------------------ cruzamento

    def salvar(self, linhas, redes):
        """linhas: saída de CruzamentoAcidentesCiclovias.gerar(); redes: nomes das redes."""
        with self.con.transaction():
            for l in linhas:
                protocolo = str(l["protocolo"])

                self.con.execute(
                    """INSERT INTO acidentes_bike
                         (protocolo, data, hora, bairro, endereco, numero, natureza,
                          vitimas, vitimas_fatais, lat, lon, geo_precisao)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (protocolo) DO UPDATE SET
                         data=EXCLUDED.data, hora=EXCLUDED.hora, bairro=EXCLUDED.bairro,
                         endereco=EXCLUDED.endereco, numero=EXCLUDED.numero,
                         natureza=EXCLUDED.natureza, vitimas=EXCLUDED.vitimas,
                         vitimas_fatais=EXCLUDED.vitimas_fatais, lat=EXCLUDED.lat,
                         lon=EXCLUDED.lon, geo_precisao=EXCLUDED.geo_precisao""",
                    (protocolo, l["data"], l["hora"], l["bairro"], l["endereco"],
                     l["numero"], l["natureza"], _num(l["vitimas"]),
                     _num(l["vitimas_fatais"]), l["lat"], l["lon"], l["geo_precisao"]),
                )

                for rede in redes:
                    self.con.execute(
                        """INSERT INTO acidente_ciclovia
                             (protocolo, rede, rota, tipo, dist_m, na_ciclovia)
                           VALUES (%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (protocolo, rede) DO UPDATE SET
                             rota=EXCLUDED.rota, tipo=EXCLUDED.tipo,
                             dist_m=EXCLUDED.dist_m, na_ciclovia=EXCLUDED.na_ciclovia""",
                        (protocolo, rede, l[f"{rede}_rota"], l[f"{rede}_tipo"],
                         l[f"{rede}_dist_m"], l[f"na_ciclovia_{rede}"]),
                    )

    def salvar_acidente_estacao(self, linhas):
        """Estação mais próxima de cada acidente (linhas com as chaves estacao_*)."""
        with self.con.transaction():
            for l in linhas:
                if "estacao_dist_m" not in l:
                    continue

                self.con.execute(
                    """INSERT INTO acidente_estacao
                         (protocolo, estacao_codigo, dist_m, no_raio, estacoes_no_raio)
                       VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (protocolo) DO UPDATE SET
                         estacao_codigo=EXCLUDED.estacao_codigo, dist_m=EXCLUDED.dist_m,
                         no_raio=EXCLUDED.no_raio, estacoes_no_raio=EXCLUDED.estacoes_no_raio""",
                    (str(l["protocolo"]), l["estacao_codigo"], l["estacao_dist_m"],
                     l["estacao_no_raio"], l["estacoes_no_raio"]),
                )

    def consultar(self, sql, parametros=()):
        return list(self.con.execute(sql, parametros).fetchall())

    def fechar(self):
        self.con.close()