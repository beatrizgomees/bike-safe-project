import math

RAIO_TERRA_M = 6371000.0

# Caixa aproximada do município do Recife (lat_min, lat_max, lon_min, lon_max).
# Serve para descartar resultados de geocodificação que caíram fora da cidade.
RECIFE_BBOX = (-8.16, -7.93, -35.02, -34.85)


def dentro_do_recife(lat, lon):
    lat_min, lat_max, lon_min, lon_max = RECIFE_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def haversine_m(lat1, lon1, lat2, lon2):
    """Distância em metros entre dois pontos (graus)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2

    return 2 * RAIO_TERRA_M * math.asin(math.sqrt(a))


def distancia_ponto_segmento_m(lat, lon, a, b):
    """Distância em metros do ponto (lat, lon) ao segmento a-b ((lat, lon) cada).

    Usa projeção plana local, que é precisa para distâncias de poucos km.
    """
    lat0 = math.radians(lat)
    m_lat = math.pi / 180 * RAIO_TERRA_M
    m_lon = m_lat * math.cos(lat0)

    def xy(p):
        return ((p[1] - lon) * m_lon, (p[0] - lat) * m_lat)

    ax, ay = xy(a)
    bx, by = xy(b)

    dx, dy = bx - ax, by - ay
    tamanho2 = dx * dx + dy * dy

    if tamanho2 == 0:
        return math.hypot(ax, ay)

    # projeção do ponto (origem) no segmento, limitada a [0, 1]
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / tamanho2))

    return math.hypot(ax + t * dx, ay + t * dy)


def distancia_ponto_linha_m(lat, lon, pontos):
    """Menor distância (m) do ponto a uma linha: lista de (lat, lon)."""
    if not pontos:
        return math.inf

    if len(pontos) == 1:
        return haversine_m(lat, lon, pontos[0][0], pontos[0][1])

    return min(
        distancia_ponto_segmento_m(lat, lon, pontos[i], pontos[i + 1])
        for i in range(len(pontos) - 1)
    )