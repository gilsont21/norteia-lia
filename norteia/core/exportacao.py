"""Importar e exportar: backup JSON, CSV (inclusive backups de outros apps de tarefas) e calendário .ics."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from dateutil import parser as _parser
from dateutil import tz as _tz

from . import ics, recorrencia
from .models import Prioridade, Tarefa, agora_utc

FORMATO_BACKUP = "tarefas-backup"


@dataclass
class ResultadoImportacao:
    tarefas: int = 0
    subtarefas: int = 0
    listas: int = 0
    ignoradas: int = 0
    avisos: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        partes = [f"{self.tarefas} tarefa(s)"]
        if self.subtarefas:
            partes.append(f"{self.subtarefas} subtarefa(s)")
        if self.listas:
            partes.append(f"{self.listas} lista(s) nova(s)")
        if self.ignoradas:
            partes.append(f"{self.ignoradas} ignorada(s)")
        return "Importado: " + ", ".join(partes) + "."


# ---------------------------------------------------------------- backup JSON
def exportar_json(servico) -> str:
    from ..sync.serial import empacotar
    return json.dumps({
        "formato": FORMATO_BACKUP, "versao": 1, "exportado_em": agora_utc().isoformat(),
        "pacote": empacotar(servico.banco, None)}, ensure_ascii=False, indent=1)


def importar_json(servico, texto: str) -> ResultadoImportacao:
    """Junta um backup ao banco atual. Em conflito vale a versão mais recente (nunca apaga o que existe)."""
    from ..sync.serial import aplicar
    try:
        dados = json.loads(texto)
    except ValueError as e:
        raise ValueError("O arquivo não é um backup válido (JSON ilegível).") from e
    if not isinstance(dados, dict) or dados.get("formato") != FORMATO_BACKUP:
        raise ValueError("O arquivo não é um backup deste app.")
    res = aplicar(servico.banco, dados["pacote"])
    r = ResultadoImportacao()
    r.tarefas = sum(1 for tipo, _ in res.aceitos if tipo == "tarefa")
    r.listas = sum(1 for tipo, _ in res.aceitos if tipo == "projeto")
    r.avisos = [f"{len(res.pendentes)} item(ns) dependiam de algo que não está no backup."] if res.pendentes else []
    return r


# ---------------------------------------------------------------- CSV próprio
COLUNAS_CSV = ["Lista", "Título", "Notas", "Prioridade", "Início", "Prazo", "Hora", "Repetição",
               "Lembretes (minutos antes)", "Etiquetas", "Status", "Criada em", "Concluída em", "Subtarefa de"]
NOME_STATUS = {"": "Aberta", "c": "Concluída", "d": "Não será feito"}


def exportar_csv(servico, incluir_finalizadas: bool = True) -> str:
    """CSV com ponto e vírgula e BOM, para abrir direto no Excel em português."""
    banco = servico.banco
    projetos = {p.id: p.nome for p in banco.listar_projetos() + banco.listar_projetos_arquivados()}
    por_id = {t.id: t for t in banco.consultar("apagada_em IS NULL")}
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    w.writerow(COLUNAS_CSV)
    for t in sorted(por_id.values(), key=lambda x: (x.pai_id is not None, x.ordem, x.id)):
        if t.finalizada and not incluir_finalizadas:
            continue
        status = "Concluída" if t.concluida else "Não será feito" if t.descartada else "Aberta"
        pai = por_id.get(t.pai_id)
        w.writerow([
            projetos.get(t.projeto_id, ""), t.titulo, t.notas, tema_prioridade(t.prioridade),
            t.inicio.isoformat() if t.inicio else "", t.prazo.isoformat() if t.prazo else "",
            t.prazo_hora.strftime("%H:%M") if t.prazo_hora else "", t.repeticao or "",
            ",".join(str(m) for m in t.lembretes), " ".join(t.tags), status,
            t.criada_em.isoformat() if t.criada_em else "", t.concluida_em.isoformat() if t.concluida_em else "",
            pai.titulo if pai else ""])
    return "﻿" + saida.getvalue()


def tema_prioridade(p) -> str:
    return {0: "Nenhuma", 1: "Baixa", 2: "Média", 3: "Alta"}[int(p)]


_PRIORIDADE_TEXTO = {"nenhuma": 0, "baixa": 1, "média": 2, "media": 2, "alta": 3,
                     "none": 0, "low": 1, "medium": 2, "high": 3}


# ---------------------------------------------------------------- CSV: leitura (nosso e de outros apps)
def _detectar_delimitador(texto: str) -> str:
    primeira = next((l for l in texto.splitlines() if l.strip()), "")
    return ";" if primeira.count(";") > primeira.count(",") else ","


def _chave(nome: str) -> str:
    return re.sub(r"\s+", " ", nome.strip().lower())


def _data_hora(valor: str, nome_fuso: str, dia_inteiro: bool) -> tuple[date | None, time | None]:
    valor = (valor or "").strip()
    if not valor:
        return None, None
    try:
        dt = _parser.isoparse(valor)
    except ValueError:
        try:
            dt = _parser.parse(valor, dayfirst=True)
        except (ValueError, OverflowError):
            return None, None
    if dt.tzinfo is not None:
        dt = dt.astimezone((_tz.gettz(nome_fuso) if nome_fuso else None) or _tz.tzlocal()).replace(tzinfo=None)
    if dia_inteiro or (dt.hour == 0 and dt.minute == 0 and len(valor) <= 10):
        return dt.date(), None
    return dt.date(), dt.time().replace(second=0, microsecond=0)


def _instante_utc(valor: str) -> datetime | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        dt = _parser.isoparse(valor)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz.tzlocal())
    return dt.astimezone(timezone.utc)


def _lembretes_externo(valor: str, dia_inteiro: bool) -> list[int]:
    saida = []
    for m in re.finditer(r"TRIGGER:?\s*([+-]?P[0-9WDTHMS]+)", valor or ""):
        d = ics._duracao(m.group(1))
        if d is None:
            continue
        minutos = int(-d.total_seconds() // 60)
        if minutos < 0:
            minutos = 0                   # positivo = "no dia, a partir da meia-noite": avisa no horário padrão
        saida.append(minutos)
    return sorted(set(saida))


def _regra_externa(valor: str) -> str | None:
    valor = (valor or "").strip()
    if not valor or valor.upper().startswith("ERULE"):
        return None
    valor = valor.removeprefix("RRULE:")
    partes = [p for p in valor.split(";") if p and not p.upper().startswith(("TT_", "X-"))]
    regra = ";".join(partes)
    return regra if recorrencia.valida(regra) else None


def _projeto_por_nome(servico, nome: str, cache: dict, resultado: ResultadoImportacao, pasta: str = ""):
    nome = (nome or "").strip()
    if not nome or nome.lower() in ("inbox", "caixa de entrada", "caixa de entrada "):
        return None
    chave = nome.lower()
    if chave in cache:
        return cache[chave]
    existente = next((p for p in servico.banco.listar_projetos() + servico.banco.listar_projetos_arquivados()
                      if p.nome.lower() == chave), None)
    if existente is None:
        existente = servico.criar_projeto(nome)
        resultado.listas += 1
        if pasta:
            existente.pasta = pasta
            servico.banco.salvar_projeto(existente)
    cache[chave] = existente.id
    return existente.id


def importar_csv(servico, texto: str) -> ResultadoImportacao:
    """Lê o CSV de backup de outro app de tarefas ou o CSV exportado por este app. Cria listas que não existirem."""
    texto = texto.lstrip("﻿")
    delim = _detectar_delimitador(texto) if "Folder Name" not in texto and "List Name" not in texto else ","
    linhas = list(csv.reader(io.StringIO(texto), delimiter=delim))
    cab_i = next((i for i, l in enumerate(linhas)
                  if {"title", "título"} & {_chave(c) for c in l} and len(l) > 3), None)
    if cab_i is None:
        raise ValueError("Não encontrei a linha de títulos (Title ou Título) no arquivo.")
    cab = [_chave(c) for c in linhas[cab_i]]
    registros = [dict(zip(cab, l)) for l in linhas[cab_i + 1:] if any(c.strip() for c in l)]
    externo = "list name" in cab or "taskid" in cab
    res = ResultadoImportacao()
    cache: dict = {}
    criadas: dict[str, Tarefa] = {}          # id de origem -> tarefa criada
    pendentes = list(enumerate(registros))
    nomes_pai: dict[str, Tarefa] = {}
    # pais antes dos filhos
    pendentes.sort(key=lambda x: bool((x[1].get("parentid") or x[1].get("subtarefa de") or "").strip()))
    for i, r in pendentes:
        titulo = (r.get("title") or r.get("título") or "").strip()
        if not titulo:
            res.ignoradas += 1
            continue
        if externo:
            t = _tarefa_externa(servico, r, cache, res)
        else:
            t = _tarefa_propria(servico, r, cache, res)
        id_origem = (r.get("taskid") or "").strip() or f"linha{i}"
        pai_ref = (r.get("parentid") or "").strip()
        if pai_ref and pai_ref in criadas:
            t.pai_id = criadas[pai_ref].id
            t.projeto_id = criadas[pai_ref].projeto_id
        elif r.get("subtarefa de", "").strip():
            pai = nomes_pai.get(r["subtarefa de"].strip())
            if pai is not None:
                t.pai_id, t.projeto_id = pai.id, pai.projeto_id
        t.ordem = servico.banco.proxima_ordem()
        servico.banco.salvar_tarefa(t)
        criadas[id_origem] = t
        if t.pai_id is None:
            nomes_pai.setdefault(t.titulo, t)
            res.tarefas += 1
        else:
            res.subtarefas += 1
        if externo and (r.get("is check list") or "").strip().upper() == "Y":
            _subtarefas_do_checklist(servico, t, r.get("content") or "", res)
    return res


def _subtarefas_do_checklist(servico, pai: Tarefa, conteudo: str, res: ResultadoImportacao) -> None:
    notas = []
    for linha in conteudo.splitlines():
        marca = linha[:1]
        if marca in ("▫", "▪"):
            sub = Tarefa(titulo=linha[1:].strip() or "(sem título)", pai_id=pai.id, projeto_id=pai.projeto_id,
                         concluida_em=agora_utc() if marca == "▪" else None,
                         ordem=servico.banco.proxima_ordem())
            servico.banco.salvar_tarefa(sub)
            res.subtarefas += 1
        else:
            notas.append(linha)
    pai.notas = "\n".join(notas).strip()
    servico.banco.salvar_tarefa(pai)


def _tarefa_externa(servico, r: dict, cache: dict, res: ResultadoImportacao) -> Tarefa:
    fuso = (r.get("timezone") or "").strip()
    dia_inteiro = (r.get("is all day") or "").strip().lower() in ("true", "y", "yes", "1")
    ini_d, _ = _data_hora(r.get("start date", ""), fuso, dia_inteiro)
    prazo, hora = _data_hora(r.get("due date", ""), fuso, dia_inteiro)
    if prazo is None and ini_d is not None:
        prazo, hora, ini_d = ini_d, _data_hora(r.get("start date", ""), fuso, dia_inteiro)[1], None
    status = (r.get("status") or "0").strip()
    tags = [re.sub(r"\s+", "-", g.strip().lstrip("#").lower()) for g in (r.get("tags") or "").split(",") if g.strip()]
    prioridade = {0: 0, 1: 1, 3: 2, 5: 3}.get(int((r.get("priority") or "0").strip() or 0), 0)
    kind = (r.get("kind") or "").strip().upper()
    concluido = status in ("1", "2")
    t = Tarefa(
        titulo=r.get("title", "").strip(), notas="" if (r.get("is check list") or "").upper() == "Y"
        else (r.get("content") or "").strip(),
        projeto_id=_projeto_por_nome(servico, r.get("list name", ""), cache, res, (r.get("folder name") or "").strip()),
        prioridade=Prioridade(prioridade), prazo=prazo, prazo_hora=hora if prazo else None,
        inicio=ini_d if prazo and ini_d and ini_d < prazo else None,
        repeticao=_regra_externa(r.get("repeat", "")) if prazo else None,
        lembretes=_lembretes_externo(r.get("reminder", ""), dia_inteiro) if prazo else [],
        tags=tags, secao=(r.get("column name") or "").strip(), tipo="nota" if kind == "NOTE" else "tarefa",
        concluida_em=(_instante_utc(r.get("completed time", "")) or agora_utc()) if concluido else None,
        descartada_em=agora_utc() if status == "-1" else None)
    criada = _instante_utc(r.get("created time", ""))
    if criada:
        t.criada_em = criada
    return t


def _tarefa_propria(servico, r: dict, cache: dict, res: ResultadoImportacao) -> Tarefa:
    def dia(chave):
        v = (r.get(chave) or "").strip()
        try:
            return date.fromisoformat(v[:10]) if v else None
        except ValueError:
            return None
    hora = None
    h = (r.get("hora") or "").strip()
    if h:
        try:
            hora = time.fromisoformat(h)
        except ValueError:
            hora = None
    prazo = dia("prazo")
    status = _chave(r.get("status", ""))
    regra = (r.get("repetição") or "").strip() or None
    lembretes = [int(x) for x in re.findall(r"\d+", r.get("lembretes (minutos antes)", "") or "")]
    return Tarefa(
        titulo=(r.get("título") or r.get("title") or "").strip(), notas=(r.get("notas") or "").strip(),
        projeto_id=_projeto_por_nome(servico, r.get("lista", ""), cache, res),
        prioridade=Prioridade(_PRIORIDADE_TEXTO.get(_chave(r.get("prioridade", "")), 0)),
        prazo=prazo, prazo_hora=hora if prazo else None, inicio=dia("início") if prazo else None,
        repeticao=regra if regra and recorrencia.valida(regra) and prazo else None,
        lembretes=lembretes if prazo else [],
        tags=[g.strip().lstrip("#").lower() for g in (r.get("etiquetas") or "").split() if g.strip("#")],
        concluida_em=agora_utc() if status.startswith("conclu") else None,
        descartada_em=agora_utc() if status.startswith("não") or status.startswith("nao") else None)


# ---------------------------------------------------------------- .ics
def exportar_ics(servico, incluir_finalizadas: bool = False, nome: str = "Tarefas") -> str:
    tarefas = [t for t in servico.banco.consultar("apagada_em IS NULL AND prazo IS NOT NULL")
               if incluir_finalizadas or not t.finalizada]
    return ics.escrever_ics(tarefas, nome)


def importar_ics(servico, texto: str, projeto_id: int | None = None, tz_destino=None) -> ResultadoImportacao:
    """Transforma cada evento (ou tarefa) do arquivo .ics em uma tarefa com data."""
    res = ResultadoImportacao()
    for ev in ics.ler_ics(texto, tz_destino):
        ini, fim = ev.dias()
        hora = ev.inicio.time() if isinstance(ev.inicio, datetime) else None
        if ev.tipo == "VTODO" and ev.fim is None and isinstance(ev.inicio, datetime):
            fim = ev.inicio.date()
        dur = 0
        if hora is not None and isinstance(ev.fim, datetime) and ev.fim.date() == ev.inicio.date():
            dur = max(15, int((ev.fim - ev.inicio).total_seconds() // 60))
        regra = ev.regra if ev.regra and recorrencia.valida(ev.regra) else None
        notas = ev.descricao + (f"\n\nLocal: {ev.local}" if ev.local else "")
        servico.banco.salvar_tarefa(Tarefa(
            titulo=ev.titulo.strip() or "(sem título)", notas=notas.strip(), projeto_id=projeto_id,
            prioridade=Prioridade(ev.prioridade), prazo=fim, inicio=ini if ini < fim else None,
            prazo_hora=hora,
            duracao_min=dur, repeticao=regra, lembretes=list(ev.lembretes),
            concluida_em=agora_utc() if ev.concluido else None, ordem=servico.banco.proxima_ordem()))
        res.tarefas += 1
    if res.tarefas == 0:
        res.avisos.append("Nenhum evento encontrado no arquivo.")
    return res
