"""Atualizacao automatica do painel — app Celery (worker + beat).

Todo dia as `HORA_ATUALIZACAO` (07:00 por padrao), no fuso **America/Fortaleza**,
a tarefa `painel.atualizar` refaz o caminho inteiro do dado:

1. **Dataset**  — manda o Dremio reler os metadados do parquet da zona de
   entrada, para enxergar um arquivo novo publicado no MinIO.
2. **DataFrame + analise** — reexecuta o notebook de refinamento no Spark, que
   regrava `refinamento.semarh_painel`, `..._fases` e os dois resumos. E o mesmo
   notebook que uma pessoa roda no JupyterLab: nao ha logica duplicada aqui.
3. **Dashboard** — grava o carimbo da atualizacao num arquivo compartilhado com
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
NOTEBOOK = os.getenv("NOTEBOOK_REFINAMENTO", "semarh_painel/refinamento_selo_ambiental.ipynb")
ARQUIVO_ESTADO = Path(os.getenv("ARQUIVO_ESTADO", "/estado/atualizacao.json"))
# Observabilidade: uma linha JSON por execucao, append-only. E a fonte do
# historico que aparece no painel e do "o que mudou" da notificacao.
ARQUIVO_HISTORICO = Path(os.getenv("ARQUIVO_HISTORICO", "/estado/historico.jsonl"))
# Nome amigavel do dataset de origem, so para a mensagem.
DATASET = os.getenv("DATASET_ORIGEM", "sermarh_painel/selo_ambiental_2026.parquet")
# Zonas do object store, so para dizer ONDE cada coisa mora na mensagem.
ZONA_ENTRADA = os.getenv("ZONA_ENTRADA", "entrada")
ZONA_ARMAZEM = os.getenv("ZONA_ARMAZEM", "armazem")
VARS_ENV = Path(os.getenv("VARS_ENV", "/opt/painel/vars.env"))
# Fonte bruta no Dremio (o parquet da zona de entrada, promovido como dataset).
FONTE_BRUTA = os.getenv(
    "FONTE_BRUTA_DREMIO",
    'minio.entrada."sermarh_painel"."selo_ambiental_2026.parquet"',
)
TABELA_CONFERE = os.getenv("TABELA_CONFERE", "nessie.refinamento.semarh_painel_fases")

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


def _conexao_dremio():
    """Conexao Arrow Flight com a conta de servico do painel (vars.env)."""
    from dotenv import load_dotenv
    from dremio_simple_query.connect import DremioConnection, get_token

    if VARS_ENV.exists():
        load_dotenv(VARS_ENV)
    endpoint = os.getenv("DREMIO_ENDPOINT", "dremio:9047")
    token = get_token(
        uri=f"http://{endpoint}/apiv2/login",
        payload={
            "userName": os.getenv("DREMIO_USERNAME"),
            "password": os.getenv("DREMIO_PASSWORD"),
        },
    )
    return DremioConnection(token, f"grpc://{os.getenv('DREMIO_FLIGHT_ENDPOINT', 'dremio:32010')}")


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


def _mensagem(estado: dict, anteriores: dict[str, int]) -> str:
    """Aviso do Telegram: o que foi publicado, ONDE mora e o que variou.

    "Onde" importa porque o mesmo dado aparece em três lugares com nomes
    diferentes: o arquivo no MinIO, a tabela Iceberg no catálogo Nessie e o
    caminho pelo qual o Dremio a serve.
    """
    partes = [
        "🟢 <b>Dados atualizados</b>",
        _por_extenso(estado["atualizado_em"]),
        "",
        f"📥 <b>Origem</b> — MinIO, zona <code>{ZONA_ENTRADA}</code>",
        f"<code>{html.escape(DATASET)}</code>"
        + (f" — {estado['linhas_origem']} linhas" if estado.get("linhas_origem") else ""),
        f"no Dremio: <code>{html.escape(FONTE_BRUTA)}</code>",
        "",
        f"📦 <b>Tabelas reescritas</b> — Iceberg na zona <code>{ZONA_ARMAZEM}</code> do MinIO, "
        "catálogo Nessie:",
    ]
    for tabela in estado.get("tabelas") or []:
        antes = anteriores.get(tabela["tabela"])
        delta = ""
        if antes is not None and antes != tabela["linhas"]:
            delta = f" ({tabela['linhas'] - antes:+d})"
        partes.append(f"• <code>{html.escape(tabela['tabela'])}</code> — {tabela['linhas']} linhas{delta}")
    if not estado.get("tabelas"):
        partes.append("(nenhuma tabela publicada)")
    partes.append(
        "\n<i>Toda carga reescreve as tabelas por inteiro; o número entre parênteses é a "
        "variação de linhas desde a carga anterior.</i>"
    )
    if estado.get("novidades"):
        partes.append("\n🔎 <b>Novidades no ambiente:</b>")
        partes += [f"• {html.escape(n)}" for n in estado["novidades"]]
    return "\n".join(partes)


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

    # 1. dataset: o Dremio so enxerga um parquet novo depois do refresh.
    try:
        _conexao_dremio().toPandas(f"ALTER TABLE {FONTE_BRUTA} REFRESH METADATA FORCE UPDATE")
        etapas["dremio_refresh"] = "ok"
    except Exception as erro:  # nao aborta: o refinamento le do MinIO, nao do Dremio
        etapas["dremio_refresh"] = f"falhou: {erro}"[:300]
        log.warning("refresh de metadados falhou (segue mesmo assim): %s", erro)
    progresso(20, "Lendo o dataset da zona de entrada")

    # 2. dataframe + analise: o MESMO notebook que roda no JupyterLab.
    estimativa = float(_ler_estado().get("duracao_s") or 90)
    # O notebook anota aqui cada tabela que publicar (ver lakehouse.gravar).
    manifesto = ARQUIVO_ESTADO.parent / f".manifesto-{self.request.id}.jsonl"
    with tempfile.TemporaryDirectory() as tmp:
        processo = subprocess.Popen(
            ["jupyter", "nbconvert", "--to", "notebook", "--execute",
             "--ExecutePreprocessor.timeout=900",
             "--output", str(Path(tmp) / "execucao.ipynb"), NOTEBOOK],
            cwd=DIR_NOTEBOOKS, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "MANIFESTO_PUBLICACAO": str(manifesto)},
        )
        while processo.poll() is None:
            fracao = min((time.monotonic() - inicio) / max(estimativa, 1), 1.0)
            progresso(20 + int(70 * fracao), "Refinando os dados no Spark")
            time.sleep(2)
        saida, erro_saida = processo.communicate()
        processo.stdout_texto, processo.stderr_texto = saida, erro_saida
    if processo.returncode != 0:
        # As validacoes do notebook viram assert: se o dado chegou inconsistente,
        # a tarefa falha e as tabelas antigas continuam no ar (nada e publicado
        # pela metade). O erro fica no log e no carimbo.
        cauda = (processo.stderr_texto or processo.stdout_texto or "")[-1500:]
        etapas["refinamento"] = "falhou"
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
        raise RuntimeError(f"notebook de refinamento falhou:\n{cauda}")
    etapas["refinamento"] = "ok"
    tabelas = _ler_manifesto(manifesto)

    # 3. confere e carimba — o carimbo e a chave de cache do dashboard.
    progresso(92, "Conferindo as tabelas publicadas")
    linhas = linhas_origem = None
    try:
        conexao = _conexao_dremio()
        linhas = int(conexao.toPandas(f"SELECT COUNT(*) AS n FROM {TABELA_CONFERE}")["n"][0])
        linhas_origem = int(conexao.toPandas(f"SELECT COUNT(*) AS n FROM {FONTE_BRUTA}")["n"][0])
        etapas["conferencia"] = "ok"
    except Exception as erro:
        etapas["conferencia"] = f"falhou: {erro}"[:300]

    # Linhas de cada tabela na carga anterior — vira a variacao na mensagem.
    anteriores = {t["tabela"]: t["linhas"] for t in (_ler_estado().get("tabelas") or [])}

    # 4. varredura do ambiente: o que mudou no Dremio e no MinIO desde a carga
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
        "dataset": DATASET,
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
