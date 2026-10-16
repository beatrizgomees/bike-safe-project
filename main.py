from src.infra.docker_db import preparar_banco

# ---------------------------------------------------------------- ajustes
LIMITE = None      # None = todos os acidentes com bike. Comece com 50 para testar.
# -----------------------------------------------------------------------


def main():
    # 1) sobe o PostgreSQL no Docker e aplica o schema (se já estiver ok, é rápido)
    preparar_banco()

    # imports depois do preparar_banco: ele ajusta as variáveis de conexão
    from src.collector.acidentes_collector import AcidentesCollector
    from src.collector.ciclovias_collector import MalhaCicloviariaCollector
    from src.collector.estacoes_collector import EstacoesBikeCollector
    from src.collector.rotas_collector import (
        RotasPermanentesCollector,
        RotasOperacionaisCollector,
    )
    from src.processing.acidentes_ciclovias import CruzamentoAcidentesCiclovias
    from src.database.banco import Banco

    cruzamento = CruzamentoAcidentesCiclovias(
        acidentes=AcidentesCollector(),
        redes={
            "permanente": RotasPermanentesCollector(),
            "operacional": RotasOperacionaisCollector(),
        },
        raio_m=30,
        estacoes=EstacoesBikeCollector(),
        raio_estacao_m=300,
    )

    # 2) coleta e cruza
    linhas = cruzamento.gerar(limite=LIMITE)

    # 3) grava no banco
    banco = Banco()
    try:
        print("Bases completas:", cruzamento.salvar_dados_completos(
            banco, malha=MalhaCicloviariaCollector()
        ))

        cruzamento.salvar_banco(linhas, banco)
        print("Cruzamento:", cruzamento.resumo(linhas))

        print(banco.consultar("""
            SELECT rede,
                   COUNT(*) FILTER (WHERE na_ciclovia) AS em_ciclovia,
                   COUNT(*) AS total
            FROM acidente_ciclovia GROUP BY rede
        """))
    finally:
        banco.fechar()


if __name__ == "__main__":
    main()