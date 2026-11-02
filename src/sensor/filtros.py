"""Filtros do Sensor Virtual: decidem quais acidentes interessam ao sistema."""
import unicodedata


def _num(valor):
    try:
        return float(str(valor).replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def _limpar(texto):
    """Maiúsculas, sem acento e sem espaços nas pontas (para comparar nomes)."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).upper().strip()


def tem_ciclista(acidente):
    """True se o acidente envolve ao menos um ciclista (coluna `ciclista` > 0)."""
    return _num(acidente.get("ciclista")) > 0


def filtrar_com_ciclista(acidentes):
    return [a for a in acidentes if tem_ciclista(a)]


def filtrar_por_bairros(acidentes, bairros):
    """Mantém só os acidentes dos bairros informados (sem diferenciar acento/maiúscula)."""
    alvo = {_limpar(b) for b in bairros}

    return [a for a in acidentes if _limpar(a.get("bairro")) in alvo]