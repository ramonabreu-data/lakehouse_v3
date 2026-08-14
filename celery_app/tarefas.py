"""Atualizacao automatica do painel — app Celery (worker + beat).

Todo dia as `HORA_ATUALIZACAO` (07:00 por padrao), no fuso **America/Fortaleza**,
a tarefa `painel.atualizar` refaz o caminho inteiro do dado:

1. **Datasets** — manda o Dremio reler os metadados dos parquets da zona de
   entrada, para enxergar um arquivo novo publicado no MinIO.
2. **DataFrame + analise** — reexecuta os notebooks de refinamento no Spark (um
   por edicao do Selo Ambiental), que regravam as tabelas de `refinamento` e os
   resumos. Sao os mesmos notebooks que uma pessoa roda no JupyterLab: nao ha
   logica duplicada aqui.
3. **Views** — recria as views curadas do space `refinamento`, que sao o caminho
   pelo qual o painel enxerga o dado. Sao elas o contrato: o nome fisico da
   tabela no Nessie pode mudar sem que o Streamlit saiba.
4. **Dashboard** — grava o carimbo da atualizacao num arquivo compartilhado com
   o Streamlit. O painel usa esse carimbo como chave de cache, entao o dado novo
   aparece na proxima interacao, sem esperar o TTL de 5 min vencer.

Rodar a mao (util para testar sem esperar o beat):

    docker compose exec celery-worker celery -A celery_app.tarefas call painel.atualizar
    docker compose logs -f celery-worker
"""

from __future__ import annotations

import html
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger

from celery_app import inventario, notificacao

log = get_task_logger(__name__)

# Fuso unico de toda a stack: horario do agendamento, carimbo da atualizacao e
# o que o painel exibe. Fortaleza (UTC-3, sem horario de verao).
FUSO = ZoneInfo(os.getenv("TZ", "America/Fortaleza"))
BROKER = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
# Horario da carga diaria, "HH:MM" no fuso acima.
HORA_ATUALIZACAO = os.getenv("HORA_ATUALIZACAO", "07:00")
_hora, _minuto = (int(p) for p in HORA_ATUALIZACAO.split(":"))

DIR_NOTEBOOKS = Path(os.getenv("DIR_NOTEBOOKS", "/workspace/notebooks"))


def _lista(bruto: str) -> list[str]:
    """"a, b , c" -> ["a", "b", "c"] — as variaveis de lista vem por virgula."""
    return [item.strip() for item in bruto.split(",") if item.strip()]


                                                                                                                                                                                                                                                                                                                                                                                ARQUIVO_ESTADO = Path(os.getenv("ARQUIVO_ESTADO", "/estado/atualizacao.json"))
# Observabilidade: uma linha JSON por execucao, append-only. E a fonte do
# historico que aparece no painel e do "o que mudou" da notificacao.
ARQUIVO_HISTORICO = Path(os.getenv("ARQUIVO_HISTORICO", "/estado/historico.jsonl"))
# Zonas do object store, so para dizer ONDE cada coisa mora na mensagem.
ZONA_ENTRADA = os.getenv("ZONA_ENTRADA", "entrada")
ZONA_ARMAZEM = os.getenv("ZONA_ARMAZEM", "armazem")
VARS_ENV = Path(os.getenv("VARS_ENV", "/opt/painel/vars.env"))

# --------------------------------------------------------------------------
# As edicoes do Selo Ambiental — a UNICA fonte de verdade do pipeline
# --------------------------------------------------------------------------
# Cada edicao descreve o caminho inteiro do seu dado, do arquivo no MinIO ate a
# view que o painel le. Antes isto eram tres listas paralelas (notebooks,
# arquivos, datasets) mantidas alinhadas por POSICAO — dava para trocar uma sem
# trocar a outra, e a notificacao so sabia listar tudo achatado, sem dizer o que
# pertencia a que edicao. Com a edicao como unidade, a mensagem sai organizada
# de graca e acrescentar uma edicao e acrescentar um item aqui.
#
# `views` mapeia nome da view -> tabela Iceberg no Nessie que ela expoe. As
# pastas espelham a navegacao do painel (setor -> familia de BI -> edicao), e
# quem carrega o ano e a PASTA: por isso os nomes das views se repetem.
PASTA_VIEWS = ["refinamento", "semarh_painel", "chefia_gabinete", "selos_ambientais"]

