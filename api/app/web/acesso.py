"""Porta de entrada: quem esta chamando e se pode chamar de novo.

Os dois modos sao declarados como esquemas de seguranca do OpenAPI (e nao lidos
direto de `request.headers`) porque e o que faz o /docs mostrar o botao
"Authorize". Sem isso, quem esta integrando nao consegue experimentar endpoint
nenhum pela pagina — toda chamada volta 401.

auto_error=False nos dois: quem decide o que fazer sem credencial e a funcao
abaixo, que responde no formato de erro da API. Deixar o FastAPI recusar sozinho
devolveria {"detail": ...}, fora do contrato.
"""

from __future__ import annotations

import logging

from fastapi import Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app import seguranca
from app.web import erros

registrador = logging.getLogger(__name__)

chave_de_aplicacao = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ChaveDeAplicacao",
    description="Chave de aplicacao (servidor-a-servidor), do API_CHAVES no .env da stack.",
    auto_error=False,
)

token_do_supabase = HTTPBearer(
    scheme_name="TokenSupabase",
    description=(
        "Token de acesso do Supabase GoTrue — o mesmo que o painel recebe no login. "
        "Cole so o token, sem o prefixo `Bearer`. Uma chave de aplicacao tambem e aceita aqui."
    ),
    auto_error=False,
)


def exigir_acesso(
    request: Request,
    chave: str | None = Security(chave_de_aplicacao),
    portador: HTTPAuthorizationCredentials | None = Security(token_do_supabase),
) -> seguranca.Identidade:
    if seguranca.auth_ativa():
        autorizacao = f"{portador.scheme} {portador.credentials}" if portador else None
        identidade = seguranca.identificar(chave, autorizacao)
        if identidade is None:
            raise erros.nao_autenticado()
    else:
        identidade = seguranca.Identidade(
            "anonimo", request.client.host if request.client else "desconhecido"
        )

    limitador = request.app.state.limitador
    if not limitador.permitir(identidade.rotulo):
        registrador.warning("Limite por minuto atingido por %s.", identidade.rotulo)
        raise erros.excedeu_o_limite(limitador.por_minuto)
    request.state.identidade = identidade
    return identidade
