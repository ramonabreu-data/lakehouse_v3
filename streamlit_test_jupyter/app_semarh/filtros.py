"""Filtros do painel: uma lista de caixas de seleção que abre num botão.

O estado vai para `st.query_params`, que persiste no reload — ao atualizar a
pagina o filtro volta ao ultimo estado, e o link compartilhado ja chega
filtrado. "|" separa os valores (nao ocorre nos nomes). Use `url_key` distinto
por aba para nao colidir.

**A tela mostra um botao, nao a lista.** O filtro fica fechado num
`st.popover`: por fora so aparece uma linha — `Território · todos`,
`Território · 3 de 12` — e as caixas de selecao abrem por cima do painel, sem
empurrar nada para baixo. Era esse o problema do multiselect: com as 12 opcoes
marcadas ele virava 12 etiquetas, e dois ou tres filtros assim ocupavam meia
tela antes de o usuario ver um numero.

**Nenhum filtro nasce com tudo marcado**, e *nada marcado = todos*. Assim o
estado de repouso e o painel inteiro, sem ruido, e marcar algo sempre significa
restringir.

**As caixas ficam num `st.form`.** Marcar uma caixa nao recarrega a tela: nada
acontece ate o **Aplicar**. Sem isso, cada clique custaria um recarregamento do
painel inteiro — e escolher cinco territorios seriam cinco recargas.

Listas longas (municipios, 224) nao viram caixas de selecao: a lista fica
impossivel de percorrer no olho. Acima de `LIMITE_CAIXAS` o popover mostra o
multiselect com busca, que serve para procurar um nome — e o botao de fora
continua o mesmo.
"""

import streamlit as st

# Acima disto, procurar e melhor do que percorrer: o popover troca as caixas
# pelo campo de busca.
LIMITE_CAIXAS = 24
# A partir daqui as caixas vao em duas colunas (12 meses numa coluna so fariam
# um popover comprido demais).
CAIXAS_EM_DUAS_COLUNAS = 8


def _da_url(qp, url_key, opcoes):
    """O que a URL traz, na ordem das opcoes. Ausente => nada escolhido."""
    if url_key not in qp:
        return []
    marcados = qp[url_key].split("|")
    return [o for o in opcoes if str(o) in marcados]


def _resumo(escolhidos, opcoes, placeholder, formato):
    """O texto do botao: o estado do filtro em uma linha."""
    # Todas marcadas e nenhuma marcada dizem a mesma coisa: o painel inteiro.
    if not escolhidos or len(escolhidos) == len(opcoes):
        return placeholder
    if len(escolhidos) == 1:
        return str(formato(escolhidos[0]))
    return f"{len(escolhidos)} de {len(opcoes)}"


def _guardar(url_key, escolhidos, opcoes):
    """Grava a escolha na sessao e na URL.

    A escolha e guardada como o usuario a fez — inclusive "todas marcadas", que
    e o que o botao **Todos** produz: as caixas ficam visivelmente marcadas.
    Para a URL, porem, tudo marcado e o mesmo que nada marcado (os dois dizem
    "sem recorte"), entao ela fica limpa nos dois casos e o link continua curto.
    """
    st.session_state[f"filtro_{url_key}"] = escolhidos
    # A caixa de selecao guarda o proprio estado pela CHAVE: sem trocar a chave,
    # ela ignoraria o estado novo e continuaria como o usuario a deixou. Este
    # contador entra na chave, entao as caixas renascem lendo o que foi gravado.
    st.session_state[f"versao_{url_key}"] = st.session_state.get(f"versao_{url_key}", 0) + 1
    if escolhidos and len(escolhidos) < len(opcoes):
        st.query_params[url_key] = "|".join(str(v) for v in escolhidos)
    elif url_key in st.query_params:
        del st.query_params[url_key]


def _painel(url_key, opcoes, escolhidos, formato) -> None:
    """O conteudo do popover: as caixas (ou a busca) e os botoes de acao."""
    versao = st.session_state.get(f"versao_{url_key}", 0)
    with st.form(f"form_{url_key}", border=False):
        if len(opcoes) > LIMITE_CAIXAS:
            marcados = st.multiselect(
                "Escolha", opcoes, default=escolhidos, format_func=formato,
                key=f"multi_{url_key}_{versao}", label_visibility="collapsed",
                placeholder="Digite para procurar…",
            )
        else:
            colunas = (st.columns(2) if len(opcoes) > CAIXAS_EM_DUAS_COLUNAS
                       else [st.container()])
            marcados = []
            for indice, opcao in enumerate(opcoes):
                with colunas[indice % len(colunas)]:
                    if st.checkbox(str(formato(opcao)), value=opcao in escolhidos,
                                   key=f"caixa_{url_key}_{versao}_{opcao}"):
                        marcados.append(opcao)

        c_aplicar, c_todos, c_limpar = st.columns(3)
        aplicar = c_aplicar.form_submit_button("Aplicar", type="primary", width='stretch')
        # "Todos" e "Limpar" nao esperam o Aplicar: os dois ja SAO uma decisao
        # completa, e pedir mais um clique para confirmar "quero tudo" so
        # atrasaria. O "Todos" ainda deixa as caixas marcadas, para a tela
        # mostrar o que esta valendo em vez de um campo vazio.
        todos = c_todos.form_submit_button("Todos", width='stretch',
                                           help="Marca todas as opções e aplica na hora.")
        limpar = c_limpar.form_submit_button("Limpar", width='stretch',
                                             help="Desmarca tudo — volta a mostrar todos.")

    if aplicar or todos or limpar:
        if todos:
            escolha = list(opcoes)
        elif limpar:
            escolha = []
        else:
            escolha = marcados
        _guardar(url_key, escolha, opcoes)
        # O botao la fora ja foi desenhado com o resumo antigo: um rerun deixa
        # o painel inteiro (botao, cartoes, mapa) contando a mesma historia.
        st.rerun()


