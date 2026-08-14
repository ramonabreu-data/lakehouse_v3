"""Baixa do IBGE as malhas usadas no mapa do painel e grava aqui ao lado.

O painel **não** chama o IBGE em tempo de execução: o mapa precisa desenhar a
cada rerun do Streamlit, e depender de uma API externa para isso deixaria o
painel refém da rede e da disponibilidade do serviço. As malhas mudam raramente
(criação/fusão de município), então ficam versionadas no repositório e este
script é rodado à mão quando for preciso atualizar.

    python3 app_semarh/geo/baixar_malhas.py

Gera:
    piaui.json       — contorno do estado, para o efeito de holofote
    municipios.json  — os 224 municípios, agrupados em território no runtime

`codarea` é o código IBGE completo (2200053). A tabela refinada guarda o mesmo
código sem o prefixo do estado (`cod_ibge` = 53), então o cruzamento é
`2200000 + cod_ibge` — a mesma chave usada no refinamento.
"""

import gzip
import json
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
API = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/22"
       "?formato=application/vnd.geo+json&qualidade=intermediaria")
# 4 casas decimais ≈ 11 m. O mapa enquadra o estado inteiro (~700 km de altura),
# onde 11 m é muito abaixo de um pixel — guardar 15 casas só inflaria o arquivo.
CASAS = 4


def _arredondar(no):
    """Corta a precisão das coordenadas, preservando a estrutura aninhada."""
    if isinstance(no, list):
        return [_arredondar(item) for item in no]
    if isinstance(no, float):
        return round(no, CASAS)
    return no


def baixar(url: str, destino: Path, manter: tuple[str, ...] = ()) -> None:
    with urllib.request.urlopen(url, timeout=60) as resposta:
        bruto = resposta.read()
    # O IBGE responde gzip mesmo pedindo `identity`, e o urllib entrega os bytes
    # comprimidos crus. Reconhece pelo número mágico e descomprime.
    if bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)
    malha = json.loads(bruto)
    for feicao in malha.get("features", []):
        feicao["geometry"]["coordinates"] = _arredondar(feicao["geometry"]["coordinates"])
        # Só as propriedades que o mapa usa — o resto é peso morto no arquivo.
        feicao["properties"] = {c: feicao.get("properties", {}).get(c) for c in manter}
    destino.write_text(json.dumps(malha, separators=(",", ":")))
    print(f"  {destino.name}: {len(malha['features'])} feição(ões), "
          f"{destino.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    baixar(API, AQUI / "piaui.json")
    baixar(f"{API}&intrarregiao=municipio", AQUI / "municipios.json", manter=("codarea",))
