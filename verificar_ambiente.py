"""
Verificacao do ambiente do grupo de estudo em geoprocessamento.

Rode este arquivo sempre que algo parar de funcionar. Ele diz exatamente
qual biblioteca esta faltando, em vez de deixar voce interpretar um
traceback de trinta linhas.

    pixi run check

(equivalente a:  pixi run python verificar_ambiente.py)
"""

import importlib
import platform
import shutil
import sys

OK = "[ OK ]"
FALHOU = "[FALHA]"

# (modulo para importar, nome amigavel, em qual aula e usado)
PACOTES = [
    ("numpy", "numpy", "todas"),
    ("rasterio", "rasterio", "todas"),
    ("pystac_client", "pystac-client", "00 (aquisicao)"),
    ("requests", "requests", "00 (aquisicao)"),
    ("PIL", "pillow", "00 (aquisicao)"),
    ("folium", "folium", "00 (aquisicao)"),
    ("geopandas", "geopandas", "todas"),
    ("rioxarray", "rioxarray", "todas"),
    ("xarray", "xarray", "todas"),
    ("matplotlib", "matplotlib", "todas"),
    ("skimage", "scikit-image", "01 e 02"),
    ("Py6S", "py6s", "01 (BOA)"),
    ("arosics", "arosics", "coregistro"),
    ("torch", "torch", "02 e 03"),
    ("torchvision", "torchvision", "02"),
    ("omnicloudmask", "omnicloudmask", "02"),
    ("sen2sr", "sen2sr", "03"),
    ("mlstac", "mlstac", "03"),
    ("cubo", "cubo", "03"),
]


def versao(modulo):
    return getattr(modulo, "__version__", "versao nao informada")


def main():
    print()
    print("=" * 62)
    print("  Verificacao do ambiente")
    print("=" * 62)
    print(f"  Sistema : {platform.system()} {platform.release()}")
    print(f"  Python  : {sys.version.split()[0]}")
    print(f"  Caminho : {sys.executable}")
    print("=" * 62)
    print()

    faltando = []

    for nome_modulo, nome_pacote, aula in PACOTES:
        try:
            mod = importlib.import_module(nome_modulo)
            print(f"{OK}   {nome_pacote:<18} {versao(mod):<12} (aula {aula})")
        except ImportError:
            print(f"{FALHOU} {nome_pacote:<18} {'ausente':<12} (aula {aula})")
            faltando.append(nome_pacote)

    # O 6S nao e um pacote Python: e um EXECUTAVEL que o Py6S chama. Precisa
    # estar no PATH do ambiente. No conda-forge quem instala isso e o pacote
    # "sixs". Sem ele, a Aula 01 roda o TOA mas falha no BOA.
    print()
    sixs_bin = shutil.which("sixs") or shutil.which("sixsV1.1")
    if sixs_bin:
        print(f"{OK}   6S (binario)       encontrado   ({sixs_bin})")
    else:
        print(f"{FALHOU} 6S (binario)       ausente      (aula 01 BOA)")
        print("        O BOA depende do executavel 6S. No pixi ele vem do")
        print("        pacote conda 'sixs'. Confirme que 'sixs' esta no pixi.toml.")
        faltando.append("sixs")

    # Situacao da GPU: nao e obrigatorio, mas muda o tempo de execucao
    print()
    try:
        import torch

        if torch.cuda.is_available():
            print(f"  GPU detectada: {torch.cuda.get_device_name(0)}")
            print("  O SEN2SRLite vai rodar rapido.")
        else:
            print("  Nenhuma GPU detectada. Isso NAO e um problema.")
            print("  O SEN2SRLite roda em CPU, so leva mais tempo.")
            print("  Se o seu recorte for grande, use a versao no Colab.")
    except ImportError:
        pass

    print()
    print("=" * 62)
    if faltando:
        print("  Faltam pacotes. Confira se eles estao no pixi.toml e rode:")
        print()
        print("      pixi install")
        print()
        print("  Se o problema persistir, apague o ambiente e recrie:")
        print("      (Windows)  rmdir /s /q .pixi   &&  pixi install")
        print("      (Linux/Mac) rm -rf .pixi       &&  pixi install")
    else:
        print("  Tudo certo. Voce pode comecar pela Aula 01.")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