EDICOES = [
    {
        "titulo": "Selo Ambiental 2026",
        "pasta": "selos_ambientais_2026",
        "notebook": "semarh_painel/refinamento_selo_ambiental.ipynb",
        "arquivo": "sermarh_painel/selo_ambiental_2026.parquet",
        "dataset": 'minio.entrada."sermarh_painel"."selo_ambiental_2026.parquet"',
        "views": {
            "selo_ambiental": "semarh_painel",
            "selo_ambiental_fases": "semarh_painel_fases",
            "por_tipo_de_selo": "semarh_painel_por_selo",
            "por_criterios_atendidos": "semarh_painel_por_criterios",
        },
        # A view que a aba do painel consulta — sinalizada na notificacao para
        # quem for mexer saber qual delas nao pode quebrar.
        "principal": "selo_ambiental_fases",
    },
    {
        "titulo": "Selo Ambiental 2025",
        "pasta": "selos_ambientais_2025",
        "notebook": "semarh_painel/refinamento_selo_ambiental_2025.ipynb",
        "arquivo": "sermarh_painel/selo_ambiental_2025.parquet",
        "dataset": 'minio.entrada."sermarh_painel"."selo_ambiental_2025.parquet"',
        "views": {
            "selo_ambiental": "semarh_painel_2025",
            "selo_ambiental_fases": "semarh_painel_2025_fases",
            "por_tipo_de_selo": "semarh_painel_2025_por_selo",
            "por_criterios_atendidos": "semarh_painel_2025_por_criterios",
        },
        "principal": "selo_ambiental_fases",
    },
]

# Derivados — nada aqui se mantem na mao.
# A carga so termina bem se TODOS os notebooks passarem: uma edicao com dado
# inconsistente nao deixa o painel meio atualizado.
NOTEBOOKS = [e["notebook"] for e in EDICOES]
FONTES_BRUTAS = [e["dataset"] for e in EDICOES]
# Tabela Iceberg -> edicao a que pertence. E o que permite agrupar o manifesto
# (que vem achatado do `lakehouse.gravar`) por edicao na notificacao.
EDICAO_DA_TABELA = {
    f"nessie.refinamento.{tabela}": edicao["titulo"]
    for edicao in EDICOES for tabela in edicao["views"].values()
}
# A conferencia final consulta pelo MESMO caminho que o painel usa — se a view
# quebrar, a carga acusa em vez de deixar o painel cair sozinho depois.
TABELA_CONFERE = os.getenv(
    "TABELA_CONFERE",
    ".".join(PASTA_VIEWS + [EDICOES[0]["pasta"], EDICOES[0]["principal"]]),
)

DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _por_extenso(carimbo: str | None) -> str:
    """ISO -> "quinta, 13/08/2026 às 11:31" (fuso da stack)."""
    if not carimbo:
        return "—"
    try:
        quando = datetime.fromisoformat(carimbo).astimezone(FUSO)
    except ValueError:
        return carimbo
    return f"{DIAS[quando.weekday()]}, {quando:%d/%m/%Y às %H:%M}"


