# Geoprocessamento com imagens CBERS-4A/WPM e Sentinel-2

[![Site](https://img.shields.io/badge/site-danfioramonte.github.io-blue)](https://danfioramonte.github.io/geoprocessamento-cbers4a/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
[![Licença: MIT](https://img.shields.io/badge/licença-MIT-green.svg)](LICENSE)

Material didático aberto sobre o processamento de imagens **CBERS-4A/WPM**, da
correção atmosférica à substituição de pixels contaminados por nuvem usando
**Sentinel-2 super-resolvido**. O conteúdo nasceu de uma etapa da pesquisa de
mestrado em Sensoriamento Remoto do autor e está sendo apresentado pelo grupo de pesquisa
**MAPEAR** (UNESP — Instituto de Geociências e Ciências Exatas, Rio Claro/SP).

> **Site do curso:** <https://danfioramonte.github.io/geoprocessamento-cbers4a/>
> **Canal no YouTube:** <https://www.youtube.com/@MapearUnesp>

Cada aula tem vídeo, código comentado e duas trilhas de execução: **JupyterLab
local** (com o gerenciador de ambientes `pixi`, recomendado) e **Google Colab**,
para quem não tem máquina com placa de vídeo. Não é preciso experiência prévia
com Python, `pixi` ou GitHub.

Os arquivos Jupyter Notebook que deverão ser rodados no JupyterLab via pixi estão na pasta "colab/". 

---

## Aulas

| Aula | Assunto | Colab |
|------|---------|-------|
| [00](https://danfioramonte.github.io/geoprocessamento-cbers4a/aulas/00-ambiente.html) | Instalando o `pixi` e adquirindo a imagem CBERS-4A via API STAC | [![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/danfioramonte/geoprocessamento-cbers4a/blob/main/colab/00_aquisicao_cbers.ipynb) |
| [01](https://danfioramonte.github.io/geoprocessamento-cbers4a/aulas/01-toa-boa.html) | De DN para reflectância TOA e BOA (6S) e fusão com a pancromática | [![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/danfioramonte/geoprocessamento-cbers4a/blob/main/colab/01_toa_boa.ipynb) |
| [02](https://danfioramonte.github.io/geoprocessamento-cbers4a/aulas/02-omnicloudmask.html) | Detecção de nuvem e sombra com OmniCloudMask | [![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/danfioramonte/geoprocessamento-cbers4a/blob/main/colab/02_nuvens_omnicloudmask.ipynb) |
| [03](https://danfioramonte.github.io/geoprocessamento-cbers4a/aulas/03-sen2sr.html) | Substituindo pixels com nuvem usando SEN2SR e Sentinel-2 | [![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/danfioramonte/geoprocessamento-cbers4a/blob/main/colab/03_sen2sr.ipynb) |

Travou em algum ponto? Veja a página de
[erros comuns](https://danfioramonte.github.io/geoprocessamento-cbers4a/aulas/99-erros-comuns.html).

---

## Trilha 1 — instalação local com `pixi` (recomendada)

O `pixi` monta um ambiente único e reprodutível para todas as aulas — incluindo
os binários pesados (GDAL, o executável do 6S) e o PyTorch — a partir do
`pixi.toml` e do `pixi.lock` versionados aqui.

```bash
# 1. instale o pixi uma única vez (ver Aula 00; no Windows há o instalar_ambiente.bat)
# 2. clone o repositório
git clone https://github.com/danfioramonte/geoprocessamento-cbers4a.git
cd geoprocessamento-cbers4a

# 3. crie o ambiente (baixa alguns GB na primeira vez)
pixi install

# 4. confira se tudo entrou
pixi run check

# 5. abra o JupyterLab dentro do ambiente
pixi run lab
```

Atalhos disponíveis (`pixi run <tarefa>`):

| Tarefa | O que faz |
|--------|-----------|
| `lab` | abre o JupyterLab no ambiente do curso |
| `check` | roda o `verificar_ambiente.py` e confere as bibliotecas |

O ambiente padrão é **de CPU** e roda em qualquer máquina: tanto o SEN2SR Lite
quanto o OmniCloudMask funcionam sem GPU. Quem tem placa NVIDIA encontra o
esboço de um ambiente CUDA comentado no fim do `pixi.toml`.

## Trilha 2 — Google Colab

Abra o notebook da aula pelo badge da tabela acima. Atenção aos limites de tempo de execução
e de disco do Colab em áreas grandes.

---

## Estrutura do repositório

```
.
├── index.qmd                 # página inicial do site
├── aulas/                    # texto das aulas (.qmd) — fonte do site (não utilizáveis)
├── colab/                    # notebooks executados + biblioteca do  (principal)
│   ├── aulas_cbers.py        # funções usadas por todas as aulas
│   ├── config/               # coeficientes ESUN e parâmetros atmosféricos
│   ├── data/                 # arquivos baixados e gerados a partir dos processamentos
│   └── model/                # pesos do SEN2SR que serão baixados pelo mlstac
├── referencias/              # .bib e estilo ABNT (.csl)
├── docs/                     # site publicado (GitHub Pages) — feito pelo Quarto
├── _quarto.yml               # configuração do site
├── pixi.toml / pixi.lock     # definição e trava do ambiente pixi
├── instalar_ambiente.bat     # instalador assistido para Windows (opcional)
└── verificar_ambiente.py     # checagem pós-instalação
```

### Sobre os dados

**As imagens não estão disponíveis no repositório.** Cenas CBERS-4A, mosaicos Sentinel-2, saídas
intermediárias e pesos de modelo somam vários gigabytes e ficam fora do
repositório de propósito. Tudo o que as aulas usam é obtido ao rodas os
códigos das aulas:

- a cena CBERS-4A e seu XML de metadados vêm da API STAC do INPE
  (`baixar_cena()` na Aula 00);
- o mosaico Sentinel-2 vem do Planetary Computer (Aula 03);
- os pesos do SEN2SR Lite são baixados pelo `mlstac` na primeira execução.

Ao clonar, as pastas `colab/data/{raw,interim,processed}` chegam vazias — é o
esperado. Rode a Aula 00 e elas se preenchem.

---

## Como citar

Se este material foi útil na sua pesquisa, aula ou relatório, cite-o assim
(ABNT NBR 6023):

> FIORAMONTE, Danilo Roberto; MAGALHÃES, Danilo Marques de. **Geoprocessamento com
> imagens CBERS-4A/WPM e Sentinel-2**: da correção atmosférica à substituição de
> pixels. Versão 1.0.0. Rio Claro: Grupo de pesquisa MAPEAR, UNESP, 2026. Material
> didático. DOI: 10.5281/zenodo.XXXXXXX. Disponível em:
> https://danfioramonte.github.io/geoprocessamento-cbers4a/. Acesso em: <data>.

<details>
<summary>BibTeX</summary>

```bibtex
@misc{fioramonte_geoprocessamento_2026,
  author       = {Fioramonte, Danilo Roberto and Magalhães, Danilo Marques de},
  title        = {Geoprocessamento com imagens {CBERS-4A/WPM} e {Sentinel-2}:
                  da correção atmosférica à substituição de pixels},
  year         = {2026},
  version      = {1.0.0},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.XXXXXXX},
  url          = {https://danfioramonte.github.io/geoprocessamento-cbers4a/},
  note         = {Material didático}
}
```

</details>


## Métodos e ferramentas utilizadas

As aulas se apoiam em trabalhos publicados, que devem ser citados junto com
este material quando os métodos forem usados:

- **STAC** - Catálogos de ativos espaço-temporais (Radiant Earth Foundation, 2021)
- **SEN2SR** — super-resolução do Sentinel-2 (Aybar et al., 2026)
- **OmniCloudMask** — detecção de nuvem e sombra (Wright et al., 2025)
- **6S / Py6S** — correção atmosférica (Vermote et al., 1997)
- **AROSICS** — coregistro automático (Scheffler et al., 2017)
- **Gram-Schmidt pansharpening** (Laben & Brower, 2000; Aiazzi et al., 2007)

As referências completas estão em `referencias/Bibliotecas Python.bib` e no fim
de cada aula.

## Licença

Código e textos distribuídos sob a licença [MIT](LICENSE). As imagens de satélite
utilizadas seguem as licenças de seus provedores (INPE/CBERS e ESA/Copernicus).

## Agradecimentos

Material desenvolvido no âmbito do Programa de Pós-Graduação em Geografia da
UNESP — Instituto de Geociências e Ciências Exatas (Rio Claro/SP).
