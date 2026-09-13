"""
aulas_cbers.py — funções compartilhadas do curso "Geoprocessamento com
imagens CBERS-4A/WPM e Sentinel-2".
============================================================================

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Cada aula é um vídeo separado, e é normal alguém começar pela Aula 02 sem ter
rodado as anteriores. Este módulo é o **atalho**: ele refaz, de forma compacta,
o que as aulas anteriores produziram, para que qualquer notebook rode sozinho.

    from aulas_cbers import preparar_aula_02
    caminhos = preparar_aula_02()      # baixa a cena e refaz TOA/BOA + fusão

O código de ensino de cada etapa está **no notebook da própria aula**, com os
comentários e as explicações. Aqui a mesma coisa aparece condensada, sem a
narrativa — é atalho, não material didático.

CONVENÇÃO DE PASTAS (igual no Colab e no pixi local)
    data/raw/        bandas recortadas do STAC + XML de metadados   (Aula 00)
    data/interim/    reflectância, fusão, máscaras, S2, coregistro  (Aulas 01-03)
    data/processed/  mosaico final                                  (Aula 03)

CONVENÇÃO DE NOMES
    data/raw/rio_claro_<CENA_ID>_BAND<n>.tif
    data/interim/rgbcomp_<DATA>_<nivel>.tif             8 m, RGBN, refl x10000
    data/interim/pan_<DATA>_alinhada.tif                2 m, 1 banda
    data/interim/pansharpening_<DATA>_<nivel>.tif       2 m, RGBN, refl x10000
    data/interim/pansharpening_<DATA>_<nivel>_cloudmask_native.tif
    data/interim/pansharpening_<DATA>_<nivel>_masked.tif
    data/interim/S2_<DATA>_10m.tif                      6 bandas int16
    data/interim/S2_<DATA>_SR2p5m.tif                   4 bandas float32
    data/processed/mosaico_<DATA>_gapfilled.tif

TODAS as etapas trabalham na MESMA bounding box e, da Aula 01 em diante, na
mesma grade de 2 m. É isso que faz o coregistro do AROSICS (Aula 03) fechar.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Parâmetros do tutorial
# ---------------------------------------------------------------------------

# bbox do tutorial, em EPSG:4326 e na ordem [oeste, sul, leste, norte].
# Mude aqui (e SÓ aqui) para rodar em outra área — mas mude em todas as aulas
# ao mesmo tempo, senão o coregistro da Aula 03 não tem o que casar.
AOI_BBOX = [-47.625969, -22.467835, -47.498227, -22.344048]
AOI_NOME = "rio_claro"

# Cena de referência do curso: Rio Claro com nuvem em parte da AOI. É essa
# nuvem que a Aula 02 detecta e a Aula 03 preenche.
CENA_PADRAO = "CBERS_4A_WPM_20260301_203_141_L4"

STAC_URL = "https://data.inpe.br/bdc/stac/v1/"
COLECAO = "CB4A-WPM-L4-DN-1"

# asset do STAC -> apelido
BANDAS = {"BAND1": "blue", "BAND2": "green", "BAND3": "red",
          "BAND4": "nir", "BAND0": "pan"}

# numeração nativa do WPM -> papel espectral
BANDAS_NATIVAS = {1: "azul", 2: "verde", 3: "vermelho", 4: "nir"}
ORDEM_SAIDA = [3, 2, 1, 4]                                   # RGBN
NOMES_SAIDA = ["red", "green", "blue", "nir"]

ESCALA = 10000          # reflectância 0-1 gravada como int16 (igual ao S2 L2A)
NODATA = -9999
SATURACAO = 1023        # o WPM é de 10 bits guardado em int16

# Faixa física da reflectância gravada. Reflectância NEGATIVA não existe: o que
# aparece abaixo de zero é ruído da correção atmosférica e undershoot da fusão
# em alvo escuro. O produto sai com piso em 0; o NODATA (-9999) continua sendo
# outro valor, então pixel ceifado permanece VÁLIDO, não vira buraco.
PISO_REFLECTANCIA = 0.0
TETO_REFLECTANCIA = 1.6

# pesos do pansharpening Gram-Schmidt (padrão do ArcGIS Pro para sensor UNKNOWN).
# Só entram como plano B: por padrão a intensidade é estimada por REGRESSÃO da
# própria PAN sobre as bandas MS (GSA, Aiazzi et al. 2007) — ver gram_schmidt().
PESOS_GS = {"red": 0.166, "green": 0.167, "blue": 0.167, "nir": 0.5}

_BASE = Path("data")


# ---------------------------------------------------------------------------
# Ambiente e pastas
# ---------------------------------------------------------------------------

def no_colab() -> bool:
    return "google.colab" in sys.modules


def definir_base(caminho) -> Path:
    """Muda a raiz dos dados. No Colab, aponte para o Drive:

        definir_base("/content/drive/MyDrive/geoproc/data")
    """
    global _BASE
    _BASE = Path(caminho)
    return _BASE


def pastas() -> dict:
    """Cria (se preciso) e devolve as pastas de dados."""
    p = {"base": _BASE, "raw": _BASE / "raw",
         "interim": _BASE / "interim", "processed": _BASE / "processed"}
    for k, v in p.items():
        v.mkdir(parents=True, exist_ok=True)
    return p


def configurar_gdal() -> None:
    """Ajustes de leitura remota. Chame ANTES de importar o rasterio."""
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
    os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
    os.environ.setdefault("GDAL_CACHEMAX", "512")


def data_da_cena(cena_id: str) -> str:
    """'CBERS_4A_WPM_20260301_203_141_L4' -> '20260301'."""
    m = re.search(r"_(\d{8})_", cena_id)
    if not m:
        raise ValueError(f"não achei a data no id da cena: {cena_id}")
    return m.group(1)


# ---------------------------------------------------------------------------
# Leitura de janelas (usada na aquisição e nos recortes)
# ---------------------------------------------------------------------------

def reprojetar_bounds(bounds, de="EPSG:4326", para=None):
    from pyproj import Transformer
    tr = Transformer.from_crs(de, para, always_xy=True)
    minx, miny = tr.transform(bounds[0], bounds[1])
    maxx, maxy = tr.transform(bounds[2], bounds[3])
    return (minx, miny, maxx, maxy)


def janela_da_aoi(src, bbox):
    """Janela em pixels correspondente ao bbox (EPSG:4326), limitada à cena."""
    from rasterio.windows import Window, from_bounds
    b = reprojetar_bounds(bbox, "EPSG:4326", src.crs)
    j = from_bounds(*b, src.transform).round_offsets().round_lengths()
    c0, r0 = max(0, int(j.col_off)), max(0, int(j.row_off))
    c1 = min(src.width, int(j.col_off + j.width))
    r1 = min(src.height, int(j.row_off + j.height))
    if c1 <= c0 or r1 <= r0:
        raise ValueError("a AOI não intersecta esta cena.")
    return Window(c0, r0, c1 - c0, r1 - r0)


def stretch(array, low=2, high=98):
    """Contraste por percentil (0-1), ignorando nodata."""
    d = np.ma.filled(np.asarray(array, dtype="float64"), np.nan)
    v = d[np.isfinite(d) & (d > 0)]
    if v.size == 0:
        return np.zeros_like(d)
    lo, hi = np.percentile(v, [low, high])
    if hi <= lo:
        hi = lo + 1
    return np.clip((d - lo) / (hi - lo), 0, 1)


# ---------------------------------------------------------------------------
# Aula 00 (atalho) — aquisição da cena CBERS-4A/WPM via STAC do INPE
# ---------------------------------------------------------------------------

def buscar_cenas(bbox=None, intervalo="2025-01-01/2026-12-31", colecao=COLECAO):
    """Devolve (items, DataFrame) das cenas que cruzam o bbox."""
    import pandas as pd
    from pystac_client import Client

    bbox = bbox or AOI_BBOX
    itens = list(Client.open(STAC_URL).search(
        collections=[colecao], bbox=bbox, datetime=intervalo).items())
    linhas = [{"idx": i, "id": it.id,
               "data": str(it.properties.get("datetime", ""))[:10],
               "orbita_ponto": f"{it.properties.get('path', '?')}_"
                               f"{it.properties.get('row', '?')}",
               "bandas": sum(1 for k in BANDAS if k in it.assets)}
              for i, it in enumerate(itens)]
    return itens, pd.DataFrame(linhas)


def diagnosticar_aoi(item, bbox=None, max_dim=150, limiar=0.7 * SATURACAO):
    """Cobertura válida e nuvem estimada SOBRE A AOI (leitura reduzida)."""
    import rasterio
    from rasterio.windows import Window

    bbox = bbox or AOI_BBOX
    leituras = []
    for asset in ("BAND1", "BAND4"):
        with rasterio.open(item.assets[asset].href) as src:
            j = janela_da_aoi(src, bbox)
            fator = max(1.0, max(j.width, j.height) / max_dim)
            forma = (max(1, int(j.height / fator)), max(1, int(j.width / fator)))
            leituras.append(src.read(1, window=j, out_shape=forma).astype("float32"))
    azul, nir = leituras

    validos = (azul > 0) & (nir > 0)
    if not validos.any():
        return {"cobertura_aoi_%": 0.0, "nuvens_est_%": np.nan, "brilho_p98": np.nan}
    nuvem = validos & (azul > limiar) & (nir < 1.6 * azul)
    return {"cobertura_aoi_%": round(100 * validos.sum() / validos.size, 1),
            "nuvens_est_%": round(100 * nuvem.sum() / validos.sum(), 1),
            "brilho_p98": int(np.percentile(azul[validos], 98))}


def _exportar_banda(href, bbox, destino: Path) -> Path:
    import rasterio
    from rasterio.windows import transform as window_transform

    with rasterio.open(href) as src:
        j = janela_da_aoi(src, bbox)
        dados = src.read(1, window=j)
        alt, larg = int(j.height), int(j.width)
        perfil = src.profile.copy()
        perfil.update(driver="GTiff", height=alt, width=larg, count=1,
                      transform=window_transform(j, src.transform),
                      compress="deflate", predictor=2)
        if alt >= 512 and larg >= 512:
            perfil.update(tiled=True, blockxsize=512, blockysize=512)
        else:
            perfil.update(tiled=False)
            perfil.pop("blockxsize", None)
            perfil.pop("blockysize", None)
    with rasterio.open(destino, "w", **perfil) as dst:
        dst.write(dados, 1)
    return destino


def arquivos_da_cena(cena_id=CENA_PADRAO, pasta=None) -> dict:
    """Mapeia asset -> arquivo já baixado em data/raw (vazio se não houver)."""
    pasta = Path(pasta) if pasta else pastas()["raw"]
    achados = {}
    for asset in BANDAS:
        cands = sorted(pasta.glob(f"*{cena_id}_{asset}.tif"))
        if cands:
            achados[asset] = cands[0]
    return achados


def baixar_cena(cena_id=CENA_PADRAO, bbox=None, destino=None, com_xml=True,
                intervalo=None) -> dict:
    """Baixa as 5 bandas da cena recortadas ao bbox (+ os XML). Idempotente."""
    import requests

    bbox = bbox or AOI_BBOX
    destino = Path(destino) if destino else pastas()["raw"]
    ja = arquivos_da_cena(cena_id, destino)
    if len(ja) == len(BANDAS):
        print(f"Cena já baixada em {destino} — nada a fazer.")
        return ja

    data = data_da_cena(cena_id)
    if intervalo is None:
        ano, mes, dia = data[:4], data[4:6], data[6:]
        intervalo = f"{ano}-{mes}-{dia}/{ano}-{mes}-{dia}"
    itens, _ = buscar_cenas(bbox, intervalo)
    item = next((i for i in itens if i.id == cena_id), None)
    if item is None:
        raise LookupError(
            f"cena {cena_id} não encontrada no STAC para {intervalo}.\n"
            "Rode o notebook da Aula 00 para escolher outra cena e passe o id "
            "em CENA_ID.")

    saidas = {}
    print(f"Baixando {cena_id} recortada ao bbox {bbox}:")
    for asset in BANDAS:
        if asset not in item.assets:
            print(f"  ! {asset} não existe nesta cena — pulando")
            continue
        base = destino / f"{AOI_NOME}_{cena_id}_{asset}"
        if not base.with_suffix(".tif").exists():
            _exportar_banda(item.assets[asset].href, bbox,
                            base.with_suffix(".tif"))
        saidas[asset] = base.with_suffix(".tif")
        print(f"  {base.name}.tif")
        if com_xml and f"{asset}_xml" in item.assets and \
                not base.with_suffix(".xml").exists():
            r = requests.get(item.assets[f"{asset}_xml"].href, timeout=120)
            r.raise_for_status()
            base.with_suffix(".xml").write_bytes(r.content)
    return saidas


# ---------------------------------------------------------------------------
# Aula 01 (atalho) — DN -> radiância -> reflectância TOA/BOA
# ---------------------------------------------------------------------------

def _local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _achar(no, *nomes, obrigatorio=True):
    alvo = {n.lower() for n in nomes}
    for el in no.iter():
        if _local(el.tag).lower() in alvo:
            return el
    if obrigatorio:
        raise ValueError(f"elemento ausente no XML: {'/'.join(nomes)}")
    return None


def _texto(no, *nomes, obrigatorio=True):
    el = _achar(no, *nomes, obrigatorio=obrigatorio)
    if el is None or not (el.text or "").strip():
        if obrigatorio:
            raise ValueError(f"campo vazio no XML: {'/'.join(nomes)}")
        return None
    return el.text.strip()


def ler_xml(cena_id=CENA_PADRAO, pasta=None) -> dict:
    """Coeficientes de calibração e geometria solar, do XML baixado na Aula 00.

    O XML descreve a CENA INTEIRA (não o recorte) e traz o bloco
    <absoluteCalibrationCoefficient> com um ganho por banda, além da posição do
    Sol no momento da passagem. É o que transforma DN em grandeza física.
    """
    import xml.etree.ElementTree as ET

    pasta = Path(pasta) if pasta else pastas()["raw"]
    candidatos = sorted(pasta.glob(f"*{cena_id}*.xml"))
    if not candidatos:
        raise FileNotFoundError(
            f"nenhum XML de {cena_id} em {pasta}. A Aula 00 baixa os XML junto "
            "com as bandas (com_xml=True).")

    falhas = []
    for cam in candidatos:
        try:
            raiz = ET.parse(cam).getroot()
            bloco = _achar(raiz, "absoluteCalibrationCoefficient")
            coefs = {}
            for b in bloco:
                if _local(b.tag).lower() != "band":
                    continue
                nome = b.get("name") or b.get("number") or b.get("id")
                if nome is None or b.text is None:
                    continue
                try:
                    coefs[int(nome)] = float(b.text)
                except ValueError:
                    continue
            faltando = [n for n in BANDAS_NATIVAS if n not in coefs]
            if faltando:
                raise ValueError(f"sem coeficiente para as bandas {faltando}")

            sol = _achar(raiz, "sunPosition")
            elev = float(_texto(sol, "elevation"))
            azim = float(_texto(sol, "sunAzimuth", "azimuth"))
            vis = _achar(raiz, "viewing", obrigatorio=False)
            momento = datetime.fromisoformat(
                _texto(vis if vis is not None else raiz, "center"))
            img = _achar(raiz, "image", obrigatorio=False) or raiz
            return {"xml": str(cam), "coeficientes": coefs,
                    "elevacao_solar": elev, "azimute_solar": azim,
                    "zenite_solar": 90.0 - elev,
                    "datahora": momento.isoformat(),
                    "data": momento.date().isoformat(),
                    "orbita": _texto(img, "path", obrigatorio=False),
                    "ponto": _texto(img, "row", obrigatorio=False),
                    "nivel_produto": _texto(img, "level", obrigatorio=False),
                    "pixel_m": float(_texto(img, "horizontalPixelSize") or 0)}
        except Exception as e:
            falhas.append(f"    {cam.name}: {e}")
    raise ValueError("nenhum XML utilizável. Tentados:\n" + "\n".join(falhas))


def ler_esun(caminho=None) -> dict:
    """ESUN por banda nativa (config/esun_wpm.json)."""
    cam = Path(caminho) if caminho else Path("config") / "esun_wpm.json"
    if not cam.exists():
        raise FileNotFoundError(
            f"{cam} não encontrado. Ele fica em colab/config/ no repositório.")
    cfg = json.loads(cam.read_text(encoding="utf-8"))
    return {int(k): float(v) for k, v in cfg["esun"].items()}


def distancia_terra_sol(quando: date) -> float:
    """Distância Terra-Sol em UA, pela aproximação padrão por dia juliano."""
    doy = (quando - date(quando.year, 1, 1)).days + 1
    return 1.0 - 0.01674 * math.cos(math.radians(0.98563 * (doy - 4)))


def dn_para_radiancia(dn, coef):
    """L = DN * absoluteCalibrationCoefficient  [W m-2 sr-1 um-1], offset = 0."""
    return dn.astype("float32") * np.float32(coef)


def radiancia_para_toa(L, esun, d, cos_z):
    """rho_TOA = (pi * d^2 * L) / (ESUN * cos(theta_z))."""
    return (math.pi * d * d * L) / np.float32(esun * cos_z)


def tem_6s() -> bool:
    """True se o Py6S E o executável 6S estiverem disponíveis.

    São duas coisas: `pip install py6s` instala só o invólucro Python. O 6S em
    si é um executável Fortran, que vem do conda-forge (pacote `sixs`).
    """
    try:
        from Py6S import SixS
    except Exception:
        return False
    try:
        return bool(SixS().sixs_path)
    except Exception:
        return False


def coeficientes_6s(meta: dict, atm: dict, banda_nativa: int) -> tuple:
    """Coeficientes (xa, xb, xc) do 6S para uma banda.

        y   = xa * L - xb
        rho = y / (1 + xc * y)
    """
    from Py6S import (SixS, Geometry, AtmosProfile, AeroProfile, Altitudes,
                      Wavelength, AtmosCorr)

    s = SixS()
    s.geometry = Geometry.User()
    s.geometry.solar_z = meta["zenite_solar"]
    s.geometry.solar_a = meta["azimute_solar"]
    s.geometry.view_z = atm.get("angulo_visada", 0.0)
    s.geometry.view_a = atm.get("azimute_visada", 0.0)
    d = datetime.fromisoformat(meta["datahora"])
    s.geometry.month, s.geometry.day = d.month, d.day
    s.atmos_profile = AtmosProfile.UserWaterAndOzone(
        atm["vapor_agua_gcm2"], atm["ozonio_cmatm"])
    s.aero_profile = AeroProfile.PredefinedType(
        getattr(AeroProfile, atm.get("perfil_aerossol", "Continental")))
    s.aot550 = atm["aot550"]
    s.altitudes = Altitudes()
    s.altitudes.set_target_custom_altitude(atm["altitude_alvo_km"])
    s.altitudes.set_sensor_satellite_level()
    ini, fim = atm["faixas_espectrais"][str(banda_nativa)]
    s.wavelength = Wavelength(ini, fim)
    s.atmos_corr = AtmosCorr.AtmosCorrLambertianFromReflectance(-0.1)
    s.run()
    return (s.outputs.coef_xa, s.outputs.coef_xb, s.outputs.coef_xc)


def converter_reflectancia(cena_id=CENA_PADRAO, nivel="boa", atmosfera=None,
                           destino=None, esun=None) -> Path:
    """DN -> reflectância (TOA ou BOA) e composição RGBN de 8 m.

    Saída: data/interim/rgbcomp_<DATA>_<nivel>.tif, int16, reflectância x10000,
    nodata -9999, bandas rotuladas red/green/blue/nir.
    """
    import rasterio
    from rasterio.enums import ColorInterp

    destino = Path(destino) if destino else pastas()["interim"]
    data = data_da_cena(cena_id)
    saida = destino / f"rgbcomp_{data}_{nivel}.tif"
    if saida.exists():
        print(f"{saida.name} já existe — nada a fazer.")
        return saida

    arqs = arquivos_da_cena(cena_id)
    faltando = [a for a in ("BAND1", "BAND2", "BAND3", "BAND4") if a not in arqs]
    if faltando:
        raise FileNotFoundError(f"bandas ausentes em data/raw: {faltando}. "
                                "Rode baixar_cena() ou a Aula 00.")

    meta = ler_xml(cena_id)
    esun = esun or ler_esun()
    quando = date.fromisoformat(meta["data"])
    d = distancia_terra_sol(quando)
    cos_z = math.cos(math.radians(meta["zenite_solar"]))

    dn, perfil, forma = {}, None, None
    for n in sorted(BANDAS_NATIVAS):
        with rasterio.open(arqs[f"BAND{n}"]) as src:
            if perfil is None:
                perfil, forma = src.profile.copy(), (src.height, src.width)
            elif (src.height, src.width) != forma:
                raise ValueError("as bandas MS não têm a mesma grade.")
            dn[n] = src.read(1)

    # nodata: zero em QUALQUER banda. Em reflectância TOA o azul nunca é zero
    # sobre terra (o espalhamento Rayleigh garante sinal até na sombra), então
    # um zero isolado é artefato de borda, não alvo escuro.
    zeros = np.zeros(forma, dtype=bool)
    for n in dn:
        zeros |= (dn[n] == 0)
    valido = ~zeros

    atm = None
    if nivel == "boa":
        cam = Path(atmosfera) if atmosfera else Path("config") / "atmosfera_rio_claro.json"
        atm = json.loads(Path(cam).read_text(encoding="utf-8"))

    refl = {}
    for n in sorted(BANDAS_NATIVAS):
        L = dn_para_radiancia(dn[n], meta["coeficientes"][n])
        r = radiancia_para_toa(L, esun[n], d, cos_z)
        if nivel == "boa":
            xa, xb, xc = coeficientes_6s(meta, atm, n)
            y = xa * L - xb
            r = y / (1.0 + xc * y)
        refl[BANDAS_NATIVAS[n]] = r

    perfil.update(count=4, dtype="int16", nodata=NODATA, compress="deflate",
                  predictor=2, tiled=True, blockxsize=512, blockysize=512,
                  BIGTIFF="IF_SAFER")
    nativo = {1: "azul", 2: "verde", 3: "vermelho", 4: "nir"}
    piso_esc, teto_esc = PISO_REFLECTANCIA * ESCALA, TETO_REFLECTANCIA * ESCALA
    with rasterio.open(saida, "w", **perfil) as dst:
        for i, n in enumerate(ORDEM_SAIDA, start=1):
            esc = np.clip(np.rint(refl[nativo[n]] * ESCALA), piso_esc, teto_esc)
            dst.write(np.where(valido, esc, NODATA).astype("int16"), i)
            dst.set_band_description(i, NOMES_SAIDA[i - 1])
        dst.colorinterp = [ColorInterp.red, ColorInterp.green,
                           ColorInterp.blue, ColorInterp.undefined]
        dst.update_tags(ORDEM_BANDAS="RGBN", NIVEL=nivel.upper(),
                        FATOR_ESCALA=str(ESCALA), CENA=cena_id,
                        DATA=meta["data"])
    print(f"Escrito: {saida}")
    return saida


# ---------------------------------------------------------------------------
# Aula 01 (atalho) — alinhamento MS/PAN e fusão Gram-Schmidt
# ---------------------------------------------------------------------------

def alinhar_ms_pan(ms_path, pan_path):
    """Devolve MS (8 m) e PAN (2 m) na MESMA extensão, com razão exata de 4:1.

    A Aula 00 recorta MS e PAN em janelas calculadas separadamente, cada uma
    arredondada na sua própria grade — então as duas podem ficar deslocadas em
    alguns metros. O Gram-Schmidt exige razão inteira e origem coincidente:
    sem isso a fusão inventa um deslocamento subpixel que contamina tudo o que
    vem depois, inclusive o coregistro da Aula 03.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import Affine
    from rasterio.warp import reproject
    from rasterio.windows import Window, from_bounds

    with rasterio.open(ms_path) as ms, rasterio.open(pan_path) as pan:
        if ms.crs != pan.crs:
            raise ValueError(f"CRS diferentes: MS {ms.crs} x PAN {pan.crs}")
        res_ms, res_pan = ms.transform.a, pan.transform.a
        fator = int(round(res_ms / res_pan))
        if abs(res_ms / res_pan - fator) > 1e-6:
            raise ValueError(f"razão MS/PAN não inteira: {res_ms / res_pan}")

        # extensão comum, encaixada na grade do MS (múltiplos de 8 m)
        b_ms, b_pan = ms.bounds, pan.bounds
        minx, miny = max(b_ms.left, b_pan.left), max(b_ms.bottom, b_pan.bottom)
        maxx, maxy = min(b_ms.right, b_pan.right), min(b_ms.top, b_pan.top)
        if maxx <= minx or maxy <= miny:
            raise ValueError("MS e PAN não se sobrepõem.")
        j = from_bounds(minx, miny, maxx, maxy, ms.transform)
        c0, r0 = math.ceil(j.col_off), math.ceil(j.row_off)
        c1 = math.floor(j.col_off + j.width)
        r1 = math.floor(j.row_off + j.height)
        larg, alt = c1 - c0, r1 - r0
        t_ms = ms.transform * Affine.translation(c0, r0)
        ms_arr = ms.read(window=Window(c0, r0, larg, alt))
        descr = ms.descriptions
        crs = ms.crs
        nod_ms = ms.nodata

        # grade da PAN: mesma origem, resolução 4x menor, tamanho 4x maior
        t_pan = t_ms * Affine.scale(1 / fator)
        pan_arr = np.zeros((alt * fator, larg * fator), dtype="float32")
        reproject(source=rasterio.band(pan, 1), destination=pan_arr,
                  src_transform=pan.transform, src_crs=pan.crs,
                  dst_transform=t_pan, dst_crs=crs,
                  resampling=Resampling.bilinear,
                  src_nodata=pan.nodata, dst_nodata=0)

    print(f"MS  alinhado: {larg} x {alt} px @ {res_ms:g} m")
    print(f"PAN alinhada: {larg * fator} x {alt * fator} px @ {res_pan:g} m")
    return ms_arr, pan_arr, t_ms, t_pan, crs, nod_ms, fator


