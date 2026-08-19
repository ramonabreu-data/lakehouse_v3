"""Motor Dremio: pedido tipado -> SQL.

Esta e a unica camada que escreve SQL, e o unico ponto onde um valor do cliente
vira texto dentro de um comando. E aqui, portanto, que mora o teste de injecao.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app import catalogo
from app.motores.dremio import sql
from app.nucleo import ErroDeValidacao, analisar_parametros, analisar_resumo


@pytest.fixture
def conjunto():
    return catalogo.obter("selo-ambiental-2026-fases")


def montar(conjunto, **params) -> str:
    return sql.dados(conjunto, analisar_parametros(conjunto, {k: [str(v)] for k, v in params.items()}))


# --- identificadores -------------------------------------------------------

def test_projecao_explicita_sem_asterisco(conjunto):
    comando = montar(conjunto)
    for campo in conjunto.campos:
        assert f'"{campo.nome}"' in comando
    # Sem `SELECT *`: coluna nova na view nao vaza sem revisao.
    assert "*" not in comando


def test_caminho_sai_com_cada_segmento_entre_aspas(conjunto):
    esperado = ".".join(f'"{p}"' for p in conjunto.fonte.endereco.split("."))
    assert f"FROM {esperado}" in montar(conjunto)


def test_identificador_estranho_no_catalogo_e_recusado():
    with pytest.raises(ErroDeValidacao):
        sql.identificador('municipio" FROM segredo --')


# --- literais --------------------------------------------------------------

def test_literais_por_tipo():
    assert sql.literal(True) == "TRUE"
    assert sql.literal(False) == "FALSE"
    assert sql.literal(42) == "42"
    assert sql.literal(70.5) == "70.5"
    assert sql.literal(dt.date(2025, 1, 1)) == "DATE '2025-01-01'"
    assert sql.literal("Fortaleza") == "'Fortaleza'"
    assert sql.literal(None) == "NULL"


def test_booleano_nao_vira_inteiro():
    # bool e subclasse de int em Python: se a ordem dos testes de tipo estiver
    # trocada, True viraria "1" e o SQL do Dremio recusaria a comparacao.
    assert sql.literal(True) != "1"


# --- operadores ------------------------------------------------------------

def test_comparacoes(conjunto):
    comando = montar(conjunto, pontos__gte=70, pontos__lt=90)
    assert '"pontos" >= 70.0' in comando
    assert '"pontos" < 90.0' in comando


def test_igualdade_e_diferenca(conjunto):
    assert """"municipio" = 'Fortaleza'""" in montar(conjunto, municipio="Fortaleza")
    assert """"municipio" <> 'Fortaleza'""" in montar(conjunto, municipio__ne="Fortaleza")


def test_lista(conjunto):
    assert '"cod_ibge" IN (2304400, 2312908)' in montar(conjunto, cod_ibge__in="2304400,2312908")


def test_contem_ignora_caixa(conjunto):
    # O LIKE do Dremio diferencia maiuscula de minuscula, e quem digita numa
    # caixa de busca nao espera isso. Descoberto testando contra o dado real.
    comando = montar(conjunto, municipio__contem="For")
    assert """LOWER("municipio") LIKE '%for%'""" in comando
    assert montar(conjunto, municipio__contem="FOR") == comando


def test_nulo():
    edicao = catalogo.obter("selo-ambiental-2025-fases")
    assert '"auditor" IS NULL' in montar(edicao, auditor__nulo="true")
    assert '"auditor" IS NOT NULL' in montar(edicao, auditor__nulo="false")


def test_booleano_no_where(conjunto):
    assert '"tem_selo" = TRUE' in montar(conjunto, tem_selo="true")
    assert '"tem_selo" = FALSE' in montar(conjunto, tem_selo="0")


# --- injecao ---------------------------------------------------------------

def test_aspa_simples_e_escapada_e_nao_encerra_o_literal(conjunto):
    assert """'Olho d''Agua'""" in montar(conjunto, municipio="Olho d'Agua")


def test_tentativa_classica_de_injecao_vira_literal_inofensivo(conjunto):
    comando = montar(conjunto, municipio="x'; DROP TABLE y; --")
    assert "DROP TABLE" in comando            # o texto continua la...
    assert comando.count("'") % 2 == 0        # ...dentro de um literal fechado
    assert """'x''; DROP TABLE y; --'""" in comando
    assert ";" not in comando.split("WHERE")[0]


def test_injecao_por_operador_in(conjunto):
    comando = montar(conjunto, municipio__in="a,b'; DELETE FROM x; --")
    assert """'b''; DELETE FROM x; --'""" in comando
    assert comando.count("'") % 2 == 0


def test_injecao_pela_busca_em_texto(conjunto):
    comando = montar(conjunto, municipio__contem="'; DROP TABLE y; --")
    assert comando.count("'") % 2 == 0


# --- paginacao, contagem e agregacao ---------------------------------------

def test_ordem_e_paginacao(conjunto):
    comando = montar(conjunto, ordenar_por="pontos", ordem="desc", limite=10, deslocamento=20)
    assert 'ORDER BY "pontos" DESC' in comando
    assert comando.endswith("LIMIT 10 OFFSET 20")


def test_ordem_padrao_decrescente_do_catalogo():
    por_selo = catalogo.obter("selo-ambiental-2026-por-selo")
    assert 'ORDER BY "n_municipios" DESC' in montar(por_selo)


def test_contagem_repete_os_filtros_e_ignora_paginacao(conjunto):
    consulta = analisar_parametros(conjunto, {"municipio": ["Fortaleza"], "limite": ["10"]})
    comando = sql.total(conjunto, consulta)
    assert comando.startswith("SELECT COUNT(*)")
    assert """"municipio" = 'Fortaleza'""" in comando
    assert "LIMIT" not in comando and "ORDER BY" not in comando


def test_resumo_agrupa_e_conta(conjunto):
    pedido = analisar_resumo(conjunto, {"agrupar_por": ["territorio_desenvolvimento"]})
    comando = sql.resumo(conjunto, pedido)
    assert comando.startswith('SELECT "territorio_desenvolvimento", COUNT(*) AS "registros"')
    assert 'GROUP BY "territorio_desenvolvimento"' in comando


def test_resumo_com_metrica(conjunto):
    pedido = analisar_resumo(
        conjunto, {"agrupar_por": ["selo"], "metrica": ["pontos"], "funcao": ["media"]}
    )
    comando = sql.resumo(conjunto, pedido)
    assert 'AVG("pontos") AS "pontos_media"' in comando


def test_resumo_leva_os_filtros(conjunto):
    pedido = analisar_resumo(conjunto, {"agrupar_por": ["selo"], "tem_selo": ["true"]})
    assert 'WHERE "tem_selo" = TRUE' in sql.resumo(conjunto, pedido)