app = Celery("painel", broker=BROKER, backend=BROKER)
app.conf.update(
    timezone=str(FUSO),
    enable_utc=False,
    task_track_started=True,
    # O refinamento leva ~1 min; o teto generoso cobre um Dremio frio.
    task_time_limit=25 * 60,
    task_soft_time_limit=20 * 60,
    # Cada execucao sobe um driver Spark. Reciclar o processo devolve a memoria
    # em vez de acumular ao longo do dia.
    worker_max_tasks_per_child=4,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "atualizar-painel": {
            "task": "painel.atualizar",
            # Uma carga por dia, no horario comercial de abertura. O crontab do
            # Celery usa o `timezone` acima — nao o UTC do container.
            "schedule": crontab(hour=_hora, minute=_minuto),
        }
    },
)


def _autenticar_dremio() -> tuple[str, str]:
    """(URL base HTTP, token) da conta de servico do painel (vars.env)."""
    from dotenv import load_dotenv
    from dremio_simple_query.connect import get_token

    if VARS_ENV.exists():
        load_dotenv(VARS_ENV)
    base = "http://" + os.getenv("DREMIO_ENDPOINT", "dremio:9047")
    token = get_token(
        uri=f"{base}/apiv2/login",
        payload={
            "userName": os.getenv("DREMIO_USERNAME"),
            "password": os.getenv("DREMIO_PASSWORD"),
        },
    )
    return base, token


def _conexao_dremio():
    """Conexao Arrow Flight — e por ela que passam consultas e DDL de view."""
    from dremio_simple_query.connect import DremioConnection

    _, token = _autenticar_dremio()
    return DremioConnection(token, f"grpc://{os.getenv('DREMIO_FLIGHT_ENDPOINT', 'dremio:32010')}")