def intensidade_por_regressao(ms_lr, pan, valido_lr, fator):
    """Coeficientes da intensidade simulada, estimados por regressão (GSA).

    ms_lr     : (N, h, w) MS na resolução NATIVA (8 m)
    pan       : (h*fator, w*fator) pancromática na grade fina
    valido_lr : (h, w) máscara de pixel válido do MS

    O Gram-Schmidt clássico simula a pancromática com pesos fixos
    (I = 0,166 R + 0,167 G + 0,167 B + 0,5 NIR). Esses pesos são um chute sobre
    a resposta espectral do sensor: I acaba dominado pelo NIR e fica muito
    diferente da PAN de verdade. Aí `delta = PAN - I` deixa de ser só o detalhe
    de alta frequência e passa a carregar o descasamento espectral inteiro — que
    é injetado nas bandas e joga os alvos escuros (água, sombra) para baixo de
    zero.

    A correção é a de Aiazzi et al. (2007): degradar a PAN para a grade do MS e
    achar por mínimos quadrados os coeficientes que MELHOR reproduzem a PAN a
    partir das bandas MS. Com isso `delta` volta a ser detalhe de verdade.

    Devolve (alpha, r2, pan_lp), com alpha = [a_red, a_green, a_blue, a_nir, a0].
    """
    n_bandas, h, w = ms_lr.shape
    pan_lp = (pan[:h * fator, :w * fator]
              .reshape(h, fator, w, fator).mean(axis=(1, 3)))
    m = valido_lr & (pan_lp > 0)
    if m.sum() < 100:
        raise ValueError("pixels válidos insuficientes para a regressão da PAN.")
    X = np.column_stack([ms_lr[i][m].astype("float64") for i in range(n_bandas)]
                        + [np.ones(int(m.sum()))])
    y = pan_lp[m].astype("float64")
    alpha, *_ = np.linalg.lstsq(X, y, rcond=None)
    r2 = float(1.0 - (y - X @ alpha).var() / max(y.var(), 1e-12))
    return alpha, r2, pan_lp


