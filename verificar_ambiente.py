"""
Verificacao do ambiente do grupo de estudo em geoprocessamento.

Rode este arquivo sempre que algo parar de funcionar. Ele diz exatamente
qual biblioteca esta faltando, em vez de deixar voce interpretar um
traceback de trinta linhas.

    conda activate geoproc
    python verificar_ambiente.py
"""

import importlib
import platform
import sys

OK = "[ OK ]"
FALHOU = "[FALHA]"

# (modulo para importar, nome no pip/conda, em qual aula e usado)
PACOTES = [
    ("numpy", "numpy", "todas"),
    ("rasterio", "rasterio", "todas"),
    ("geopandas", "geopandas", "todas"),
    ("rioxarray", "rioxarray", "todas"),
    ("xarray", "xarray", "todas"),
    ("matplotlib", "matplotlib", "todas"),
    ("skimage", "scikit-image", "01 e 02"),
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
        print("  Faltam pacotes. Com o ambiente geoproc ativado, rode:")
        print()
        print(f"      pip install {' '.join(faltando)}")
        print()
        print("  Se o problema persistir, apague e recrie o ambiente:")
        print("      conda env remove -n geoproc")
        print("      conda env create -f env\\environment.yml")
    else:
        print("  Tudo certo. Voce pode comecar pela Aula 01.")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
