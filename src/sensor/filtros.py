"""Funções de filtro do Sensor Virtual (SV).

Ficam num lugar só e são usadas pelo SV e pelos collectors.
"""
from src.utils.text_format import normalizar_texto


def _numero(valor):
    try:
        return float(str(valor if valor is not None else 0).replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def tem_ciclista(acidente):
    """True se o acidente envolveu ciclista (a base traz "1,0")."""
    return _numero(acidente.get("ciclista")) > 0


def filtrar_com_ciclista(acidentes):
    return [a for a in acidentes if tem_ciclista(a)]


def filtrar_por_bairros(registros, bairros, campo="bairro"):
    """Registros cujo bairro contém algum dos termos (sem acento/caixa)."""
    termos = [normalizar_texto(b) for b in ([bairros] if isinstance(bairros, str) else bairros)]

    return [
        r for r in registros
        if any(t in normalizar_texto(r.get(campo) or "") for t in termos)
    ]