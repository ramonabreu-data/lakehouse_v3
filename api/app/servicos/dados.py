"""Do pedido do cliente ate a resposta pronta.

O caminho e sempre o mesmo, para qualquer conjunto e qualquer fonte:

    query string -> nucleo valida -> motor da Fonte consulta -> cache guarda

Trocar a fonte de um conjunto (de Dremio para outra coisa) nao mexe em nada
deste arquivo: a escolha do motor sai de `conjunto.fonte.motor`.
"""

from __future__ import annotations

import logging

from app.motores.arrow import tabela_para_registros
from app.motores.base import Motor
from app.nucleo import Conjunto, FonteIndisponivel, analisar_parametros, analisar_resumo
from app.servicos import estado
from app.servicos.cache import Cache

registrador = logging.getLogger(__name__)


class Servico:
    def __init__(self, motores: dict[str, Motor], cache: Cache) -> None:
        self.motores = motores
        self.cache = cache

    # -- apoio --------------------------------------------------------------

    def motor(self, conjunto: Conjunto) -> Motor:
        try:
            return self.motores[conjunto.fonte.motor]
        except KeyError as exc:  # pragma: no cover — o catalogo confere no import
            raise FonteIndisponivel(f"motor `{conjunto.fonte.motor}` nao construido") from exc

    def _chave(self, operacao: str, conjunto: Conjunto, params: dict[str, list[str]], versao: str) -> str:
        """Chave estavel a partir do pedido cru, mais a versao do dado.

        A versao vem do carimbo da ultima carga: quando o refinamento publica
        dado novo, todas as chaves mudam de uma vez — sem esperar o TTL.
        """
        assinatura = ";".join(f"{c}={','.join(v)}" for c, v in sorted(params.items()))
        return self.cache.chave(operacao, conjunto.slug, assinatura, versao)

    def _executar(self, conjunto: Conjunto, acao, *argumentos):
        """Chama o motor traduzindo qualquer falha dele para FonteIndisponivel.

        A mensagem original fica no log: erro de fonte costuma trazer endereco
        interno e, no pior caso, credencial.
        """
        try:
            return acao(*argumentos)
        except Exception as exc:  # noqa: BLE001
            registrador.exception(
                "Falha na fonte `%s` (motor %s) do conjunto `%s`.",
                conjunto.fonte.endereco, conjunto.fonte.motor, conjunto.slug,
            )
            raise FonteIndisponivel(conjunto.fonte.motor) from exc

    # -- operacoes ----------------------------------------------------------

    def dados(self, conjunto: Conjunto, params: dict[str, list[str]]) -> dict:
        consulta = analisar_parametros(conjunto, params)
        versao = estado.versao_do_dado()
        chave = self._chave("dados", conjunto, params, versao)

        guardado = self.cache.obter(chave)
        if guardado is not None:
            return guardado

        motor = self.motor(conjunto)
        registros = tabela_para_registros(self._executar(conjunto, motor.dados, conjunto, consulta))
        total = (
            self._executar(conjunto, motor.total, conjunto, consulta)
            if consulta.incluir_total
            else None
        )

        corpo = {
            "conjunto": conjunto.slug,
            "titulo": conjunto.titulo,
            "fonte": conjunto.fonte.endereco,
            "motor": conjunto.fonte.motor,
            "atualizado_em": versao or None,
            "paginacao": {
                "limite": consulta.limite,
                "deslocamento": consulta.deslocamento,
                "retornados": len(registros),
                "total": total,
            },
            "dados": registros,
        }
        self.cache.guardar(chave, corpo)
        return corpo

    def resumo(self, conjunto: Conjunto, params: dict[str, list[str]]) -> dict:
        pedido = analisar_resumo(conjunto, params)
        versao = estado.versao_do_dado()
        chave = self._chave("resumo", conjunto, params, versao)

        guardado = self.cache.obter(chave)
        if guardado is not None:
            return guardado

        motor = self.motor(conjunto)
        tabela = self._executar(conjunto, motor.resumo, conjunto, pedido)
        corpo = {
            "conjunto": conjunto.slug,
            "agrupado_por": list(pedido.agrupar_por),
            "metrica": pedido.metrica,
            "funcao": pedido.funcao if pedido.metrica else None,
            "atualizado_em": versao or None,
            "dados": tabela_para_registros(tabela),
        }
        self.cache.guardar(chave, corpo)
        return corpo

    def verificar(self) -> None:
        """Prontidao: todo motor construido precisa responder."""
        for motor in self.motores.values():
            motor.verificar()
