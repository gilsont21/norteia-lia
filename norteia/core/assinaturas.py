"""Assinaturas de calendário: lê um endereço .ics (Google Agenda, Outlook, feriados) e mostra no calendário.

Somente leitura. No Google Agenda use "Endereço secreto no formato iCal" (Configurações do calendário).
O endereço é como uma senha: quem tem pode ver o calendário. Fica guardado só neste aparelho.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from datetime import date, datetime

from . import ics
from .db import Banco
from .models import agora_utc

CORES = ["#4dd0b1", "#b57edc", "#f5a623", "#4772fa", "#f0524a"]


class ErroAssinatura(Exception):
    pass


def normalizar_url(url: str) -> str:
    url = url.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not url.lower().startswith(("http://", "https://")):
        raise ErroAssinatura("O endereço precisa começar com https:// (ou webcal://).")
    return url


def baixar(url: str, timeout: float = 20.0) -> str:
    """Só rede (sem banco): pode rodar numa thread."""
    req = urllib.request.Request(normalizar_url(url), headers={"User-Agent": "Norteia/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            bruto = resp.read(20 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        raise ErroAssinatura(f"O servidor respondeu erro {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroAssinatura(f"Não consegui baixar o calendário: {e}") from e
    texto = bruto.decode("utf-8", errors="replace")
    if "BEGIN:VCALENDAR" not in texto:
        raise ErroAssinatura("O endereço não devolveu um calendário .ics.")
    return texto


class Assinaturas:
    def __init__(self, banco: Banco):
        self.banco = banco

    def listar(self, origem: str | None = None) -> list[dict]:
        """Todas as assinaturas; `origem` = "ics" (endereço .ics) ou "google" (calendários da conta Google)."""
        sql, args = "SELECT * FROM assinatura", ()
        if origem is not None:
            sql, args = sql + " WHERE origem=?", (origem,)
        return [dict(l) for l in self.banco.con.execute(sql + " ORDER BY id", args)]

    def adicionar(self, nome: str, url: str, cor: str | None = None) -> int:
        url = normalizar_url(url)
        nome = nome.strip() or "Calendário"
        cor = cor or CORES[len(self.listar()) % len(CORES)]
        cur = self.banco.con.execute("INSERT INTO assinatura(nome, url, cor) VALUES (?,?,?)", (nome, url, cor))
        self.banco.con.commit()
        return cur.lastrowid

    def remover(self, assinatura_id: int) -> None:
        self.banco.con.execute("DELETE FROM assinatura WHERE id=?", (assinatura_id,))
        self.banco.con.commit()

    def aplicar_texto(self, assinatura_id: int, texto: str, tz_destino=None) -> int:
        """Troca os eventos guardados pelos do texto .ics. Devolve quantos eventos ficaram."""
        eventos = [e for e in ics.ler_ics(texto, tz_destino) if e.tipo == "VEVENT"]
        con = self.banco.con
        con.execute("DELETE FROM evento_externo WHERE assinatura_id=?", (assinatura_id,))
        for e in eventos:
            fim = e.fim.isoformat() if e.fim is not None else None
            con.execute(
                "INSERT INTO evento_externo(assinatura_id, uid, titulo, inicio, fim, dia_inteiro, regra, local)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (assinatura_id, e.uid, e.titulo, e.inicio.isoformat(), fim, int(e.dia_inteiro), e.regra, e.local))
        con.execute("UPDATE assinatura SET ultima_sync=?, erro='' WHERE id=?", (agora_utc().isoformat(), assinatura_id))
        con.commit()
        return len(eventos)

    def registrar_erro(self, assinatura_id: int, erro: str) -> None:
        self.banco.con.execute("UPDATE assinatura SET erro=? WHERE id=?", (erro, assinatura_id))
        self.banco.con.commit()

    def atualizar(self, assinatura_id: int) -> int:
        """Baixa e aplica (bloqueia: na tela, use `baixar` numa thread e depois `aplicar_texto`)."""
        ass = next((a for a in self.listar() if a["id"] == assinatura_id), None)
        if ass is None:
            raise ValueError("assinatura não encontrada")
        try:
            texto = baixar(ass["url"])
        except ErroAssinatura as e:
            self.registrar_erro(assinatura_id, str(e))
            raise
        return self.aplicar_texto(assinatura_id, texto)
