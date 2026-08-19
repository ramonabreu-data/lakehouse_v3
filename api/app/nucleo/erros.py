"""Erros de negocio. Sem HTTP: quem traduz para status code e `web/erros.py`."""

from __future__ import annotations


class ErroDeValidacao(ValueError):
    """Pedido do cliente fora do contrato do conjunto."""


class ConjuntoDesconhecido(KeyError):
    """Slug pedido nao esta publicado."""


class CatalogoInvalido(RuntimeError):
    """Catalogo malformado. Estoura no import — antes de a API aceitar trafego."""


class FonteIndisponivel(RuntimeError):
    """A origem do dado nao respondeu. Vira HTTP 502.

    Existe para que `servicos/` nao precise conhecer status HTTP nem `web/`
    precise conhecer as excecoes de cada motor (Flight, driver, requests...).
    """
