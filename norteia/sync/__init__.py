"""Sincronização entre aparelhos: o servidor guarda tudo e cada aparelho conversa só com ele."""
from .cliente import Resumo, Sincronizador
from .serial import aplicar, empacotar

__all__ = ["Sincronizador", "Resumo", "empacotar", "aplicar"]
