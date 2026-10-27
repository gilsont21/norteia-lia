import sqlite3
from datetime import timedelta

from norteia.core import Banco, Servico
from norteia.core.models import agora_utc

ESQUEMA_V1 = """
CREATE TABLE projeto (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
  cor TEXT NOT NULL DEFAULT '#4f7cff', ordem INTEGER NOT NULL DEFAULT 0, arquivado INTEGER NOT NULL DEFAULT 0);
CREATE TABLE tag (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE,
  cor TEXT NOT NULL DEFAULT '#8a8f98');
CREATE TABLE tarefa (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL,
  notas TEXT NOT NULL DEFAULT '', projeto_id INTEGER, pai_id INTEGER,
  prioridade INTEGER NOT NULL DEFAULT 0, prazo TEXT, concluida_em TEXT,
  criada_em TEXT NOT NULL, atualizada_em TEXT NOT NULL, apagada_em TEXT,
  ordem INTEGER NOT NULL DEFAULT 0);
CREATE TABLE tarefa_tag (tarefa_id INTEGER NOT NULL, tag_id INTEGER NOT NULL, PRIMARY KEY (tarefa_id, tag_id));
"""


def _banco_antigo(caminho):
    con = sqlite3.connect(caminho)
    con.executescript(ESQUEMA_V1)
    con.execute("INSERT INTO projeto(nome) VALUES ('Faculdade')")
    con.execute("INSERT INTO tag(nome) VALUES ('si601')")
    for n in range(3):
        con.execute(
            "INSERT INTO tarefa(titulo, projeto_id, prazo, criada_em, atualizada_em) VALUES (?,?,?,?,?)",
            (f"Antiga {n}", 1, "2026-10-20", "2026-10-01T10:00:00", "2026-10-01T10:00:00"),
        )
    con.execute("INSERT INTO tarefa_tag VALUES (1, 1)")
    con.commit()
    con.close()


def test_migra_banco_antigo_sem_perder_dados(tmp_path):
    arq = tmp_path / "velho.db"
    _banco_antigo(arq)
    b = Banco(arq)
    tarefas = b.consultar()
    assert [t.titulo for t in tarefas] == ["Antiga 0", "Antiga 1", "Antiga 2"]
    assert tarefas[0].tags == ["si601"]
    assert len({t.uuid for t in tarefas}) == 3 and all(t.uuid for t in tarefas)
    assert b.listar_projetos()[0].uuid and b.listar_tags()[0].uuid
    assert b.con.execute("PRAGMA user_version").fetchone()[0] == 6


def test_migracao_e_idempotente_e_mantem_uuid(tmp_path):
    arq = tmp_path / "velho.db"
    _banco_antigo(arq)
    uuids = [t.uuid for t in Banco(arq).consultar()]
    assert [t.uuid for t in Banco(arq).consultar()] == uuids


def test_datas_em_utc_com_fuso():
    svc = Servico(Banco(":memory:"))
    t = svc.adicionar_rapido("x")
    de_volta = svc.banco.obter_tarefa(t.id)
    assert de_volta.criada_em.tzinfo is not None
    assert de_volta.atualizada_em.utcoffset() == timedelta(0)


def test_alteradas_desde_entrega_so_o_que_mudou():
    svc = Servico(Banco(":memory:"))
    a = svc.adicionar_rapido("antiga")
    marco = agora_utc()
    b = svc.adicionar_rapido("nova")
    svc.alternar_conclusao(a.id)
    uuids = {t.uuid for t in svc.banco.alteradas_desde(marco)}
    assert uuids == {a.uuid, b.uuid}
    assert svc.banco.alteradas_desde(agora_utc() + timedelta(seconds=1)) == []


def test_id_do_dispositivo_e_estavel():
    b = Banco(":memory:")
    assert b.id_dispositivo() == b.id_dispositivo()


def test_uuid_unico_e_busca_por_uuid():
    svc = Servico(Banco(":memory:"))
    t = svc.adicionar_rapido("achar")
    assert svc.banco.obter_tarefa_por_uuid(t.uuid).id == t.id
