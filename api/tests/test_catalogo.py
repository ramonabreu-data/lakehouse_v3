"""O catalogo e o contrato publico: so o que esta ali existe para o mundo.

Alem do formato, estes testes prendem duas garantias que o resto da API assume:
que todo conjunto aponta para uma view do space `refinamento`, e que catalogo
malformado derruba a subida em vez de virar erro de SQL na primeira consulta.
"""

from __future__ import annotations

import pytest

from app import catalogo
from app.motores.dremio import fonte
from app.nucleo import Area, Campo, CatalogoInvalido, Conjunto, Fonte

AREA = catalogo.AREAS[0]


def conjunto(**mudancas) -> Conjunto:
    """Um conjunto valido, com o campo que o teste quiser estragar."""
    base = {
        "slug": "exemplo",
        "area": AREA,
        "fonte": fonte("refinamento.espaco.view"),
        "titulo": "Exemplo",
        "descricao": "Conjunto de teste.",
        "campos": (Campo("municipio", "texto"), Campo("pontos", "decimal")),
        "ordem_padrao": ("municipio",),
    }
    return Conjunto(**{**base, **mudancas})


# --- forma do catalogo publicado -------------------------------------------

def test_publica_os_conjuntos_das_areas_registradas():
    assert catalogo.CATALOGO
    assert len(catalogo.CATALOGO) == len(catalogo.CONJUNTOS)


def test_todo_conjunto_aponta_para_uma_view_do_space_refinamento():
    # A API nunca le tabela Iceberg crua nem fonte conectada (Postgres, Mongo):
    # so as views curadas, que sao o contrato estavel do lakehouse.
    for c in catalogo.CATALOGO.values():
        assert c.fonte.motor in {m.NOME for m in __import__("app.motores", fromlist=["x"]).MODULOS}
        assert c.fonte.endereco.startswith("refinamento.")


def test_slug_e_a_chave_e_bate_com_o_proprio_conjunto():
    for slug, c in catalogo.CATALOGO.items():
        assert c.slug == slug
        assert catalogo.SLUG_VALIDO.match(slug)


def test_todo_conjunto_pertence_a_uma_area_registrada():
    registradas = {a.slug for a in catalogo.AREAS}
    for c in catalogo.CATALOGO.values():
        assert c.area.slug in registradas


def test_toda_area_tem_ao_menos_um_conjunto():
    for area in catalogo.AREAS:
        assert catalogo.conjuntos_da_area(area.slug)


def test_as_duas_edicoes_do_selo_publicam_o_mesmo_conjunto_de_views():
    # O refinamento entrega o MESMO contrato para 2025 e 2026; se uma edicao
    # ganhar uma view e a outra nao, e sinal de esquecimento.
    sufixos = lambda ano: {  # noqa: E731
        s.removeprefix(f"selo-ambiental-{ano}") for s in catalogo.CATALOGO if f"selo-ambiental-{ano}" in s
    }
    assert sufixos(2025) == sufixos(2026)


def test_edicao_2025_tem_auditor_e_2026_nao():
    assert catalogo.obter("selo-ambiental-2025-fases").campo("auditor") is not None
    assert catalogo.obter("selo-ambiental-2026-fases").campo("auditor") is None


def test_obter_conjunto_desconhecido_falha():
    with pytest.raises(catalogo.ConjuntoDesconhecido):
        catalogo.obter("nao-existe")


# --- ordenacao padrao -------------------------------------------------------

def test_prefixo_de_menos_no_catalogo_significa_decrescente():
    assert conjunto(ordem_padrao=("-pontos", "municipio")).ordenacao_padrao == (
        ("pontos", "DESC"),
        ("municipio", "ASC"),
    )


# --- catalogo malformado derruba a subida -----------------------------------

@pytest.mark.parametrize(
    "estrago",
    [
        {"slug": "Slug_Invalido"},
        {"fonte": fonte("entrada.bruta.tabela")},   # fora do refinamento
        {"fonte": Fonte("inexistente", "x")},       # motor nao registrado
        {"titulo": ""},
        {"campos": ()},
        {"campos": (Campo("x", "texto"), Campo("x", "inteiro"))},   # repetido
        {"campos": (Campo("x", "geometria"),)},                     # tipo inexistente
        {"ordem_padrao": ("coluna_que_nao_existe",)},
        {"area": Area("area-fantasma", "Fantasma", "Nao registrada")},
    ],
)
def test_conjunto_malformado_e_recusado(estrago):
    with pytest.raises(CatalogoInvalido):
        catalogo.conferir((conjunto(**estrago),))


def test_slug_repetido_e_recusado():
    with pytest.raises(CatalogoInvalido):
        catalogo.conferir((conjunto(), conjunto()))


def test_conjunto_valido_passa():
    catalogo.conferir((conjunto(),))
