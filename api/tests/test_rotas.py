"""Comportamento HTTP de ponta a ponta, com o motor dublado.

O que estes testes protegem e o contrato que a aplicacao web enxerga: formato da
resposta, codigos de erro, paginacao, CORS — e o fato de a camada de rotas nao
saber de onde o dado vem. As asserções sao sobre o PEDIDO que chegou ao motor,
nao sobre SQL: SQL e assunto de `test_sql_dremio.py`.
"""

from __future__ import annotations

SLUG = "selo-ambiental-2026-fases"


# --- descoberta do catalogo ------------------------------------------------

def test_lista_de_conjuntos_descreve_o_contrato(cliente, cabecalho):
    corpo = cliente.get("/v1/conjuntos", headers=cabecalho).json()
    slugs = [c["slug"] for c in corpo["conjuntos"]]
    assert SLUG in slugs and "acoes-secretario" in slugs
    # Todas as views do refinamento estao publicadas, nao so as do BI na tela.
    assert len(slugs) == 10


def test_detalhe_do_conjunto_lista_campos_tipos_e_filtros(cliente, cabecalho):
    corpo = cliente.get(f"/v1/conjuntos/{SLUG}", headers=cabecalho).json()
    campos = {c["nome"]: c for c in corpo["campos"]}
    assert campos["pontos"]["tipo"] == "decimal"
    assert campos["municipio"]["filtravel"] is True
    assert campos["latitude"]["filtravel"] is False
    assert corpo["fonte"].startswith("refinamento.")
    assert corpo["motor"] == "dremio"
    assert corpo["area"]["slug"] == "chefia-de-gabinete"


def test_conjunto_inexistente_responde_404(cliente, cabecalho):
    for caminho in ("", "/dados", "/resumo"):
        resposta = cliente.get(f"/v1/conjuntos/nao-existe{caminho}", headers=cabecalho)
        assert resposta.status_code == 404
        assert resposta.json()["erro"]["codigo"] == "conjunto_desconhecido"


# --- dados -----------------------------------------------------------------

def test_dados_devolvem_registros_e_metadados(cliente, cabecalho, motor):
    corpo = cliente.get(f"/v1/conjuntos/{SLUG}/dados", headers=cabecalho).json()
    assert corpo["conjunto"] == SLUG
    assert corpo["dados"][0]["municipio"] == "Fortaleza"
    assert corpo["paginacao"]["retornados"] == 2
    assert corpo["paginacao"]["total"] is None       # so com incluir_total
    assert motor.operacoes == ["dados"]


def test_data_sai_serializada_em_iso(cliente, cabecalho):
    corpo = cliente.get(f"/v1/conjuntos/{SLUG}/dados", headers=cabecalho).json()
    assert corpo["dados"][0]["primeira_visita"] == "2025-03-01"


def test_filtro_da_query_string_chega_tipado_ao_motor(cliente, cabecalho, motor):
    cliente.get(f"/v1/conjuntos/{SLUG}/dados?municipio=Fortaleza&pontos__gte=70", headers=cabecalho)
    assert motor.filtro("municipio").valor == "Fortaleza"
    assert motor.filtro("pontos").valor == 70.0
    assert motor.filtro("pontos").operador == "gte"


def test_selecao_de_colunas_chega_ao_motor(cliente, cabecalho, motor):
    cliente.get(f"/v1/conjuntos/{SLUG}/dados?colunas=municipio,pontos", headers=cabecalho)
    assert motor.ultimo.colunas == ("municipio", "pontos")


def test_parametro_invalido_responde_400_com_mensagem_util(cliente, cabecalho, motor):
    resposta = cliente.get(f"/v1/conjuntos/{SLUG}/dados?pontos=muitos", headers=cabecalho)
    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "parametro_invalido"
    assert "pontos" in resposta.json()["erro"]["mensagem"]
    assert motor.pedidos == []      # nem chegou a consultar


def test_incluir_total_dispara_a_contagem(cliente, cabecalho, motor):
    corpo = cliente.get(f"/v1/conjuntos/{SLUG}/dados?incluir_total=true", headers=cabecalho).json()
    assert motor.operacoes == ["dados", "total"]
    assert corpo["paginacao"]["total"] == 2


def test_paginacao_e_repassada(cliente, cabecalho, motor):
    cliente.get(f"/v1/conjuntos/{SLUG}/dados?limite=10&deslocamento=20", headers=cabecalho)
    assert (motor.ultimo.limite, motor.ultimo.deslocamento) == (10, 20)


def test_limite_absurdo_responde_400(cliente, cabecalho):
    assert cliente.get(f"/v1/conjuntos/{SLUG}/dados?limite=999999", headers=cabecalho).status_code == 400


def test_resumo_agrega_na_fonte(cliente, cabecalho, motor):
    resposta = cliente.get(
        f"/v1/conjuntos/{SLUG}/resumo?agrupar_por=territorio_desenvolvimento&metrica=pontos&funcao=media",
        headers=cabecalho,
    )
    assert resposta.status_code == 200
    assert motor.operacoes == ["resumo"]
    assert motor.ultimo.agrupar_por == ("territorio_desenvolvimento",)
    assert resposta.json()["funcao"] == "media"


def test_resumo_sem_agrupamento_responde_400(cliente, cabecalho):
    assert cliente.get(f"/v1/conjuntos/{SLUG}/resumo", headers=cabecalho).status_code == 400


# --- falhas da fonte -------------------------------------------------------

def test_fonte_fora_do_ar_responde_502_sem_vazar_detalhe(cliente, cabecalho, motor):
    motor.erro = RuntimeError("Flight returned unauthenticated error: senha=segredo")
    resposta = cliente.get(f"/v1/conjuntos/{SLUG}/dados", headers=cabecalho)
    assert resposta.status_code == 502
    assert resposta.json()["erro"]["codigo"] == "fonte_indisponivel"
    assert "senha" not in resposta.text and "SELECT" not in resposta.text


# --- consumo por navegador -------------------------------------------------

def test_cors_libera_a_origem_configurada(cliente, cabecalho):
    resposta = cliente.get(
        f"/v1/conjuntos/{SLUG}/dados",
        headers={**cabecalho, "Origin": "https://app.exemplo.gov.br"},
    )
    assert resposta.headers["access-control-allow-origin"] == "https://app.exemplo.gov.br"


def test_preflight_do_navegador_e_respondido(cliente):
    resposta = cliente.options(
        f"/v1/conjuntos/{SLUG}/dados",
        headers={
            "Origin": "https://app.exemplo.gov.br",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert resposta.status_code == 200
    assert "x-api-key" in resposta.headers["access-control-allow-headers"].lower()


def test_origem_nao_autorizada_nao_recebe_o_cabecalho(cliente, cabecalho):
    resposta = cliente.get(
        f"/v1/conjuntos/{SLUG}/dados",
        headers={**cabecalho, "Origin": "https://site-aleatorio.com"},
    )
    assert "access-control-allow-origin" not in resposta.headers


# --- saude -----------------------------------------------------------------

def test_saude_nao_consulta_a_fonte(cliente, motor):
    corpo = cliente.get("/saude").json()
    assert corpo["status"] == "ok"
    assert motor.pedidos == []


def test_prontidao_consulta_a_fonte(cliente):
    assert cliente.get("/saude/pronto").json() == {"status": "pronto"}
