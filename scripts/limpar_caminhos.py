#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tira caminhos absolutos da maquina das SAIDAS dos notebooks.

POR QUE ISTO EXISTE
As aulas publicam os notebooks COM as saidas salvas — e o site do Quarto
embute essas saidas com {{< embed >}}. So que varias saidas trazem o caminho
completo de onde o notebook rodou. O formato (com a unidade e as pastas da
sua maquina no lugar de UNIDADE e PASTAS):

    UNIDADE:/PASTAS/projeto/.pixi/envs/default/Lib/
        site-packages/arosics/CoReg.py:122: UserWarning: ...
    Writing GeoArray of size (6968, 6456, 5) to
        UNIDADE:/PASTAS/projeto/colab/data/interim/...

Isso nao e catastrofico — nao e senha nem chave —, mas conta a quem le a
estrutura de pastas da sua maquina, o gerenciador de ambiente que voce usa e
a letra do disco. Em repositorio publico, e informacao de graca para quem
esta montando um ataque direcionado. E some sozinho: basta trocar o prefixo.

O QUE O SCRIPT FAZ
Reescreve SO as saidas (stream, execute_result, display_data e traceback de
erro). O codigo das celulas nao e tocado — se voce escreveu um caminho no
codigo de proposito, ele fica. Cada caminho absoluto vira:

    <ambiente>/.../site-packages/arosics/CoReg.py   (quando e biblioteca)
    <projeto>/colab/data/interim/...                (quando e do projeto)
    <caminho local>                                 (qualquer outro)

COMO USAR
    pixi run limpar          # limpa colab/*.ipynb
    pixi run publicar        # limpa e depois renderiza o site

Rode ANTES de commitar. Depois de limpar, renderize: o docs/ e gerado a
partir dos notebooks, entao o site so fica limpo se voce renderizar de novo.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Nome da pasta do projeto, para reconhecer um caminho "de dentro de casa".
PROJETO = "geoprocessamento-cbers4a"

# Windows (C:\...), Unix (/home/fulano/..., /Users/Fulano/...) e UNC (\\servidor\...).
#
# O olhar-para-tras é o detalhe que importa: sem ele, o "s:/" de "https://"
# casa como se fosse uma unidade de disco, e o script sai destruindo as URLs
# de CDN dentro do mapa folium que fica salvo como saída da Aula 03. Proibir
# letra, dígito, ":" e "/" antes do padrão resolve — um caminho de verdade vem
# sempre depois de espaço, aspas, início de linha ou pontuação.
# Também exigimos DOIS separadores no caminho do Windows. Sem isso, um texto
# como "veja a nota e:\nproximo item" — dois-pontos no fim da frase seguido de
# uma quebra de linha escapada — passa por unidade de disco. Caminho de
# verdade tem pelo menos duas barras. A troca é perder um "C:\Windows" solto,
# que de qualquer forma não conta nada sobre a sua máquina.
PADRAO = re.compile(
    r"""(?<![A-Za-z0-9_:/])(?:
          [A-Za-z]:[\\/](?![\\/])[^\s"'<>|?*\n]*[\\/][^\s"'<>|?*\n]+  # C:\a\b
        | \\\\[A-Za-z0-9._-][^\s"'<>|?*\n]{2,300}        # \\servidor\compartilhamento
        | /(?:home|Users|root)/[^\s"'<>|?*\n]{2,300}     # /home/fulano/...
        )""",
    re.VERBOSE,
)


def encurtar(caminho: str) -> str:
    """Troca a parte que identifica a maquina por um marcador generico."""
    norm = caminho.replace("\\", "/")
    baixo = norm.lower()

    if "site-packages/" in baixo:
        resto = norm[baixo.index("site-packages/") + len("site-packages/"):]
        return f"<ambiente>/.../site-packages/{resto}"
    if "dist-packages/" in baixo:
        resto = norm[baixo.index("dist-packages/") + len("dist-packages/"):]
        return f"<ambiente>/.../dist-packages/{resto}"
    if f"/{PROJETO.lower()}/" in baixo:
        resto = norm[baixo.index(f"/{PROJETO.lower()}/") + len(PROJETO) + 2:]
        return f"<projeto>/{resto}"
    if baixo.rstrip("/").endswith(f"/{PROJETO.lower()}"):
        return "<projeto>"
    return "<caminho local>"


def limpar_texto(txt: str) -> tuple[str, int]:
    achados = 0

    def troca(m):
        nonlocal achados
        achados += 1
        return encurtar(m.group(0))

    return PADRAO.sub(troca, txt), achados


def _campo(obj, chave):
    """Le um campo de saida que pode ser str ou lista de str."""
    v = obj.get(chave)
    if v is None:
        return None, None
    return ("".join(v), list) if isinstance(v, list) else (v, str)


def _grava(obj, chave, texto, tipo):
    obj[chave] = texto.splitlines(keepends=True) if tipo is list else texto


def limpar_notebook(caminho: Path, aplicar: bool) -> int:
    nb = json.loads(caminho.read_text(encoding="utf-8"))
    total = 0

    for i, cel in enumerate(nb.get("cells", [])):
        for saida in cel.get("outputs", []):
            tipo_saida = saida.get("output_type")

            if tipo_saida == "stream":
                txt, t = _campo(saida, "text")
                if txt:
                    novo, n = limpar_texto(txt)
                    if n:
                        total += n
                        print(f"  celula {i} [stream]      {n} caminho(s)")
                        if aplicar:
                            _grava(saida, "text", novo, t)

            elif tipo_saida in ("execute_result", "display_data"):
                # so os formatos de TEXTO: imagem nao tem caminho dentro
                for mime in ("text/plain", "text/html", "text/markdown"):
                    txt, t = _campo(saida.get("data", {}), mime)
                    if txt:
                        novo, n = limpar_texto(txt)
                        if n:
                            total += n
                            print(f"  celula {i} [{mime}] {n} caminho(s)")
                            if aplicar:
                                _grava(saida["data"], mime, novo, t)

            elif tipo_saida == "error":
                if saida.get("evalue"):
                    novo, n = limpar_texto(saida["evalue"])
                    if n:
                        total += n
                        print(f"  celula {i} [evalue]      {n} caminho(s)")
                        if aplicar:
                            saida["evalue"] = novo
                tb = saida.get("traceback") or []
                for j, linha in enumerate(tb):
                    novo, n = limpar_texto(linha)
                    if n:
                        total += n
                        print(f"  celula {i} [traceback]   {n} caminho(s)")
                        if aplicar:
                            tb[j] = novo

    if total and aplicar:
        caminho.write_text(
            json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return total


def main(argv: list[str]) -> int:
    conferir = "--conferir" in argv          # so relata, nao grava
    alvos = [a for a in argv[1:] if not a.startswith("-")]
    caminhos = (
        [Path(a) for a in alvos]
        if alvos
        else sorted(Path("colab").glob("*.ipynb"))
    )
    if not caminhos:
        print("nenhum notebook encontrado (rode a partir da raiz do projeto).")
        return 1

    total = 0
    for p in caminhos:
        if not p.exists():
            print(f"{p}: nao existe — pulando")
            continue
        print(f"{p}:")
        n = limpar_notebook(p, aplicar=not conferir)
        total += n
        if not n:
            print("  limpo")

    print()
    if conferir:
        print(f"{total} caminho(s) absoluto(s) nas saidas."
              f"{'  Rode sem --conferir para limpar.' if total else ''}")
        return 1 if total else 0

    if total:
        print(f"{total} caminho(s) removido(s). "
              "Agora rode 'pixi run render' para o docs/ acompanhar.")
    else:
        print("nada a fazer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
