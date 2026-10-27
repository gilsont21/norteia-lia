"""Armazenamento SQLite. Um arquivo local, sem servidor.

Os ids numéricos são só locais (rápidos para ligar tabelas). O que identifica uma
entidade entre aparelhos é o `uuid`.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time
from pathlib import Path

from .models import Filtro, Prioridade, Projeto, Registro, Tag, Tarefa, agora_utc, novo_uuid

VERSAO_ESQUEMA = 6

ESQUEMA = """
CREATE TABLE IF NOT EXISTS projeto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL,
    nome TEXT NOT NULL,
    cor TEXT NOT NULL DEFAULT '#c39a3f',
    ordem INTEGER NOT NULL DEFAULT 0,
    arquivado INTEGER NOT NULL DEFAULT 0,
    atualizada_em TEXT,
    apagado_em TEXT,
    pasta TEXT NOT NULL DEFAULT '',
    emoji TEXT NOT NULL DEFAULT '',
    visao TEXT NOT NULL DEFAULT 'lista',
    tipo TEXT NOT NULL DEFAULT 'tarefas',
    inteligente TEXT NOT NULL DEFAULT 'todas'
);
CREATE TABLE IF NOT EXISTS tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL,
    nome TEXT NOT NULL UNIQUE,
    cor TEXT NOT NULL DEFAULT '#8a8f98',
    atualizada_em TEXT
);
CREATE TABLE IF NOT EXISTS tarefa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL,
    titulo TEXT NOT NULL,
    notas TEXT NOT NULL DEFAULT '',
    projeto_id INTEGER REFERENCES projeto(id) ON DELETE SET NULL,
    pai_id INTEGER REFERENCES tarefa(id) ON DELETE CASCADE,
    prioridade INTEGER NOT NULL DEFAULT 0,
    prazo TEXT,
    prazo_hora TEXT,
    repeticao TEXT,
    lembretes TEXT NOT NULL DEFAULT '[]',
    concluida_em TEXT,
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL,
    apagada_em TEXT,
    ordem INTEGER NOT NULL DEFAULT 0,
    fixada INTEGER NOT NULL DEFAULT 0,
    descartada_em TEXT,
    insistir_min INTEGER NOT NULL DEFAULT 0,
    inicio TEXT,
    duracao_min INTEGER NOT NULL DEFAULT 0,
    secao TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL DEFAULT 'tarefa'
);
CREATE TABLE IF NOT EXISTS tarefa_tag (
    tarefa_id INTEGER NOT NULL REFERENCES tarefa(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (tarefa_id, tag_id)
);
CREATE TABLE IF NOT EXISTS notificacao (
    tarefa_id INTEGER NOT NULL REFERENCES tarefa(id) ON DELETE CASCADE,
    instante TEXT NOT NULL,
    PRIMARY KEY (tarefa_id, instante)
);
CREATE TABLE IF NOT EXISTS soneca (
    tarefa_id INTEGER PRIMARY KEY REFERENCES tarefa(id) ON DELETE CASCADE,
    ate TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS filtro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL,
    nome TEXT NOT NULL,
    criterios TEXT NOT NULL DEFAULT '{}',
    atualizada_em TEXT NOT NULL,
    apagado_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_filtro_uuid ON filtro(uuid);
CREATE TABLE IF NOT EXISTS registro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    uuid TEXT NOT NULL,
    dados TEXT NOT NULL DEFAULT '{}',
    atualizada_em TEXT NOT NULL,
    apagado_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_registro_uuid ON registro(uuid);
CREATE INDEX IF NOT EXISTS ix_registro_tipo ON registro(tipo);
-- as tabelas abaixo valem só neste aparelho (não sincronizam)
CREATE TABLE IF NOT EXISTS secao_ordem (
    projeto_id INTEGER NOT NULL,           -- 0 = Caixa de entrada
    nome TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (projeto_id, nome)
);
CREATE TABLE IF NOT EXISTS assinatura (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    url TEXT NOT NULL,
    cor TEXT NOT NULL DEFAULT '#4dd0b1',
    ultima_sync TEXT,
    erro TEXT NOT NULL DEFAULT '',
    origem TEXT NOT NULL DEFAULT 'ics',      -- 'ics' (link) ou 'google'
    ref TEXT NOT NULL DEFAULT '',            -- id do calendário no Google
    sync_token TEXT NOT NULL DEFAULT '',
    ativa INTEGER NOT NULL DEFAULT 1,
    completa_em TEXT
);
CREATE TABLE IF NOT EXISTS evento_externo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assinatura_id INTEGER NOT NULL REFERENCES assinatura(id) ON DELETE CASCADE,
    uid TEXT NOT NULL,
    titulo TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT,
    dia_inteiro INTEGER NOT NULL DEFAULT 0,
    regra TEXT,
    local TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_evento_assinatura ON evento_externo(assinatura_id);
-- Google Calendar: ligação entre cada tarefa e o evento que foi criado para ela (só neste aparelho)
CREATE TABLE IF NOT EXISTS ligacao_google (
    tarefa_uuid TEXT PRIMARY KEY,
    evento_id TEXT NOT NULL DEFAULT '',      -- vazio = o evento foi apagado no Google
    corpo_hash TEXT NOT NULL DEFAULT '',
    etag TEXT NOT NULL DEFAULT ''
);
-- conversas com o assistente de IA (só neste aparelho, não sincronizam)
CREATE TABLE IF NOT EXISTS conversa_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL DEFAULT '',
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL,
    dados TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS anexo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL,
    tarefa_id INTEGER NOT NULL REFERENCES tarefa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    caminho TEXT NOT NULL,
    tamanho INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alteracao (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    uuid TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tarefa_projeto ON tarefa(projeto_id);
CREATE INDEX IF NOT EXISTS ix_tarefa_prazo ON tarefa(prazo);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tarefa_uuid ON tarefa(uuid);
CREATE UNIQUE INDEX IF NOT EXISTS ix_projeto_uuid ON projeto(uuid);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tag_uuid ON tag(uuid);
"""

# colunas que bancos da versão 1 não tinham
_NOVAS_COLUNAS = {
    "projeto": [("uuid", "TEXT"), ("atualizada_em", "TEXT"), ("apagado_em", "TEXT"),
                ("pasta", "TEXT NOT NULL DEFAULT ''"), ("emoji", "TEXT NOT NULL DEFAULT ''"),
                ("visao", "TEXT NOT NULL DEFAULT 'lista'"), ("tipo", "TEXT NOT NULL DEFAULT 'tarefas'"),
                ("inteligente", "TEXT NOT NULL DEFAULT 'todas'")],
    "tag": [("uuid", "TEXT"), ("atualizada_em", "TEXT")],
    "assinatura": [("origem", "TEXT NOT NULL DEFAULT 'ics'"), ("ref", "TEXT NOT NULL DEFAULT ''"),
                   ("sync_token", "TEXT NOT NULL DEFAULT ''"), ("ativa", "INTEGER NOT NULL DEFAULT 1"),
                   ("completa_em", "TEXT")],
    "evento_externo": [("link", "TEXT NOT NULL DEFAULT ''")],
    "tarefa": [("uuid", "TEXT"), ("prazo_hora", "TEXT"), ("repeticao", "TEXT"),
               ("lembretes", "TEXT NOT NULL DEFAULT '[]'"), ("fixada", "INTEGER NOT NULL DEFAULT 0"),
               ("descartada_em", "TEXT"), ("insistir_min", "INTEGER NOT NULL DEFAULT 0"),
               ("inicio", "TEXT"), ("duracao_min", "INTEGER NOT NULL DEFAULT 0"),
               ("secao", "TEXT NOT NULL DEFAULT ''"), ("tipo", "TEXT NOT NULL DEFAULT 'tarefa'")],
}


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


def _d(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def _h(valor: str | None) -> time | None:
    return time.fromisoformat(valor) if valor else None


def _iso(valor) -> str | None:
    return valor.isoformat() if valor else None


class Banco:
    def __init__(self, caminho: str | Path = ":memory:", varias_threads: bool = False):
        # varias_threads=True é para o servidor, que protege o acesso com um lock próprio
        self.caminho = str(caminho)
        self.con = sqlite3.connect(self.caminho, check_same_thread=not varias_threads, timeout=15)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self._migrar()
        self.con.executescript(ESQUEMA)
        self.con.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
        self.con.commit()

    def fechar(self) -> None:
        self.con.close()

    # ---- migração de bancos antigos ----
    def _migrar(self) -> None:
        tabelas = {l["name"] for l in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "tarefa" not in tabelas:
            return  # banco novo, o esquema completo é criado em seguida
        for tabela, colunas in _NOVAS_COLUNAS.items():
            existentes = {l["name"] for l in self.con.execute(f"PRAGMA table_info({tabela})")}
            if not existentes:
                continue  # tabela ainda não existe, o esquema cria completa
            for nome, tipo in colunas:
                if nome not in existentes:
                    self.con.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
        agora = agora_utc().isoformat()
        for tabela in ("projeto", "tag", "tarefa"):
            for l in self.con.execute(f"SELECT id FROM {tabela} WHERE uuid IS NULL").fetchall():
                self.con.execute(f"UPDATE {tabela} SET uuid=? WHERE id=?", (novo_uuid(), l["id"]))
        for tabela in ("projeto", "tag"):
            self.con.execute(f"UPDATE {tabela} SET atualizada_em=? WHERE atualizada_em IS NULL", (agora,))
        self.con.commit()

    # ---- meta (identidade do aparelho etc.) ----
    def meta(self, chave: str, padrao: str | None = None) -> str | None:
        l = self.con.execute("SELECT valor FROM meta WHERE chave=?", (chave,)).fetchone()
        return l["valor"] if l else padrao

    def definir_meta(self, chave: str, valor: str) -> None:
        self.con.execute(
            "INSERT INTO meta(chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, valor),
        )
        self.con.commit()

    def id_dispositivo(self) -> str:
        atual = self.meta("dispositivo")
        if atual is None:
            atual = novo_uuid()
            self.definir_meta("dispositivo", atual)
        return atual

    # ---- projetos ----
    def _projeto(self, l: sqlite3.Row) -> Projeto:
        return Projeto(
            nome=l["nome"], cor=l["cor"], ordem=l["ordem"], arquivado=bool(l["arquivado"]),
            uuid=l["uuid"], atualizada_em=_dt(l["atualizada_em"]) or agora_utc(),
            apagado_em=_dt(l["apagado_em"]), id=l["id"], pasta=l["pasta"] or "",
            emoji=l["emoji"] or "", visao=l["visao"] or "lista", tipo=l["tipo"] or "tarefas",
            inteligente=l["inteligente"] or "todas",
        )

    def salvar_projeto(self, p: Projeto, preservar_tempo: bool = False) -> Projeto:
        if not preservar_tempo:
            p.atualizada_em = agora_utc()
        if p.id is None:
            cur = self.con.execute(
                "INSERT INTO projeto(uuid, nome, cor, ordem, arquivado, atualizada_em, apagado_em, pasta,"
                " emoji, visao, tipo, inteligente) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.uuid, p.nome, p.cor, p.ordem, int(p.arquivado), _iso(p.atualizada_em), _iso(p.apagado_em),
                 p.pasta, p.emoji, p.visao, p.tipo, p.inteligente),
            )
            p.id = cur.lastrowid
        else:
            self.con.execute(
                "UPDATE projeto SET nome=?, cor=?, ordem=?, arquivado=?, atualizada_em=?, apagado_em=?, pasta=?,"
                " emoji=?, visao=?, tipo=?, inteligente=? WHERE id=?",
                (p.nome, p.cor, p.ordem, int(p.arquivado), _iso(p.atualizada_em), _iso(p.apagado_em), p.pasta,
                 p.emoji, p.visao, p.tipo, p.inteligente, p.id),
            )
        self.con.commit()
        return p

    def listar_projetos(self) -> list[Projeto]:
        linhas = self.con.execute(
            "SELECT * FROM projeto WHERE arquivado=0 AND apagado_em IS NULL ORDER BY ordem, id"
        ).fetchall()
        return [self._projeto(l) for l in linhas]

    def listar_projetos_arquivados(self) -> list[Projeto]:
        linhas = self.con.execute(
            "SELECT * FROM projeto WHERE arquivado=1 AND apagado_em IS NULL ORDER BY ordem, id"
        ).fetchall()
        return [self._projeto(l) for l in linhas]

    # ---- filtros salvos ----
    def _filtro(self, l: sqlite3.Row) -> Filtro:
        return Filtro(l["nome"], json.loads(l["criterios"] or "{}"), l["uuid"],
                      _dt(l["atualizada_em"]) or agora_utc(), _dt(l["apagado_em"]), l["id"])

    def salvar_filtro(self, f: Filtro, preservar_tempo: bool = False) -> Filtro:
        if not preservar_tempo:
            f.atualizada_em = agora_utc()
        dados = (f.nome, json.dumps(f.criterios, ensure_ascii=False), _iso(f.atualizada_em), _iso(f.apagado_em))
        if f.id is None:
            cur = self.con.execute(
                "INSERT INTO filtro(uuid, nome, criterios, atualizada_em, apagado_em) VALUES (?,?,?,?,?)",
                (f.uuid, *dados))
            f.id = cur.lastrowid
        else:
            self.con.execute(
                "UPDATE filtro SET nome=?, criterios=?, atualizada_em=?, apagado_em=? WHERE id=?", (*dados, f.id))
        self.con.commit()
        return f

    def listar_filtros(self) -> list[Filtro]:
        return [self._filtro(l) for l in
                self.con.execute("SELECT * FROM filtro WHERE apagado_em IS NULL ORDER BY nome COLLATE NOCASE, id")]

    def obter_filtro(self, filtro_id: int) -> Filtro | None:
        l = self.con.execute("SELECT * FROM filtro WHERE id=? AND apagado_em IS NULL", (filtro_id,)).fetchone()
        return self._filtro(l) if l else None

    def obter_filtro_por_uuid(self, uuid: str) -> Filtro | None:
        l = self.con.execute("SELECT * FROM filtro WHERE uuid=?", (uuid,)).fetchone()
        return self._filtro(l) if l else None

    def filtros_alterados_desde(self, instante: datetime | None) -> list[Filtro]:
        sql, args = "SELECT * FROM filtro", ()
        if instante is not None:
            sql, args = sql + " WHERE atualizada_em > ?", (instante.isoformat(),)
        return [self._filtro(l) for l in self.con.execute(sql, args)]

    def obter_projeto(self, projeto_id: int) -> Projeto | None:
        l = self.con.execute("SELECT * FROM projeto WHERE id=?", (projeto_id,)).fetchone()
        return self._projeto(l) if l else None

    def obter_projeto_por_uuid(self, uuid: str) -> Projeto | None:
        l = self.con.execute("SELECT * FROM projeto WHERE uuid=?", (uuid,)).fetchone()
        return self._projeto(l) if l else None

    def projetos_alterados_desde(self, instante: datetime | None) -> list[Projeto]:
        sql, args = "SELECT * FROM projeto", ()
        if instante is not None:
            sql, args = sql + " WHERE atualizada_em > ?", (instante.isoformat(),)
        return [self._projeto(l) for l in self.con.execute(sql, args)]

    # ---- registro de alterações (usado pelo servidor de sincronização) ----
    def registrar_alteracao(self, tipo: str, uuid: str) -> int:
        cur = self.con.execute("INSERT INTO alteracao(tipo, uuid) VALUES (?,?)", (tipo, uuid))
        self.con.commit()
        return cur.lastrowid

    def alteracoes_depois_de(self, seq: int) -> list[tuple[int, str, str]]:
        """[(seq, tipo, uuid)] sem repetir a mesma entidade (vale a mais recente)."""
        linhas = self.con.execute(
            "SELECT MAX(seq) AS seq, tipo, uuid FROM alteracao WHERE seq > ? GROUP BY tipo, uuid ORDER BY seq",
            (seq,)).fetchall()
        return [(l["seq"], l["tipo"], l["uuid"]) for l in linhas]

    def ultima_alteracao(self) -> int:
        return self.con.execute("SELECT COALESCE(MAX(seq), 0) FROM alteracao").fetchone()[0]

    def proxima_ordem(self) -> int:
        return self.con.execute("SELECT COALESCE(MAX(ordem), 0) + 1 FROM tarefa").fetchone()[0]

    # ---- tags ----
    def obter_ou_criar_tag(self, nome: str) -> Tag:
        nome = nome.strip().lstrip("#").lower()
        linha = self.con.execute("SELECT * FROM tag WHERE nome=?", (nome,)).fetchone()
        if linha:
            return Tag(linha["nome"], linha["cor"], linha["uuid"],
                       _dt(linha["atualizada_em"]) or agora_utc(), linha["id"])
        tag = Tag(nome)
        cur = self.con.execute(
            "INSERT INTO tag(uuid, nome, cor, atualizada_em) VALUES (?,?,?,?)",
            (tag.uuid, tag.nome, tag.cor, _iso(tag.atualizada_em)),
        )
        self.con.commit()
        tag.id = cur.lastrowid
        return tag

    def obter_tag(self, nome: str) -> Tag | None:
        nome = nome.strip().lstrip("#").lower()
        l = self.con.execute("SELECT * FROM tag WHERE nome=?", (nome,)).fetchone()
        return Tag(l["nome"], l["cor"], l["uuid"], _dt(l["atualizada_em"]) or agora_utc(), l["id"]) if l else None

    def salvar_tag(self, tag: Tag) -> Tag:
        tag.atualizada_em = agora_utc()
        self.con.execute("UPDATE tag SET nome=?, cor=?, atualizada_em=? WHERE id=?",
                         (tag.nome, tag.cor, _iso(tag.atualizada_em), tag.id))
        self.con.commit()
        return tag

    def excluir_tag(self, tag_id: int) -> None:
        self.con.execute("DELETE FROM tag WHERE id=?", (tag_id,))
        self.con.commit()

    def tarefas_da_tag(self, nome: str) -> list[Tarefa]:
        return self.consultar(
            "id IN (SELECT tt.tarefa_id FROM tarefa_tag tt JOIN tag g ON g.id = tt.tag_id WHERE g.nome = ?)",
            (nome,))

    def listar_tags(self) -> list[Tag]:
        return [
            Tag(l["nome"], l["cor"], l["uuid"], _dt(l["atualizada_em"]) or agora_utc(), l["id"])
            for l in self.con.execute("SELECT * FROM tag ORDER BY nome")
        ]

    # ---- tarefas ----
    def _tags_da_tarefa(self, tarefa_id: int) -> list[str]:
        return [
            l["nome"]
            for l in self.con.execute(
                "SELECT t.nome FROM tag t JOIN tarefa_tag tt ON tt.tag_id=t.id "
                "WHERE tt.tarefa_id=? ORDER BY t.nome",
                (tarefa_id,),
            )
        ]

    def _montar(self, l: sqlite3.Row) -> Tarefa:
        return Tarefa(
            titulo=l["titulo"],
            notas=l["notas"],
            projeto_id=l["projeto_id"],
            pai_id=l["pai_id"],
            prioridade=Prioridade(l["prioridade"]),
            prazo=_d(l["prazo"]),
            prazo_hora=_h(l["prazo_hora"]),
            repeticao=l["repeticao"],
            lembretes=json.loads(l["lembretes"] or "[]"),
            concluida_em=_dt(l["concluida_em"]),
            criada_em=_dt(l["criada_em"]),
            atualizada_em=_dt(l["atualizada_em"]),
            apagada_em=_dt(l["apagada_em"]),
            ordem=l["ordem"],
            tags=self._tags_da_tarefa(l["id"]),
            uuid=l["uuid"],
            id=l["id"],
            fixada=bool(l["fixada"]),
            descartada_em=_dt(l["descartada_em"]),
            insistir_min=l["insistir_min"] or 0,
            inicio=_d(l["inicio"]),
            duracao_min=l["duracao_min"] or 0,
            secao=l["secao"] or "",
            tipo=l["tipo"] or "tarefa",
        )

    def salvar_tarefa(self, t: Tarefa, preservar_tempo: bool = False) -> Tarefa:
        """`preservar_tempo=True` é para dados vindos de outro aparelho: mantém o horário original."""
        if not preservar_tempo:
            t.atualizada_em = agora_utc()
        campos = (
            t.titulo, t.notas, t.projeto_id, t.pai_id, int(t.prioridade),
            _iso(t.prazo), _iso(t.prazo_hora), t.repeticao, json.dumps(sorted(t.lembretes)),
            _iso(t.concluida_em), _iso(t.criada_em), _iso(t.atualizada_em),
            _iso(t.apagada_em), t.ordem, int(t.fixada), _iso(t.descartada_em), int(t.insistir_min),
            _iso(t.inicio), int(t.duracao_min), t.secao, t.tipo,
        )
        if t.id is None:
            cur = self.con.execute(
                "INSERT INTO tarefa(uuid, titulo, notas, projeto_id, pai_id, prioridade, prazo,"
                " prazo_hora, repeticao, lembretes, concluida_em, criada_em, atualizada_em,"
                " apagada_em, ordem, fixada, descartada_em, insistir_min, inicio, duracao_min, secao, tipo)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (t.uuid, *campos),
            )
            t.id = cur.lastrowid
        else:
            self.con.execute(
                "UPDATE tarefa SET titulo=?, notas=?, projeto_id=?, pai_id=?, prioridade=?,"
                " prazo=?, prazo_hora=?, repeticao=?, lembretes=?, concluida_em=?, criada_em=?,"
                " atualizada_em=?, apagada_em=?, ordem=?, fixada=?, descartada_em=?, insistir_min=?,"
                " inicio=?, duracao_min=?, secao=?, tipo=?"
                " WHERE id=?",
                (*campos, t.id),
            )
        self.con.execute("DELETE FROM tarefa_tag WHERE tarefa_id=?", (t.id,))
        for nome in t.tags:
            tag = self.obter_ou_criar_tag(nome)
            self.con.execute(
                "INSERT OR IGNORE INTO tarefa_tag(tarefa_id, tag_id) VALUES (?,?)",
                (t.id, tag.id),
            )
        self.con.commit()
        return t

    def obter_tarefa(self, tarefa_id: int) -> Tarefa | None:
        l = self.con.execute("SELECT * FROM tarefa WHERE id=?", (tarefa_id,)).fetchone()
        return self._montar(l) if l else None

    def obter_tarefa_por_uuid(self, uuid: str) -> Tarefa | None:
        l = self.con.execute("SELECT * FROM tarefa WHERE uuid=?", (uuid,)).fetchone()
        return self._montar(l) if l else None

    def consultar(self, where: str = "1=1", params: tuple = (), ordem: str = "ordem, id") -> list[Tarefa]:
        linhas = self.con.execute(
            f"SELECT * FROM tarefa WHERE {where} ORDER BY {ordem}", params
        ).fetchall()
        return [self._montar(l) for l in linhas]

    def alteradas_desde(self, instante: datetime | None) -> list[Tarefa]:
        """Tarefas mudadas depois do instante (UTC). É a base da sincronização."""
        if instante is None:
            return self.consultar(ordem="atualizada_em")
        return self.consultar("atualizada_em > ?", (instante.isoformat(),), "atualizada_em")

    def excluir_definitivamente(self, tarefa_id: int) -> None:
        self.con.execute("DELETE FROM tarefa WHERE id=?", (tarefa_id,))
        self.con.commit()

    # ---- soneca (adiar lembrete): vale só neste aparelho ----
    def definir_soneca(self, tarefa_id: int, ate: datetime) -> None:
        self.con.execute(
            "INSERT INTO soneca(tarefa_id, ate) VALUES (?,?) ON CONFLICT(tarefa_id) DO UPDATE SET ate=excluded.ate",
            (tarefa_id, ate.isoformat()))
        self.con.commit()

    def sonecas(self) -> list[tuple[int, datetime]]:
        return [(l["tarefa_id"], datetime.fromisoformat(l["ate"]))
                for l in self.con.execute("SELECT tarefa_id, ate FROM soneca ORDER BY ate")]

    def limpar_soneca(self, tarefa_id: int) -> None:
        self.con.execute("DELETE FROM soneca WHERE tarefa_id=?", (tarefa_id,))
        self.con.commit()

    # ---- notificações já enviadas ----
    def ja_notificada(self, tarefa_id: int, instante: datetime) -> bool:
        return self.con.execute(
            "SELECT 1 FROM notificacao WHERE tarefa_id=? AND instante=?",
            (tarefa_id, instante.isoformat()),
        ).fetchone() is not None

    def marcar_notificada(self, tarefa_id: int, instante: datetime) -> None:
        self.con.execute(
            "INSERT OR IGNORE INTO notificacao(tarefa_id, instante) VALUES (?,?)",
            (tarefa_id, instante.isoformat()),
        )
        self.con.commit()

    # ---- registros genéricos (hábitos, foco, comentários, modelos, contagens) ----
    @staticmethod
    def _registro(l: sqlite3.Row) -> Registro:
        return Registro(l["tipo"], json.loads(l["dados"] or "{}"), l["uuid"],
                        _dt(l["atualizada_em"]) or agora_utc(), _dt(l["apagado_em"]), l["id"])

    def salvar_registro(self, r: Registro, preservar_tempo: bool = False) -> Registro:
        if not preservar_tempo:
            r.atualizada_em = agora_utc()
        dados = json.dumps(r.dados, ensure_ascii=False)
        if r.id is None:
            cur = self.con.execute(
                "INSERT INTO registro(tipo, uuid, dados, atualizada_em, apagado_em) VALUES (?,?,?,?,?)",
                (r.tipo, r.uuid, dados, _iso(r.atualizada_em), _iso(r.apagado_em)))
            r.id = cur.lastrowid
        else:
            self.con.execute(
                "UPDATE registro SET tipo=?, dados=?, atualizada_em=?, apagado_em=? WHERE id=?",
                (r.tipo, dados, _iso(r.atualizada_em), _iso(r.apagado_em), r.id))
        self.con.commit()
        return r

    def obter_registro_por_uuid(self, uuid: str) -> Registro | None:
        l = self.con.execute("SELECT * FROM registro WHERE uuid=?", (uuid,)).fetchone()
        return self._registro(l) if l else None

    def listar_registros(self, tipo: str, incluir_apagados: bool = False) -> list[Registro]:
        sql = "SELECT * FROM registro WHERE tipo=?" + ("" if incluir_apagados else " AND apagado_em IS NULL")
        return [self._registro(l) for l in self.con.execute(sql + " ORDER BY id", (tipo,))]

    def registros_alterados_desde(self, instante: datetime | None) -> list[Registro]:
        sql, args = "SELECT * FROM registro", ()
        if instante is not None:
            sql, args = sql + " WHERE atualizada_em > ?", (instante.isoformat(),)
        return [self._registro(l) for l in self.con.execute(sql, args)]

    # ---- seções do Kanban (ordem das colunas, só neste aparelho) ----
    def secoes_da_lista(self, projeto_id: int | None) -> list[str]:
        """Nomes das colunas do Kanban de uma lista, na ordem escolhida; as que só existem em tarefas vêm depois."""
        chave = projeto_id if projeto_id is not None else 0
        ordenadas = [l["nome"] for l in self.con.execute(
            "SELECT nome FROM secao_ordem WHERE projeto_id=? ORDER BY ordem, nome", (chave,))]
        em_uso = [l["secao"] for l in self.con.execute(
            "SELECT DISTINCT secao FROM tarefa WHERE secao != '' AND apagada_em IS NULL AND "
            + ("projeto_id IS NULL" if projeto_id is None else "projeto_id = ?"),
            () if projeto_id is None else (projeto_id,))]
        return ordenadas + sorted(n for n in em_uso if n not in ordenadas)

    def definir_secoes(self, projeto_id: int | None, nomes: list[str]) -> None:
        chave = projeto_id if projeto_id is not None else 0
        self.con.execute("DELETE FROM secao_ordem WHERE projeto_id=?", (chave,))
        for i, nome in enumerate(dict.fromkeys(n.strip() for n in nomes if n.strip())):
            self.con.execute("INSERT INTO secao_ordem(projeto_id, nome, ordem) VALUES (?,?,?)", (chave, nome, i))
        self.con.commit()
