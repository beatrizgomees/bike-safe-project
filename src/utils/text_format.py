import unicodedata
import re

def escolher_recurso(recursos, *preferencias):
    for alvo in preferencias:
        alvo = alvo.lower()
        for r in recursos:
            nome = (r.get("name") or "").lower()
            formato = (r.get("format") or "").lower()
            if alvo in nome or alvo == formato:
                return r
    return recursos[0] if recursos else None

def remover_acentos(txt):
    if not txt:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', txt)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])

def normalizar_texto(txt):
    if not txt:
        return ""
    return remover_acentos(txt).upper().strip()

BAIRROS_FILTRO = [
    # RPA 1 (11)
    "RECIFE",  # Bairro do Recife (Recife Antigo)
    "BOA VISTA",
    "CABANGA",
    "COELHOS",
    "ILHA DO LEITE",
    "ILHA JOANA BEZERRA",
    "PAISSANDU",
    "SANTO AMARO",
    "SANTO ANTONIO",
    "SAO JOSE",
    "SOLEDADE",
 
    # RPA 2 (18)
    "AGUA FRIA",
    "ALTO SANTA TEREZINHA",
    "ARRUDA",
    "BEBERIBE",
    "BOMBA DO HEMETERIO",
    "CAJUEIRO",
    "CAMPINA DO BARRETO",
    "CAMPO GRANDE",
    "DOIS UNIDOS",
    "ENCRUZILHADA",
    "FUNDAO",
    "HIPODROMO",
    "LINHA DO TIRO",
    "PEIXINHOS",
    "PONTO DE PARADA",
    "PORTO DA MADEIRA",
    "ROSARINHO",
    "TORREAO",
 
    # RPA 3 (29)
    "AFLITOS",
    "ALTO DO MANDU",
    "ALTO JOSE BONIFACIO",
    "ALTO JOSE DO PINHO",
    "APIPUCOS",
    "BREJO DA GUABIRABA",
    "BREJO DE BEBERIBE",
    "CASA AMARELA",
    "CASA FORTE",
    "CORREGO DO JENIPAPO",
    "DERBY",
    "DOIS IRMAOS",
    "ESPINHEIRO",
    "GRACAS",
    "GUABIRABA",
    "JAQUEIRA",
    "MACAXEIRA",
    "MANGABEIRA",
    "MONTEIRO",
    "MORRO DA CONCEICAO",
    "NOVA DESCOBERTA",
    "PARNAMIRIM",
    "PASSARINHO",
    "PAU-FERRO",
    "PAU FERRO",  # grafia alternativa nos dados
    "POCO DA PANELA",
    "SANTANA",
    "SITIO DOS PINTOS",
    "TAMARINEIRA",
    "VASCO DA GAMA",
 
    # RPA 4 (12)
    "CAXANGA",
    "CIDADE UNIVERSITARIA",
    "CORDEIRO",
    "ENGENHO DO MEIO",
    "ILHA DO RETIRO",
    "IPUTINGA",
    "MADALENA",
    "PRADO",
    "TORRE",
    "TORROES",
    "VARZEA",
    "ZUMBI",
 
    # RPA 5 (16)
    "AFOGADOS",
    "AREIAS",
    "BARRO",
    "BONGI",
    "CACOTE",
    "COQUEIRAL",
    "CURADO",
    "ESTANCIA",
    "JARDIM SAO PAULO",
    "JIQUIA",
    "MANGUEIRA",
    "MUSTARDINHA",
    "SAN MARTIN",
    "SANCHO",
    "TEJIPIO",
    "TOTO",
 
    # RPA 6 (8)
    "BOA VIAGEM",
    "BRASILIA TEIMOSA",
    "COHAB",
    "IBURA",
    "IMBIRIBEIRA",
    "IPSEP",
    "JORDAO",
    "PINA",
]