def _filtro(rotulo, opcoes, url_key, container, placeholder, ajuda, formato):
    """Desenha o filtro e devolve o que esta escolhido (lista, talvez vazia)."""
    alvo = container if container is not None else st
    opcoes = list(opcoes)
    estado = f"filtro_{url_key}"
    if estado not in st.session_state:
        st.session_state[estado] = _da_url(st.query_params, url_key, opcoes)
    # As opcoes mudam com o dado (um ano novo, um territorio a menos): o que
    # sobrou de uma lista antiga sai daqui em vez de virar filtro fantasma.
    escolhidos = [o for o in st.session_state[estado] if o in opcoes]

    # A CHAVE do popover carrega o contador de versao (o mesmo das caixas), e e
    # o que o fecha sozinho: aplicar incrementa o contador, entao o popover que
    # renasce e outro elemento — nasce fechado, e o painel ja atualizado
    # aparece sem ninguem precisar clicar fora para tirar o filtro da frente.
    versao = st.session_state.get(f"versao_{url_key}", 0)
    with alvo.popover(f"{rotulo} · {_resumo(escolhidos, opcoes, placeholder, formato)}",
                      width='stretch', help=ajuda, key=f"popover_{url_key}_{versao}"):
        st.caption(rotulo)
        _painel(url_key, opcoes, escolhidos, formato)
    return escolhidos


def multiselect_url(rotulo, opcoes, url_key, container=None, placeholder="todos",
                    ajuda=None, formato=str):
    """Filtro por lista onde **vazio = todos** — e e assim que ele comeca.

    Devolve sempre uma lista utilizavel num `.isin(...)`: sem nada marcado,
    devolve TODAS as opcoes. Quem chama nao precisa saber se houve recorte.
    """
    escolhidos = _filtro(rotulo, opcoes, url_key, container, placeholder, ajuda, formato)
    return escolhidos or list(opcoes)


def multiselect_opcional_url(rotulo, opcoes, url_key, container=None, ajuda=None,
                             placeholder="todos", formato=str):
    """Igual ao `multiselect_url`, mas devolve **[] quando nada foi escolhido**.

    Use quando a tela precisa DISTINGUIR "sem recorte" de "todos escolhidos" —
    por exemplo para so mostrar o aviso "filtrando 3 de 224 municípios" quando
    alguem de fato filtrou.
    """
    escolhidos = _filtro(rotulo, opcoes, url_key, container, placeholder, ajuda, formato)
    # Marcar as 224 opcoes e dizer "sem recorte", nao "filtrei 224 municípios":
    # quem usa esta variante quer justamente distinguir os dois casos.
    return [] if len(escolhidos) == len(opcoes) else escolhidos


def selectbox_url(rotulo, opcoes, url_key, container=None, padrao=None, formato=str,
                  ajuda=None):
    """Escolha unica persistida na URL (sobrevive ao refresh e vai no link).

    Diferente dos filtros de lista: aqui sempre ha um valor. `padrao` e usado
    quando a URL nao traz nada (ou traz algo fora das opcoes).
    """
    alvo = container if container is not None else st
    widget_key = f"filtro_{url_key}"
    qp = st.query_params
    padrao = opcoes[0] if padrao is None else padrao

    def _sincronizar():
        escolhido = st.session_state.get(widget_key, padrao)
        if escolhido == padrao:
            if url_key in qp:
                del qp[url_key]      # padrao => mantem a URL limpa
        else:
            qp[url_key] = str(escolhido)

    da_url = qp.get(url_key)
    inicial = next((o for o in opcoes if str(o) == da_url), padrao)
    return alvo.selectbox(
        rotulo, opcoes,
        index=opcoes.index(inicial),
        key=widget_key,
        on_change=_sincronizar,
        format_func=formato,
        help=ajuda,
    )