def _garantir_views(conexao) -> None:
    """Recria as pastas e as views curadas que o painel consulta.

    Pasta em *space* nao se cria por SQL (`CREATE FOLDER` so vale para fonte
    versionada) e `CREATE VIEW` nao cria os niveis intermediarios sozinho — daí
    as pastas irem pela API REST do catalogo e as views por SQL.

    Idempotente de ponta a ponta: pasta que ja existe e pulada, view que ja
    aponta para a mesma tabela e reescrita igual.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    base, token = _autenticar_dremio()
    cabecalhos = {"Content-Type": "application/json",
                  "Authorization": "_dremio" + token}

    def existe(caminho: list[str]) -> bool:
        endereco = f"{base}/api/v3/catalog/by-path/" + urllib.parse.quote("/".join(caminho))
        try:
            urllib.request.urlopen(urllib.request.Request(endereco, headers=cabecalhos))
            return True
        except urllib.error.HTTPError as erro:
            if erro.code == 404:
                return False
            raise

    def criar_pasta(caminho: list[str]) -> None:
        if existe(caminho):
            return
        pedido = urllib.request.Request(
            f"{base}/api/v3/catalog",
            data=json.dumps({"entityType": "folder", "path": caminho}).encode(),
            method="POST", headers=cabecalhos,
        )
        try:
            urllib.request.urlopen(pedido)
        except urllib.error.HTTPError as erro:
            if erro.code != 409:  # 409 = outra execucao criou primeiro
                raise
        log.info("pasta criada no Dremio: %s", "/".join(caminho))

    # O primeiro nivel e o proprio space, que ja existe e nao se cria por aqui.
    for nivel in range(2, len(PASTA_VIEWS) + 1):
        criar_pasta(PASTA_VIEWS[:nivel])
    for edicao in EDICOES:
        criar_pasta(PASTA_VIEWS + [edicao["pasta"]])
        for view, tabela in edicao["views"].items():
            alvo = ".".join(PASTA_VIEWS + [edicao["pasta"], view])
            conexao.toPandas(
                f"CREATE OR REPLACE VIEW {alvo} AS "
                f"SELECT * FROM nessie.refinamento.{tabela} AT BRANCH main"
            )


def _gravar_estado(dados: dict) -> None:
    """Escreve o carimbo de forma atomica (o painel le esse arquivo a todo run)."""
    ARQUIVO_ESTADO.parent.mkdir(parents=True, exist_ok=True)
    temporario = ARQUIVO_ESTADO.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2))
    temporario.replace(ARQUIVO_ESTADO)


def _ler_estado() -> dict:
    try:
        return json.loads(ARQUIVO_ESTADO.read_text())
    except Exception:
        return {}


def _registrar_historico(estado: dict) -> None:
    """Anexa a execucao ao historico (uma linha JSON por carga)."""
    try:
        ARQUIVO_HISTORICO.parent.mkdir(parents=True, exist_ok=True)
        with ARQUIVO_HISTORICO.open("a") as arquivo:
            arquivo.write(json.dumps(estado, ensure_ascii=False) + "\n")
    except Exception as erro:
        log.warning("não foi possível gravar o histórico: %s", erro)


def _ler_manifesto(caminho: Path) -> list[dict]:
    """Tabelas publicadas na execucao (escritas por `lakehouse.gravar`).

    Vale para qualquer notebook do pipeline, nao so o do Selo Ambiental: quem
    grava com o helper aparece aqui — e, portanto, na notificacao.
    """
    tabelas: dict[str, dict] = {}
    try:
        for linha in caminho.read_text().splitlines():
            registro = json.loads(linha)
            tabelas[registro["tabela"]] = registro  # a ultima gravacao vale
    except FileNotFoundError:
        return []
    except Exception as erro:
        log.warning("manifesto ilegível: %s", erro)
        return []
    finally:
        caminho.unlink(missing_ok=True)
    return sorted(tabelas.values(), key=lambda r: r["tabela"])


def _duracao(segundos: float | None) -> str:
    """90.4 -> "1min 30s" — a leitura e sempre "quanto demorou", nao "quantos s"."""
    if not segundos:
        return "—"
    minutos, resto = divmod(int(segundos), 60)
    return f"{minutos}min {resto:02d}s" if minutos else f"{resto}s"


def _variacao(linhas: int, antes: int | None) -> str:
    """" (+12)" desde a carga anterior; vazio se nao mudou ou se e a primeira."""
    if antes is None or antes == linhas:
        return ""
    return f" <b>({linhas - antes:+d})</b>"


def _bloco_edicao(edicao: dict, estado: dict, anteriores: dict[str, int]) -> list[str]:
    """Uma seção da notificação: o caminho completo do dado de UMA edição.

    A ordem das subseções é a ordem em que o dado anda — arquivo no MinIO →
    dataset no Dremio → notebook no Spark → tabelas no Nessie → views no space.
    Quem lê de cima para baixo lê o pipeline.
    """
    linhas_origem = estado.get("linhas_origem") or {}
    publicadas = {t["tabela"]: t["linhas"] for t in (estado.get("tabelas") or [])}
    total_origem = linhas_origem.get(edicao["dataset"])

    linhas = [
        f"<b>▊ {html.escape(edicao['titulo'])}</b>",
        "",
        f"<u>Origem</u> · MinIO, zona <code>{ZONA_ENTRADA}</code>",
        f"    arquivo · <code>{html.escape(edicao['arquivo'])}</code>"
        + (f" — {total_origem} linhas" if total_origem is not None else ""),
        f"    dataset · <code>{html.escape(edicao['dataset'])}</code>",
        "",
        "<u>Refinamento</u> · Spark",
        f"    notebook · <code>{html.escape(edicao['notebook'])}</code>",
        "",
        f"<u>Tabelas</u> · Iceberg, zona <code>{ZONA_ARMAZEM}</code>, catálogo Nessie",
    ]
    # Percorre as tabelas DESTA edicao na ordem declarada, nao a ordem alfabetica
    # do manifesto: assim a principal (`_fases`) nao cai no meio da lista.
    for tabela in edicao["views"].values():
        completo = f"nessie.refinamento.{tabela}"
        if completo not in publicadas:
            linhas.append(f"    ✗ <code>{html.escape(tabela)}</code> — não publicada nesta carga")
            continue
        n = publicadas[completo]
        linhas.append(f"    • <code>{html.escape(tabela)}</code> — {n} linhas"
                      + _variacao(n, anteriores.get(completo)))

    caminho = " › ".join(PASTA_VIEWS[1:] + [edicao["pasta"]])
    linhas += [
        "",
        f"<u>Views</u> · space <code>{PASTA_VIEWS[0]}</code>",
        f"    {html.escape(caminho)}",
    ]
    for view in edicao["views"]:
        marca = "  ← lida pelo painel" if view == edicao.get("principal") else ""
        linhas.append(f"    • <code>{html.escape(view)}</code>{marca}")
    return linhas


def _mensagem(estado: dict, anteriores: dict[str, int]) -> str:
    """Aviso do Telegram, uma seção por edição.

    "Onde o dado mora" importa porque a mesma informação aparece com quatro
    nomes diferentes ao longo do caminho: o arquivo no MinIO, o dataset que o
    Dremio promoveu, a tabela Iceberg no Nessie e a view no space. A seção de
    cada edição mostra os quatro na ordem em que o dado passa por eles.
    """
    etapas = estado.get("etapas") or {}
    origem = estado.get("origem", "")
    cabecalho = [
        "🟢 <b>Painel SEMARH — dados atualizados</b>",
        f"<i>{_por_extenso(estado['atualizado_em'])} · carga {origem} · "
        f"{_duracao(estado.get('duracao_s'))}</i>",
    ]
    # Uma etapa que falhou nao derruba a carga (o dado ja esta publicado), mas
    # nao pode passar despercebida no meio da mensagem: vai logo no topo.
    problemas = [nome for nome, situacao in etapas.items() if situacao != "ok"]
    if problemas:
        cabecalho.append(f"⚠️ <b>Com ressalvas:</b> {', '.join(problemas)} — veja os logs.")

    corpo = []
    for edicao in EDICOES:
        corpo += ["", "━━━━━━━━━━━━━━━━━━", ""] + _bloco_edicao(edicao, estado, anteriores)

    # Tabelas publicadas por notebooks fora das edicoes acima — nao somem da
    # notificacao so por nao terem uma secao propria.
    outras = [t for t in (estado.get("tabelas") or [])
              if t["tabela"] not in EDICAO_DA_TABELA]
    if outras:
        corpo += ["", "━━━━━━━━━━━━━━━━━━", "", "<b>▊ Outras tabelas publicadas</b>", ""]
        corpo += [f"    • <code>{html.escape(t['tabela'])}</code> — {t['linhas']} linhas"
                  + _variacao(t["linhas"], anteriores.get(t["tabela"])) for t in outras]

    rodape = [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "<i>Toda carga reescreve as tabelas por inteiro e recria as views; o número em "
        "negrito é a variação de linhas desde a carga anterior.</i>",
    ]
    if estado.get("novidades"):
        rodape += ["", "🔎 <b>Novidades no ambiente</b>",
                   "<i>mudanças desde a carga anterior, inclusive feitas por fora do pipeline</i>"]
        for grupo in estado["novidades"]:
            rodape += ["", f"<u>{html.escape(grupo['titulo'])}</u>"]
            if grupo.get("prefixo"):
                # O prefixo comum vira cabecalho do grupo; os itens abaixo sao
                # so o que os distingue.
                rodape.append(f"    em <code>{html.escape(grupo['prefixo'])}</code>")
            rodape += [f"    • <code>{html.escape(item)}</code>" for item in grupo["itens"]]
            if grupo.get("restantes"):
                rodape.append(f"    <i>… e mais {grupo['restantes']}</i>")
    return "\n".join(cabecalho + corpo + rodape)


@app.task(name="painel.atualizar", bind=True)
def atualizar(self, forcar: bool = False) -> dict:
    """Refaz dataset -> tabelas refinadas -> carimbo para o dashboard.

    Publica o progresso em `update_state` para a barra do botao "Atualizar
    agora" do painel acompanhar. O trecho longo (o notebook no Spark) nao tem
    como reportar de dentro, entao a barra avanca pelo tempo decorrido usando a
    duracao da ULTIMA execucao como estimativa — quanto mais roda, melhor a
    estimativa fica.
    """
    inicio = time.monotonic()
    agora = datetime.now(FUSO)
    etapas: dict[str, str] = {}

    def progresso(percentual: int, etapa: str) -> None:
        self.update_state(state="PROGRESS", meta={"percentual": percentual, "etapa": etapa})

    progresso(5, "Preparando a atualização")

    # 1. datasets: o Dremio so enxerga um parquet novo depois do refresh.
    falhas_refresh = []
    for fonte in FONTES_BRUTAS:
        try:
            _conexao_dremio().toPandas(f"ALTER TABLE {fonte} REFRESH METADATA FORCE UPDATE")
        except Exception as erro:  # nao aborta: o refinamento le do MinIO, nao do Dremio
            falhas_refresh.append(f"{fonte}: {erro}"[:150])
            log.warning("refresh de metadados falhou em %s (segue mesmo assim): %s", fonte, erro)
    etapas["dremio_refresh"] = "; ".join(falhas_refresh)[:300] if falhas_refresh else "ok"
    progresso(20, "Lendo os datasets da zona de entrada")

    # 2. dataframe + analise: os MESMOS notebooks que rodam no JupyterLab, um
    # por edicao. Rodam em sequencia porque cada um sobe o seu driver Spark.
    estimativa = float(_ler_estado().get("duracao_s") or 90)
    # Os notebooks anotam aqui cada tabela que publicarem (ver lakehouse.gravar).
    manifesto = ARQUIVO_ESTADO.parent / f".manifesto-{self.request.id}.jsonl"
    falhou = None
    for indice, notebook in enumerate(NOTEBOOKS):
        # A barra cobre os 70 pontos divididos entre os notebooks; dentro de cada
        # fatia ela anda pelo tempo decorrido, com a duracao da carga anterior
        # como estimativa.
        base = 20 + int(70 * indice / len(NOTEBOOKS))
        fatia = 70 / len(NOTEBOOKS)
        comeco = time.monotonic()
        with tempfile.TemporaryDirectory() as tmp:
            processo = subprocess.Popen(
                ["jupyter", "nbconvert", "--to", "notebook", "--execute",
                 "--ExecutePreprocessor.timeout=900",
                 "--output", str(Path(tmp) / "execucao.ipynb"), notebook],
                cwd=DIR_NOTEBOOKS, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={**os.environ, "MANIFESTO_PUBLICACAO": str(manifesto)},
            )
            while processo.poll() is None:
                decorrido = time.monotonic() - comeco
                fracao = min(decorrido / max(estimativa / len(NOTEBOOKS), 1), 1.0)
                progresso(base + int(fatia * fracao),
                          f"Refinando os dados no Spark ({Path(notebook).stem})")
                time.sleep(2)
            saida, erro_saida = processo.communicate()
        if processo.returncode != 0:
            falhou = (notebook, (erro_saida or saida or "")[-1500:])
            break
    if falhou:
        # As validacoes do notebook viram assert: se o dado chegou inconsistente,
        # a tarefa falha e as tabelas antigas continuam no ar (nada e publicado
        # pela metade). O erro fica no log e no carimbo.
        notebook, cauda = falhou
        manifesto.unlink(missing_ok=True)
        etapas["refinamento"] = f"falhou em {notebook}"
        falha = {
            "atualizado_em": None,
            "falhou_em": datetime.now(FUSO).isoformat(timespec="seconds"),
            "duracao_s": round(time.monotonic() - inicio, 1),
            "origem": "manual" if forcar else "automática",
            "etapas": etapas,
            "erro": cauda[-600:],
            "tarefa": self.request.id,
        }
        _gravar_estado({**_ler_estado(), "ultima_falha_em": falha["falhou_em"],
                        "erro": falha["erro"], "etapas": etapas})
        _registrar_historico(falha)
        notificacao.enviar(
            "🔴 <b>Painel SEMARH — falha na atualização</b>\n"
            f"Quando: {_por_extenso(falha['falhou_em'])}\n"
            f"Origem: {falha['origem']}\n"
            f"<pre>{html.escape(cauda[-500:])}</pre>",
            evento="falha",
        )
        raise RuntimeError(f"notebook de refinamento {notebook} falhou:\n{cauda}")
    etapas["refinamento"] = "ok"
    tabelas = _ler_manifesto(manifesto)

    # 3. views curadas: o caminho pelo qual o painel enxerga o dado. Vem DEPOIS
    # do refinamento (as tabelas ja existem) e ANTES da conferencia, que passa
    # por elas de proposito.
    progresso(90, "Publicando as views no Dremio")
    try:
        _garantir_views(_conexao_dremio())
        etapas["views"] = "ok"
    except Exception as erro:
        # Nao aborta: o dado esta publicado nas tabelas. Mas a conferencia logo
        # abaixo consulta pela view, entao uma falha aqui nao passa despercebida.
        etapas["views"] = f"falhou: {erro}"[:300]
        log.warning("não consegui recriar as views curadas: %s", erro)

    # 4. confere e carimba — o carimbo e a chave de cache do dashboard.
    progresso(92, "Conferindo as tabelas publicadas")
    linhas = None
    linhas_origem: dict[str, int] = {}
    try:
        conexao = _conexao_dremio()
        linhas = int(conexao.toPandas(f"SELECT COUNT(*) AS n FROM {TABELA_CONFERE}")["n"][0])
        for fonte in FONTES_BRUTAS:
            linhas_origem[fonte] = int(
                conexao.toPandas(f"SELECT COUNT(*) AS n FROM {fonte}")["n"][0]
            )
        etapas["conferencia"] = "ok"
    except Exception as erro:
        etapas["conferencia"] = f"falhou: {erro}"[:300]

    # Linhas de cada tabela na carga anterior — vira a variacao na mensagem.
    anteriores = {t["tabela"]: t["linhas"] for t in (_ler_estado().get("tabelas") or [])}

    # 5. varredura do ambiente: o que mudou no Dremio e no MinIO desde a carga
    # anterior — inclusive coisa criada por fora do pipeline.
    progresso(96, "Varrendo o catálogo")
    try:
        foto = inventario.coletar(_conexao_dremio())
        novidades = inventario.diferencas(_ler_estado().get("inventario") or {}, foto)
        etapas["varredura"] = "ok"
    except Exception as erro:
        foto, novidades = {}, []
        etapas["varredura"] = f"falhou: {erro}"[:300]
        log.warning("varredura do ambiente falhou: %s", erro)

    # Carimbo com a hora do FIM: e o que o painel mostra como "atualizado em".
    estado = {
        "atualizado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
        "iniciado_em": agora.isoformat(timespec="seconds"),
        "duracao_s": round(time.monotonic() - inicio, 1),
        "edicoes": [{"titulo": e["titulo"], "arquivo": e["arquivo"]} for e in EDICOES],
        "tabelas": tabelas,
        "linhas": linhas,
        "linhas_origem": linhas_origem,
        "origem": "manual" if forcar else "automática",
        "hora_agendada": HORA_ATUALIZACAO,
        "fuso": str(FUSO),
        "novidades": novidades,
        "etapas": etapas,
        "tarefa": self.request.id,
    }
    progresso(100, "Concluído")
    # A foto do ambiente fica so no estado (e grande); no historico vai o diff.
    _gravar_estado({**estado, "inventario": foto})
    _registrar_historico(estado)

    notificacao.enviar(_mensagem(estado, anteriores), evento="sucesso")

    log.info("painel atualizado: %s", estado)
    return estado