def gram_schmidt(ms, pan, pesos=None, valido=None, alpha=None):
    """Pansharpening Gram-Schmidt (substituição de componente).

    ms    : (N, h, w) já reamostrado para a grade da PAN
    pan   : (h, w)
    alpha : coeficientes de `intensidade_por_regressao` (modo GSA, recomendado).
            Sem eles, cai nos pesos fixos de `PESOS_GS` — o GS clássico.
    Devolve (N, h, w) na mesma escala radiométrica do MS.

    O método simula uma pancromática a partir das bandas MS, casa média e desvio
    da PAN real com essa simulada, e distribui a diferença entre as bandas com um
    ganho por banda. É por isso que o GS não se importa se a PAN está em DN ou em
    reflectância: qualquer escala multiplicativa da PAN é absorvida no casamento.
    """
    ms = ms.astype("float32")
    pan = pan.astype("float32")
    if valido is None:
        valido = np.ones(pan.shape, dtype=bool)

    if alpha is not None:
        a = np.asarray(alpha, dtype="float32")
        I = np.tensordot(a[:-1], ms, axes=(0, 0)) + a[-1]   # intensidade GSA
    else:
        pesos = pesos or PESOS_GS
        w = np.array([pesos[n] for n in NOMES_SAIDA], dtype="float32")
        w = w / w.sum()
        I = np.tensordot(w, ms, axes=(0, 0))                # pan simulada

    # As estatísticas saem de uma amostra: numa cena de 2 m a AOI inteira tem
    # dezenas de milhões de pixels, e média/desvio/covariância convergem muito
    # antes disso. Semente fixa para o resultado ser reproduzível.
    idx = np.flatnonzero(valido.ravel())
    if idx.size == 0:
        raise ValueError("nenhum pixel válido para ajustar o Gram-Schmidt.")
    if idx.size > 2_000_000:
        idx = np.random.default_rng(42).choice(idx, 2_000_000, replace=False)
    pa, ia = pan.ravel()[idx].astype("float64"), I.ravel()[idx].astype("float64")

    mp, sp = pa.mean(), pa.std()
    mi, si = ia.mean(), ia.std()
    pan_ajustada = (pan - mp) * (si / max(sp, 1e-9)) + mi   # casamento com GS1

    delta = pan_ajustada - I
    var_I = max(float(ia.var()), 1e-9)
    ia_c = ia - mi
    saida = np.empty_like(ms)
    for i in range(ms.shape[0]):
        bi = ms[i].ravel()[idx].astype("float64")
        ganho = float(np.dot(bi - bi.mean(), ia_c) / ia_c.size) / var_I
        saida[i] = ms[i] + ganho * delta
    return saida


