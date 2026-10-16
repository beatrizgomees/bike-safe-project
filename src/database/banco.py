import os

import psycopg
from psycopg.rows import dict_row


def _num(valor):
    try:
        return float(str(valor).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _url_do_env():
    """DATABASE_URL, ou monta a partir de POSTGRES_* (todas no .env)."""
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
    """PostgreSQL com o resultado do cruzamento.

    Tabelas:
      acidentes_bike      1 linha por acidente com ciclista (protocolo é a chave)
      acidente_ciclovia   1 linha por acidente x rede (permanente, operacional...)
    View:
      vw_acidentes_ciclovias   junção das duas, pronta para consulta

    Gravar de novo o mesmo protocolo atualiza a linha (não duplica).
    """

    def __init__(self, url=None):
        self.con = psycopg.connect(url or _url_do_env(), row_factory=dict_row)
        self._criar()

    def _criar(self):
        with self.con.transaction():
            self.con.execute("""
            CREATE TABLE IF NOT EXISTS acidentes_bike (
                protocolo      TEXT PRIMARY KEY,
                data           TEXT,
                hora           TEXT,
                bairro         TEXT,
                endereco       TEXT,
                numero         TEXT,
                natureza       TEXT,
                vitimas        DOUBLE PRECISION,
                vitimas_fatais DOUBLE PRECISION,
                lat            DOUBLE PRECISION,
                lon            DOUBLE PRECISION,
                geo_precisao   TEXT
            )""")

            self.con.execute("""
            CREATE TABLE IF NOT EXISTS acidente_ciclovia (
                protocolo    TEXT NOT NULL REFERENCES acidentes_bike(protocolo) ON DELETE CASCADE,
                rede         TEXT NOT NULL,
                rota         TEXT,
                tipo         TEXT,
                dist_m       DOUBLE PRECISION,
                na_ciclovia  BOOLEAN,
                PRIMARY KEY (protocolo, rede)
            )""")

            self.con.execute(
                "CREATE INDEX IF NOT EXISTS ix_acid_bairro ON acidentes_bike(bairro)")
            self.con.execute(
                "CREATE INDEX IF NOT EXISTS ix_acid_ciclo_rede "
                "ON acidente_ciclovia(rede, na_ciclovia)")

            self.con.execute("""
            CREATE OR REPLACE VIEW vw_acidentes_ciclovias AS
            SELECT a.*, c.rede, c.rota, c.tipo, c.dist_m, c.na_ciclovia
            FROM acidentes_bike a
            LEFT JOIN acidente_ciclovia c USING (protocolo)""")

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

    def consultar(self, sql, parametros=()):
        with self.con.transaction():
            return list(self.con.execute(sql, parametros).fetchall())

    def fechar(self):
        self.con.close()