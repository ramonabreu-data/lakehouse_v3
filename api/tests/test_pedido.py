"""Nucleo: a query string vira um pedido tipado, **sem SQL nenhum**.

O que se prende aqui e a fronteira: identificador so sai do catalogo, e valor so
passa depois de virar objeto Python do tipo declarado. Se estes testes passam, o
motor recebe `70.0` e `date(2025,1,1)` — nunca um pedaco de texto do cliente.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app import catalogo
from app.nucleo import ErroDeValidacao, analisar_parametros, analisar_resumo
from app.nucleo import pedido as nucleo


@pytest.fixture
def conjunto():
    return catalogo.obter("selo-ambiental-2026-fases")


def analisar(conjunto, **params):
    return analisar_parametros(conjunto, {k: [str(v)] for k, v in params.items()})


# --- selecao de colunas ----------------------------------------------------

def test_sem_colunas_seleciona_todas_do_catalogo(conjunto):
    assert analisar(conjunto).colunas == conjunto.nomes


def test_colunas_restringe_a_projecao(conjunto):
    assert analisar(conjunto, colunas="municipio,pontos").colunas == ("municipio", "pontos")


def test_coluna_fora_do_catalogo_e_rejeitada(conjunto):
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, colunas="municipio,senha_do_banco")


# --- filtros viram valores tipados -----------------------------------------

def test_igualdade_em_texto(conjunto):
    filtro = analisar(conjunto, municipio="Fortaleza").filtros[0]
    assert (filtro.campo.nome, filtro.operador, filtro.valores) == ("municipio", "eq", ("Fortaleza",))


def test_numero_vira_numero_e_nao_texto(conjunto):
    filtros = analisar(conjunto, pontos__gte=70, cod_ibge=2304400).filtros
    valores = {f.campo.nome: f.valor for f in filtros}
    assert valores["pontos"] == 70.0 and isinstance(valores["pontos"], float)
    assert valores["cod_ibge"] == 2304400 and isinstance(valores["cod_ibge"], int)


def test_data_vira_date(conjunto):
    acoes = catalogo.obter("acoes-secretario")
    assert analisar(acoes, data__gte="2025-01-01").filtros[0].valor == dt.date(2025, 1, 1)
    with pytest.raises(ErroDeValidacao):
        analisar(acoes, data__gte="01/01/2025")


def test_booleano_aceita_as_formas_usuais(conjunto):
    for bruto in ("true", "1", "sim"):
        assert analisar(conjunto, tem_selo=bruto).filtros[0].valor is True
    for bruto in ("false", "0", "nao"):
        assert analisar(conjunto, tem_selo=bruto).filtros[0].valor is False
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, tem_selo="talvez")


def test_operador_in_gera_lista_tipada(conjunto):
    filtro = analisar(conjunto, cod_ibge__in="2304400,2312908").filtros[0]
    assert filtro.valores == (2304400, 2312908)


def test_lista_vazia_ou_longa_demais_e_rejeitada(conjunto):
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, cod_ibge__in=",")
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, cod_ibge__in=",".join(["1"] * 300))


def test_contem_so_vale_para_texto(conjunto):
    assert analisar(conjunto, municipio__contem="For").filtros[0].operador == "contem"
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, pontos__contem="70")


def test_filtro_nulo_vira_booleano():
    edicao = catalogo.obter("selo-ambiental-2025-fases")
    assert analisar(edicao, auditor__nulo="true").filtros[0].valor is True


def test_campo_desconhecido_e_rejeitado(conjunto):
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, coluna_inventada="x")


def test_campo_nao_filtravel_e_rejeitado():
    acoes = catalogo.obter("acoes-secretario")
    nao_filtravel = next(c for c in acoes.campos if not c.filtravel)
    with pytest.raises(ErroDeValidacao):
        analisar(acoes, **{nao_filtravel.nome: "1"})


def test_operador_desconhecido_e_rejeitado(conjunto):
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, pontos__aproximadamente="70")


def test_valor_com_tipo_errado_e_rejeitado(conjunto):
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, pontos="muitos")
    # A tentativa classica de injecao morre aqui: nao e um inteiro.
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, cod_ibge="2304400; DROP TABLE x")


def test_texto_com_controle_ou_longo_demais_e_rejeitado(conjunto):
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, municipio="Fortaleza\nUNION SELECT 1")
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, municipio="a" * (nucleo.TAMANHO_MAXIMO_DO_VALOR + 1))


def test_mesmo_campo_duas_vezes_gera_dois_filtros(conjunto):
    consulta = analisar_parametros(conjunto, {"pontos__gte": ["70"], "pontos__lt": ["90"]})
    assert len(consulta.filtros) == 2


# --- ordenacao e paginacao -------------------------------------------------

def test_ordenacao_padrao_vem_do_catalogo(conjunto):
    assert analisar(conjunto).ordenacao == conjunto.ordenacao_padrao


def test_prefixo_de_menos_no_catalogo_e_decrescente():
    por_selo = catalogo.obter("selo-ambiental-2026-por-selo")
    assert analisar(por_selo).ordenacao == (("n_municipios", "DESC"),)


def test_ordenacao_pedida_pelo_cliente(conjunto):
    assert analisar(conjunto, ordenar_por="pontos", ordem="desc").ordenacao == (("pontos", "DESC"),)


def test_ordenacao_por_campo_fora_do_catalogo_e_rejeitada(conjunto):
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, ordenar_por="1; DROP TABLE x")


def test_paginacao_padrao_e_limitada(conjunto):
    consulta = analisar(conjunto)
    assert (consulta.limite, consulta.deslocamento) == (nucleo.LIMITE_PADRAO, 0)


def test_limite_fora_da_faixa_e_rejeitado(conjunto):
    for invalido in (nucleo.LIMITE_MAXIMO + 1, 0, -5):
        with pytest.raises(ErroDeValidacao):
            analisar(conjunto, limite=invalido)
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, deslocamento=-1)
    with pytest.raises(ErroDeValidacao):
        analisar(conjunto, limite="muitos")


# --- resumo ----------------------------------------------------------------

def test_resumo_valida_agrupamento_metrica_e_funcao(conjunto):
    pedido = analisar_resumo(
        conjunto,
        {"agrupar_por": ["territorio_desenvolvimento"], "metrica": ["pontos"], "funcao": ["media"]},
    )
    assert pedido.agrupar_por == ("territorio_desenvolvimento",)
    assert pedido.apelido_da_metrica == "pontos_media"


def test_resumo_recusa_pedido_fora_do_catalogo(conjunto):
    for params in (
        {},                                                                   # sem agrupamento
        {"agrupar_por": ["nao_existe"]},
        {"agrupar_por": ["latitude"]},                                        # nao agrupavel
        {"agrupar_por": ["municipio"], "metrica": ["municipio"]},             # metrica nao numerica
        {"agrupar_por": ["municipio"], "metrica": ["pontos"], "funcao": ["exec"]},
        {"agrupar_por": ["municipio,situacao,selo,resultado"]},               # mais de 3
    ):
        with pytest.raises(ErroDeValidacao):
            analisar_resumo(conjunto, params)


def test_resumo_aceita_os_mesmos_filtros(conjunto):
    pedido = analisar_resumo(conjunto, {"agrupar_por": ["selo"], "tem_selo": ["true"]})
    assert pedido.filtros[0].campo.nome == "tem_selo"