def fundir(cena_id=CENA_PADRAO, nivel="boa", destino=None) -> Path:
    """rgbcomp (8 m) + PAN (2 m) -> pansharpening_<DATA>_<nivel>.tif (2 m)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    destino = Path(destino) if destino else pastas()["interim"]
    data = data_da_cena(cena_id)
    saida = destino / f"pansharpening_{data}_{nivel}.tif"
    if saida.exists():
        print(f"{saida.name} já existe — nada a fazer.")
        return saida

    rgbcomp = destino / f"rgbcomp_{data}_{nivel}.tif"
    if not rgbcomp.exists():
        rgbcomp = converter_reflectancia(cena_id, nivel, destino=destino)
    pan_path = arquivos_da_cena(cena_id).get("BAND0")
    if pan_path is None:
        raise FileNotFoundError("BAND0 (pancromática) ausente em data/raw.")

    ms, pan, t_ms, t_pan, crs, nod, fator = alinhar_ms_pan(rgbcomp, pan_path)

    ms_f = ms.astype("float32")
    valido_ms = ~np.all(ms == (nod if nod is not None else NODATA), axis=0)
    ms_f[:, ~valido_ms] = np.nan

    alt, larg = pan.shape
    ms_up = np.empty((ms.shape[0], alt, larg), dtype="float32")
    for i in range(ms.shape[0]):
        reproject(source=np.nan_to_num(ms_f[i], nan=0.0), destination=ms_up[i],
                  src_transform=t_ms, src_crs=crs,
                  dst_transform=t_pan, dst_crs=crs,
                  resampling=Resampling.cubic)
    val_up = np.empty((alt, larg), dtype="float32")
    reproject(source=valido_ms.astype("float32"), destination=val_up,
              src_transform=t_ms, src_crs=crs, dst_transform=t_pan,
              dst_crs=crs, resampling=Resampling.bilinear)
    valido = (val_up > 0.999) & (pan > 0)

    # intensidade por regressão (GSA): sem isso o delta injetado carrega o
    # descasamento espectral inteiro e afunda os alvos escuros em negativo
    alpha, r2, _ = intensidade_por_regressao(ms.astype("float32"), pan,
                                             valido_ms, fator)
    print(f"intensidade por regressão (GSA): R² = {r2:.4f}")
    fus = gram_schmidt(ms_up, pan, valido=valido, alpha=alpha)

    piso_esc, teto_esc = PISO_REFLECTANCIA * ESCALA, TETO_REFLECTANCIA * ESCALA
    perfil = dict(driver="GTiff", dtype="int16", count=4, height=alt, width=larg,
                  transform=t_pan, crs=crs, nodata=NODATA, compress="deflate",
                  predictor=2, tiled=True, blockxsize=512, blockysize=512,
                  BIGTIFF="IF_SAFER", interleave="band")
    with rasterio.open(saida, "w", **perfil) as dst:
        for i in range(4):
            frac = float((fus[i][valido] < piso_esc).mean())
            b = np.clip(np.rint(fus[i]), piso_esc, teto_esc)
            dst.write(np.where(valido, b, NODATA).astype("int16"), i + 1)
            dst.set_band_description(i + 1, NOMES_SAIDA[i])
            print(f"  {NOMES_SAIDA[i]:<6} ceifado no piso: {frac:.3%}")
        dst.update_tags(ORDEM_BANDAS="RGBN", NIVEL=nivel.upper(),
                        FATOR_ESCALA=str(ESCALA), METODO="Gram-Schmidt (GSA)",
                        PESOS=json.dumps(PESOS_GS), CENA=cena_id,
                        FAIXA_REFLECTANCIA=f"[{PISO_REFLECTANCIA}, {TETO_REFLECTANCIA}]")
    print(f"Escrito: {saida}")
    return saida


def carimbar_bandas(caminho, ordem="RGBN") -> tuple:
    """Grava os nomes das bandas dentro do GeoTIFF, sem reescrever os pixels."""
    import rasterio
    nomes = {"RGBN": ["red", "green", "blue", "nir"],
             "BGRN": ["blue", "green", "red", "nir"]}[ordem]
    with rasterio.open(caminho, "r+") as src:
        for i, n in enumerate(nomes[:src.count], start=1):
            src.set_band_description(i, n)
        atual = src.descriptions
    print(f"{Path(caminho).name}: {atual}")
    return atual


# ---------------------------------------------------------------------------
# Aula 02 (atalho) — máscara de nuvem com OmniCloudMask
# ---------------------------------------------------------------------------

CLASSES_OCM = {0: "clear", 1: "thick_cloud", 2: "thin_cloud", 3: "cloud_shadow"}
NODATA_MASCARA = 255


def mascara_nuvens(entrada, destino=None, detect_res=10.0,
                   banda_red=1, banda_green=2, banda_nir=4,
                   patch_size=1000, patch_overlap=300,
                   aplicar=True) -> dict:
    """Roda o OmniCloudMask e grava máscara, máscara clear e imagem mascarada.

    Entrada em ordem RGBN (padrão do pansharpening da Aula 01): red=1, green=2,
    nir=4.
    """
    import rasterio
    from rasterio import Affine
    from rasterio.enums import Resampling
    from rasterio.warp import reproject
    from rasterio.windows import Window
    from omnicloudmask import predict_from_array

    entrada = Path(entrada)
    destino = Path(destino) if destino else pastas()["interim"]
    stem = entrada.stem

    with rasterio.open(entrada) as src:
        nativo = {"transform": src.transform, "crs": src.crs,
                  "height": src.height, "width": src.width}
        nodata = src.nodata
        escala = src.res[0] / float(detect_res) if detect_res else 1.0
        h = max(1, int(round(src.height * escala)))
        w = max(1, int(round(src.width * escala)))
        det = src.read([banda_red, banda_green, banda_nir],
                       out_shape=(3, h, w),
                       resampling=Resampling.average).astype("float32")
        # A média do GDAL ignora os pixels de nodata, então blocos parciais
        # saem limpos; a máscara (255 = tem dado) diz onde não sobrou nada.
        mascara = src.read_masks(1, out_shape=(h, w),
                                 resampling=Resampling.average)
        t_det = src.transform * Affine.scale(src.width / w, src.height / h)

    valido = ((mascara >= 255) & np.all(det > -5000, axis=0)
              & ~np.all(det == 0, axis=0))
    det[:, ~valido] = 0.0

    mask = predict_from_array(det, patch_size=patch_size,
                              patch_overlap=patch_overlap,
                              no_data_value=0, apply_no_data_mask=True)
    mask = np.squeeze(np.asarray(mask)).astype("uint8")
    mask = np.where(valido, mask, NODATA_MASCARA).astype("uint8")

    def grava(caminho, arr, transform):
        perfil = dict(driver="GTiff", dtype="uint8", count=1,
                      height=arr.shape[0], width=arr.shape[1],
                      transform=transform, crs=nativo["crs"],
                      nodata=NODATA_MASCARA, compress="deflate",
                      tiled=True, blockxsize=256, blockysize=256,
                      BIGTIFF="IF_SAFER")
        with rasterio.open(caminho, "w", **perfil) as dst:
            dst.write(arr.astype("uint8"), 1)
        return caminho

    saidas = {}
    saidas["deteccao"] = grava(
        destino / f"{stem}_cloudmask_{int(detect_res)}m.tif", mask, t_det)

    nativa = np.full((nativo["height"], nativo["width"]), NODATA_MASCARA,
                     dtype="uint8")
    reproject(source=mask, destination=nativa, src_transform=t_det,
              src_crs=nativo["crs"], dst_transform=nativo["transform"],
              dst_crs=nativo["crs"], resampling=Resampling.nearest)
    saidas["nativa"] = grava(destino / f"{stem}_cloudmask_native.tif", nativa,
                             nativo["transform"])

    clear = (nativa == 0).astype("uint8")
    clear[nativa == NODATA_MASCARA] = NODATA_MASCARA
    saidas["clear"] = grava(destino / f"{stem}_clearmask_native.tif", clear,
                            nativo["transform"])

    total = int(valido.sum())
    for c, nome in CLASSES_OCM.items():
        n = int(np.count_nonzero((mask == c) & valido))
        print(f"  {c} {nome:<13}: {n:>10d}  ({100.0 * n / max(total, 1):5.1f} %)")

    if aplicar:
        alvo = destino / f"{stem}_masked.tif"
        with rasterio.open(entrada) as src:
            perfil = src.profile.copy()
            nd = src.nodata if src.nodata is not None else NODATA
            for k in ("blockxsize", "blockysize", "tiled", "interleave"):
                perfil.pop(k, None)
            perfil.update(nodata=nd, compress="deflate", predictor=2,
                          tiled=True, blockxsize=512, blockysize=512,
                          BIGTIFF="IF_SAFER", interleave="band")
            nublado = np.isin(nativa, [1, 2, 3])
            with rasterio.open(alvo, "w", **perfil) as dst:
                for b in range(1, src.count + 1):
                    for r0 in range(0, src.height, 2048):
                        nr = min(2048, src.height - r0)
                        jan = Window(0, r0, src.width, nr)
                        dados = src.read(b, window=jan)
                        dados[nublado[r0:r0 + nr, :]] = nd
                        dst.write(dados, b, window=jan)
                    dst.set_band_description(b, NOMES_SAIDA[b - 1])
        saidas["mascarada"] = alvo
        print(f"Escrito: {alvo}")
    return saidas


# ---------------------------------------------------------------------------
# Atalhos de aula
# ---------------------------------------------------------------------------

def preparar_aula_01(cena_id=CENA_PADRAO) -> dict:
    """Garante o que a Aula 01 consome: bandas da cena em data/raw."""
    pastas()
    configurar_gdal()
    return baixar_cena(cena_id)


def preparar_aula_02(cena_id=CENA_PADRAO, nivel="boa") -> dict:
    """Garante o que a Aula 02 consome: pansharpening_<DATA>_<nivel>.tif.

    Se o 6S não estiver instalado, cai para TOA e avisa — a detecção de nuvem
    funciona nos dois níveis.
    """
    preparar_aula_01(cena_id)
    if nivel == "boa" and not tem_6s():
        print("AVISO: Py6S/6S indisponível — seguindo em TOA.\n"
              "       Para BOA, instale py6s e sixs (ver Aula 01).")
        nivel = "toa"
    fus = fundir(cena_id, nivel)
    return {"nivel": nivel, "pansharpening": fus}


def preparar_aula_03(cena_id=CENA_PADRAO, nivel="boa") -> dict:
    """Garante o que a Aula 03 consome: fusão + máscara de nuvem + mascarada."""
    r = preparar_aula_02(cena_id, nivel)
    fus = Path(r["pansharpening"])
    inter = pastas()["interim"]
    nativa = inter / f"{fus.stem}_cloudmask_native.tif"
    mascarada = inter / f"{fus.stem}_masked.tif"
    if nativa.exists() and mascarada.exists():
        print("Máscara de nuvem já existe — nada a fazer.")
    else:
        r.update(mascara_nuvens(fus))
    r["cloudmask"] = nativa
    r["mascarada"] = mascarada
    return r
