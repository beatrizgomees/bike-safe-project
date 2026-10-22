"""Fontes em memória: o MP recebe as bases pelo MQTT (não baixa do portal).

Têm a mesma interface dos collectors usados pelo CruzamentoAcidentesCiclovias
(buscar_dados / filtrar_acidentes_com_bike / buscar_trechos).
"""


class FonteLista:
    def __init__(self, dados):
        self.dados = dados

    def buscar_dados(self, *args, **kwargs):
        return self.dados


class FonteAcidentes(FonteLista):
    """Acidentes já marcados pelo SV (`_com_bike`)."""

    def filtrar_acidentes_com_bike(self, dados):
        return [d for d in dados if d.get("_com_bike")]


class FonteRede:
    def __init__(self, trechos):
        self.trechos = trechos

    def buscar_trechos(self):
        return self.trechos