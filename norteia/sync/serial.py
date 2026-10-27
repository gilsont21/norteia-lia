"""Converte tarefas, listas e filtros em dicionários JSON e de volta.

Entre aparelhos, tudo se liga por `uuid` (os ids numéricos são só locais). A regra de
conflito é "vale a edição mais recente" (`atualizada_em`); empate não muda nada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

from ..core.db import Banco
from ..core.models import Filtro, Prioridade, Projeto, Registro, Tarefa


def _iso(v) -> str | None:
    return v.isoformat() if v else None


def _dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


# ---------- para dicionário ----------
def projeto_para_dict(p: Projeto) -> dict:
    return {"uuid": p.uuid, "nome": p.nome, "cor": p.cor, "ordem": p.ordem,
            "arquivado": p.arquivado, "atualizada_em": _iso(p.atualizada_em),
            "apagado_em": _iso(p.apagado_em), "pasta": p.pasta, "emoji": p.emoji,
            "visao": p.visao, "tipo": p.tipo, "inteligente": p.inteligente}


def registro_para_dict(r: Registro) -> dict:
    return {"uuid": r.uuid, "tipo": r.tipo, "dados": r.dados,
            "atualizada_em": _iso(r.atualizada_em), "apagado_em": _iso(r.apagado_em)}


def filtro_para_dict(f: Filtro) -> dict:
    return {"uuid": f.uuid, "nome": f.nome, "criterios": f.criterios,
            "atualizada_em": _iso(f.atualizada_em), "apagado_em": _iso(f.apagado_em)}


def tarefa_para_dict(banco: Banco, t: Tarefa) -> dict:
    projeto = banco.obter_projeto(t.projeto_id) if t.projeto_id else None
    pai = banco.obter_tarefa(t.pai_id) if t.pai_id else None
    return {
        "uuid": t.uuid, "titulo": t.titulo, "notas": t.notas,
        "projeto": projeto.uuid if projeto else None,
        "pai": pai.uuid if pai else None,
        "prioridade": int(t.prioridade), "prazo": _iso(t.prazo), "prazo_hora": _iso(t.prazo_hora),
        "repeticao": t.repeticao, "lembretes": list(t.lembretes),
        "concluida_em": _iso(t.concluida_em), "criada_em": _iso(t.criada_em),
        "atualizada_em": _iso(t.atualizada_em), "apagada_em": _iso(t.apagada_em),
        "ordem": t.ordem, "tags": list(t.tags),
        "fixada": t.fixada, "descartada_em": _iso(t.descartada_em), "insistir_min": t.insistir_min,
        "inicio": _iso(t.inicio), "duracao_min": t.duracao_min, "secao": t.secao, "tipo": t.tipo,
        "tag_cores": {g.nome: g.cor for g in (banco.obter_tag(n) for n in t.tags) if g and g.cor != "#8a8f98"},
    }


def empacotar(banco: Banco, desde: datetime | None = None) -> dict:
    """Tudo o que mudou neste banco depois de `desde` (ou tudo, se for None)."""
    return {
        "projetos": [projeto_para_dict(p) for p in banco.projetos_alterados_desde(desde)],
        "filtros": [filtro_para_dict(f) for f in banco.filtros_alterados_desde(desde)],
        "tarefas": [tarefa_para_dict(banco, t) for t in banco.alteradas_desde(desde)],
        "registros": [registro_para_dict(r) for r in banco.registros_alterados_desde(desde)],
    }


def pacote_de(banco: Banco, entidades: list[tuple[str, str]]) -> dict:
    """Estado atual das entidades [(tipo, uuid)] — usado pelo servidor na resposta."""
    pacote = {"projetos": [], "filtros": [], "tarefas": [], "registros": []}
    for tipo, uuid in entidades:
        if tipo == "projeto" and (p := banco.obter_projeto_por_uuid(uuid)):
            pacote["projetos"].append(projeto_para_dict(p))
        elif tipo == "filtro" and (f := banco.obter_filtro_por_uuid(uuid)):
            pacote["filtros"].append(filtro_para_dict(f))
        elif tipo == "tarefa" and (t := banco.obter_tarefa_por_uuid(uuid)):
            pacote["tarefas"].append(tarefa_para_dict(banco, t))
        elif tipo == "registro" and (r := banco.obter_registro_por_uuid(uuid)):
            pacote["registros"].append(registro_para_dict(r))
    return pacote


# ---------- aplicar ----------
@dataclass
class Aplicado:
    aceitos: list[tuple[str, str]] = field(default_factory=list)   # [(tipo, uuid)] que mudaram o banco
    pendentes: list[str] = field(default_factory=list)             # uuids que dependem de algo ausente


def _mais_novo(novo: str | None, atual: datetime | None) -> bool:
    return atual is None or (novo is not None and _dt(novo) > atual)


def aplicar(banco: Banco, pacote: dict) -> Aplicado:
    res = Aplicado()
    for d in pacote.get("projetos", []):
        antigo = banco.obter_projeto_por_uuid(d["uuid"])
        if antigo is not None and not _mais_novo(d["atualizada_em"], antigo.atualizada_em):
            continue
        banco.salvar_projeto(Projeto(
            nome=d["nome"], cor=d["cor"], ordem=d["ordem"], arquivado=d["arquivado"],
            uuid=d["uuid"], atualizada_em=_dt(d["atualizada_em"]), apagado_em=_dt(d["apagado_em"]),
            pasta=d.get("pasta", "") or "", emoji=d.get("emoji", "") or "", visao=d.get("visao", "lista") or "lista",
            tipo=d.get("tipo", "tarefas") or "tarefas", inteligente=d.get("inteligente", "todas") or "todas",
            id=antigo.id if antigo else None), preservar_tempo=True)
        res.aceitos.append(("projeto", d["uuid"]))

    for d in pacote.get("filtros", []):
        antigo = banco.obter_filtro_por_uuid(d["uuid"])
        if antigo is not None and not _mais_novo(d["atualizada_em"], antigo.atualizada_em):
            continue
        banco.salvar_filtro(Filtro(
            nome=d["nome"], criterios=d["criterios"], uuid=d["uuid"],
            atualizada_em=_dt(d["atualizada_em"]), apagado_em=_dt(d["apagado_em"]),
            id=antigo.id if antigo else None), preservar_tempo=True)
        res.aceitos.append(("filtro", d["uuid"]))

    # tarefas principais antes das subtarefas
    for d in sorted(pacote.get("tarefas", []), key=lambda x: x["pai"] is not None):
        antigo = banco.obter_tarefa_por_uuid(d["uuid"])
        if antigo is not None and not _mais_novo(d["atualizada_em"], antigo.atualizada_em):
            continue
        projeto_id = None
        if d["projeto"]:
            proj = banco.obter_projeto_por_uuid(d["projeto"])
            projeto_id = proj.id if proj else None
        pai_id = None
        if d["pai"]:
            pai = banco.obter_tarefa_por_uuid(d["pai"])
            if pai is None:
                res.pendentes.append(d["uuid"])
                continue
            pai_id = pai.id
        banco.salvar_tarefa(Tarefa(
            titulo=d["titulo"], notas=d["notas"], projeto_id=projeto_id, pai_id=pai_id,
            prioridade=Prioridade(d["prioridade"]),
            prazo=date.fromisoformat(d["prazo"]) if d["prazo"] else None,
            prazo_hora=time.fromisoformat(d["prazo_hora"]) if d["prazo_hora"] else None,
            repeticao=d["repeticao"], lembretes=list(d["lembretes"]),
            concluida_em=_dt(d["concluida_em"]), criada_em=_dt(d["criada_em"]),
            atualizada_em=_dt(d["atualizada_em"]), apagada_em=_dt(d["apagada_em"]),
            ordem=d["ordem"], tags=list(d["tags"]), uuid=d["uuid"],
            fixada=bool(d.get("fixada", False)), descartada_em=_dt(d.get("descartada_em")),
            insistir_min=int(d.get("insistir_min", 0) or 0),
            inicio=date.fromisoformat(d["inicio"]) if d.get("inicio") else None,
            duracao_min=int(d.get("duracao_min", 0) or 0), secao=d.get("secao", "") or "",
            tipo=d.get("tipo", "tarefa") or "tarefa",
            id=antigo.id if antigo else None), preservar_tempo=True)
        for nome, cor in (d.get("tag_cores") or {}).items():
            tag = banco.obter_tag(nome)
            if tag is not None and tag.cor == "#8a8f98" and cor != tag.cor:
                tag.cor = cor
                banco.salvar_tag(tag)
        res.aceitos.append(("tarefa", d["uuid"]))

    for d in pacote.get("registros", []):
        antigo = banco.obter_registro_por_uuid(d["uuid"])
        if antigo is not None and not _mais_novo(d["atualizada_em"], antigo.atualizada_em):
            continue
        banco.salvar_registro(Registro(
            tipo=d["tipo"], dados=d["dados"], uuid=d["uuid"], atualizada_em=_dt(d["atualizada_em"]),
            apagado_em=_dt(d["apagado_em"]), id=antigo.id if antigo else None), preservar_tempo=True)
        res.aceitos.append(("registro", d["uuid"]))
    return res
