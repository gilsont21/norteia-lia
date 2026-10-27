"""Testes da integração com o Google Calendar, com uma API do Google simulada (nada sai para a internet)."""
import copy
import hashlib
import base64
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, time as hora, timedelta, timezone

import pytest

from norteia.core import Banco, Servico
from norteia.core import google_agenda as ga
from norteia.core.google_agenda import (Cofre, ErroGoogle, Google, SemAutorizacao, corpo_evento, hash_corpo,
                                        linha_do_evento, login_pelo_navegador, mudancas_do_evento)


@pytest.fixture(autouse=True)
def fuso_brasil():
    antigo = os.environ.get("TZ")
    os.environ["TZ"] = "America/Sao_Paulo"
    time.tzset()
    yield
    if antigo is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = antigo
    time.tzset()


def _agora_z():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class GoogleFalso:
    """Imita o que a API do Google responde, o bastante para os testes."""

    def __init__(self):
        self.calendarios = {"eu@gmail.com": {"id": "eu@gmail.com", "summary": "Gilson", "primary": True,
                                              "backgroundColor": "#9fe1e7"},
                            "trab@group.calendar.google.com": {"id": "trab@group.calendar.google.com",
                                                               "summary": "Trabalho", "backgroundColor": "#f83a22"}}
        self.eventos: dict[str, dict[str, dict]] = {c: {} for c in self.calendarios}
        self.log: dict[str, list[tuple[int, str]]] = {c: [] for c in self.calendarios}
        self.seq = 0
        self.chamadas: list[tuple[str, str]] = []
        self.token_expirado = False
        self.vencer_sync_tokens = False
        self.recusar_refresh = False
        self.n_tokens = 0

    # ---- ajudantes de teste
    def _tocar(self, cal, ev):
        self.seq += 1
        ev["etag"] = f'"e{self.seq}"'
        ev["updated"] = _agora_z()
        self.log[cal].append((self.seq, ev["id"]))

    def por_google(self, cal, ev):
        """Simula alguém criando/editando o evento no site do Google."""
        ev = copy.deepcopy(ev)
        ev.setdefault("id", f"g{len(self.eventos[cal]) + 1}_{self.seq}")
        ev.setdefault("status", "confirmed")
        ev.setdefault("htmlLink", "https://calendar.google.com/event?eid=" + ev["id"])
        antigo = self.eventos[cal].get(ev["id"])
        if antigo:
            antigo.update(ev)
            ev = antigo
        else:
            self.eventos[cal][ev["id"]] = ev
        self._tocar(cal, ev)
        return ev

    def apagar_por_google(self, cal, ev_id):
        self.eventos[cal][ev_id]["status"] = "cancelled"
        self._tocar(cal, self.eventos[cal][ev_id])

    def da_tarefa(self, cal_nome="Tarefas"):
        cid = next(c for c, v in self.calendarios.items() if v["summary"] == cal_nome)
        return cid, self.eventos[cid]

    # ---- o "servidor"
    def __call__(self, metodo, url, cabecalhos, corpo=None, timeout=30):
        p = urllib.parse.urlparse(url)
        caminho, q = p.path, {k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()}
        if url.startswith(ga.URL_TOKEN):
            self.n_tokens += 1
            form = urllib.parse.parse_qs(corpo.decode())
            if form.get("grant_type") == ["refresh_token"]:
                if self.recusar_refresh:
                    return 400, {"error": "invalid_grant"}
                return 200, {"access_token": f"acesso{self.n_tokens}", "expires_in": 3600}
            return 200, {"access_token": "acesso0", "refresh_token": "renova0", "expires_in": 3600}
        self.chamadas.append((metodo, caminho.replace("/calendar/v3", "") + (("?" + p.query) if p.query else "")))
        if self.token_expirado and cabecalhos.get("Authorization") != "Bearer acesso" + str(self.n_tokens):
            return 401, {"error": {"message": "expirou"}}
        corpo_json = json.loads(corpo) if corpo else None
        c = caminho.replace("/calendar/v3", "")
        if c == "/users/me/calendarList":
            return 200, {"items": list(self.calendarios.values())}
        if c == "/calendars" and metodo == "POST":
            cid = f"tarefas{len(self.calendarios)}@group.calendar.google.com"
            self.calendarios[cid] = {"id": cid, "summary": corpo_json["summary"], "backgroundColor": "#16a765"}
            self.eventos[cid], self.log[cid] = {}, []
            return 200, {"id": cid, "summary": corpo_json["summary"]}
        partes = [urllib.parse.unquote(x) for x in c.split("/") if x]
        cal = partes[1]
        if len(partes) == 3 and partes[2] == "events" and metodo == "GET":
            if "syncToken" in q:
                if self.vencer_sync_tokens:
                    return 410, {"error": {"message": "Gone"}}
                desde = int(q["syncToken"].replace("tok", ""))
                ids = []
                for s, i in self.log[cal]:
                    if s > desde and i not in ids:
                        ids.append(i)
                itens = [copy.deepcopy(self.eventos[cal][i]) for i in ids]
            else:
                itens = [copy.deepcopy(e) for e in self.eventos[cal].values() if e["status"] != "cancelled"]
            return 200, {"items": itens, "nextSyncToken": f"tok{self.seq}"}
        if len(partes) == 3 and partes[2] == "events" and metodo == "POST":
            ev = dict(corpo_json)
            ev["id"] = f"ev{self.seq + 1}"
            ev["status"] = "confirmed"
            ev["htmlLink"] = "https://calendar.google.com/event?eid=" + ev["id"]
            self.eventos[cal][ev["id"]] = ev
            self._tocar(cal, ev)
            return 200, copy.deepcopy(ev)
        ev_id = partes[3]
        if metodo == "PATCH":
            ev = self.eventos[cal].get(ev_id)
            if ev is None or ev["status"] == "cancelled":
                return 404, {"error": {"message": "Not Found"}}
            for k, v in corpo_json.items():
                if isinstance(v, dict) and isinstance(ev.get(k), dict):
                    ev[k].update(v)
                    ev[k] = {a: b for a, b in ev[k].items() if b is not None}
                else:
                    ev[k] = v
            self._tocar(cal, ev)
            return 200, copy.deepcopy(ev)
        if metodo == "DELETE":
            ev = self.eventos[cal].get(ev_id)
            if ev is None or ev["status"] == "cancelled":
                return 410, {"error": {"message": "Resource has been deleted"}}
            ev["status"] = "cancelled"
            self._tocar(cal, ev)
            return 204, {}
        return 404, {}


@pytest.fixture
def mundo(tmp_path):
    svc = Servico(Banco(":memory:"), pasta_dados=tmp_path)
    falso = GoogleFalso()
    g = Google(svc, transporte=falso, cofre=Cofre(svc.banco, usar_keyring=False))
    g.cliente.definir_credenciais("id-cliente", "segredo")
    g.cliente.guardar_login({"refresh_token": "renova0", "access_token": "", "expira_em": 0})
    return svc, falso, g


def marcar(g, nome):
    g._atualizar_calendarios()
    a = next(x for x in g.calendarios() if x["nome"] == nome)
    g.definir_calendario_ativo(a["id"], True)
    return a


def tarefa(svc, titulo, dia, h=None, **kw):
    t = svc.adicionar_rapido(titulo)
    t.prazo, t.prazo_hora = dia, h
    for k, v in kw.items():
        setattr(t, k, v)
    return svc.salvar(t)


# ================= login e credenciais =================
def test_login_pelo_navegador_usa_pkce_e_devolve_tokens():
    pedidos = []

    def transporte(metodo, url, cab, corpo=None, timeout=30):
        pedidos.append(urllib.parse.parse_qs(corpo.decode()))
        return 200, {"access_token": "A", "refresh_token": "R", "expires_in": 3600}

    def navegador(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"]
        assert q["scope"] == [ga.ESCOPO]
        navegador.desafio = q["code_challenge"][0]
        destino = q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": "codigo123", "state": q["state"][0]})
        threading.Thread(target=lambda: urllib.request.urlopen(destino, timeout=5).read(), daemon=True).start()

    r = login_pelo_navegador("cid", "sec", abrir=navegador, transporte=transporte, tempo_limite=10)
    assert r["refresh_token"] == "R" and r["access_token"] == "A"
    enviado = pedidos[0]
    assert enviado["code"] == ["codigo123"] and enviado["client_secret"] == ["sec"]
    esperado = base64.urlsafe_b64encode(hashlib.sha256(enviado["code_verifier"][0].encode()).digest()).rstrip(b"=")
    assert esperado.decode() == navegador.desafio


def test_login_recusado_ou_com_estado_errado_falha():
    def navegador(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        destino = q["redirect_uri"][0] + "?error=access_denied&state=" + q["state"][0]
        threading.Thread(target=lambda: urllib.request.urlopen(destino, timeout=5).read(), daemon=True).start()

    with pytest.raises(ErroGoogle, match="não autorizou"):
        login_pelo_navegador("cid", "sec", abrir=navegador, transporte=lambda *a, **k: (200, {}), tempo_limite=10)


def test_cofre_cai_para_a_tabela_meta_sem_keyring():
    banco = Banco(":memory:")
    c = Cofre(banco, usar_keyring=False)
    assert c.ler("x") == ""
    c.gravar("x", "segredo")
    assert c.ler("x") == "segredo" and banco.meta("google_cofre_x") == "segredo"
    c.apagar("x")
    assert c.ler("x") == ""


def test_renova_o_token_e_repete_a_chamada_quando_expira(mundo):
    svc, falso, g = mundo
    g.cliente.listar_calendarios()
    assert falso.n_tokens == 1
    falso.token_expirado = True
    falso.n_tokens += 100                      # o token antigo "expirou" no servidor
    g.cliente.listar_calendarios()             # recebe 401, renova e repete
    assert falso.n_tokens >= 102


def test_autorizacao_recusada_pede_novo_login(mundo):
    svc, falso, g = mundo
    falso.recusar_refresh = True
    r = g.sincronizar()
    assert "entrar de novo" in r.erro


def test_sem_login_nao_sincroniza():
    svc = Servico(Banco(":memory:"))
    g = Google(svc, transporte=GoogleFalso(), cofre=Cofre(svc.banco, usar_keyring=False))
    assert not g.conectado and "não conectada" in g.sincronizar().erro


# ================= Google -> app =================
def test_calendarios_novos_comecam_desligados(mundo):
    svc, falso, g = mundo
    r = g.sincronizar()
    nomes = {a["nome"]: a["ativa"] for a in g.calendarios()}
    assert nomes == {"Gilson": 0, "Trabalho": 0} and r.eventos_lidos == 0
    assert g.conta == "eu@gmail.com"


def test_le_eventos_do_calendario_marcado_e_mostra_no_calendario(mundo):
    svc, falso, g = mundo
    hoje = date.today()
    falso.por_google("trab@group.calendar.google.com", {
        "summary": "Audiência", "location": "Fórum",
        "start": {"dateTime": f"{hoje}T12:00:00Z"}, "end": {"dateTime": f"{hoje}T13:30:00Z"}})
    falso.por_google("trab@group.calendar.google.com", {
        "summary": "Feriado", "start": {"date": str(hoje + timedelta(days=1))},
        "end": {"date": str(hoje + timedelta(days=3))}})
    falso.por_google("eu@gmail.com", {"summary": "Pessoal oculto",
                                      "start": {"date": str(hoje)}, "end": {"date": str(hoje + timedelta(days=1))}})
    marcar(g, "Trabalho")
    r = g.sincronizar()
    assert r.eventos_lidos == 2
    oc = svc.calendario.ocorrencias(hoje, hoje + timedelta(days=3))
    titulos = {o.titulo: o for o in oc}
    assert "Pessoal oculto" not in titulos                    # calendário não marcado fica de fora
    aud = titulos["Audiência"]
    assert aud.externo and aud.hora == hora(9, 0) and aud.duracao_min == 90      # 12h UTC = 9h em São Paulo
    assert aud.link.startswith("https://calendar.google.com")
    fer = titulos["Feriado"]
    assert fer.dia_inteiro and (fer.inicio, fer.fim) == (hoje + timedelta(days=1), hoje + timedelta(days=2))


def test_leitura_incremental_aplica_mudancas_e_cancelamentos(mundo):
    svc, falso, g = mundo
    hoje = date.today()
    cal = "trab@group.calendar.google.com"
    ev = falso.por_google(cal, {"summary": "Reunião", "start": {"date": str(hoje)},
                                "end": {"date": str(hoje + timedelta(days=1))}})
    marcar(g, "Trabalho")
    g.sincronizar()
    falso.chamadas.clear()
    falso.por_google(cal, {"id": ev["id"], "summary": "Reunião (remarcada)"})
    novo = falso.por_google(cal, {"summary": "Outro", "start": {"date": str(hoje)},
                                  "end": {"date": str(hoje + timedelta(days=1))}})
    r = g.sincronizar()
    assert r.eventos_lidos == 2
    assert any("syncToken" in c[1] for c in falso.chamadas)                 # só pediu o que mudou
    titulos = sorted(o.titulo for o in svc.calendario.ocorrencias(hoje, hoje))
    assert titulos == ["Outro", "Reunião (remarcada)"]
    falso.apagar_por_google(cal, novo["id"])
    g.sincronizar()
    assert [o.titulo for o in svc.calendario.ocorrencias(hoje, hoje)] == ["Reunião (remarcada)"]


def test_token_de_sincronizacao_vencido_refaz_tudo(mundo):
    svc, falso, g = mundo
    hoje = date.today()
    cal = "trab@group.calendar.google.com"
    falso.por_google(cal, {"summary": "A", "start": {"date": str(hoje)}, "end": {"date": str(hoje + timedelta(days=1))}})
    marcar(g, "Trabalho")
    g.sincronizar()
    falso.vencer_sync_tokens = True
    falso.por_google(cal, {"summary": "B", "start": {"date": str(hoje)}, "end": {"date": str(hoje + timedelta(days=1))}})
    g.sincronizar()
    assert sorted(o.titulo for o in svc.calendario.ocorrencias(hoje, hoje)) == ["A", "B"]


def test_evento_recusado_nao_aparece():
    ev = {"id": "x", "summary": "Convite", "start": {"date": "2026-10-26"}, "end": {"date": "2026-10-27"},
          "attendees": [{"self": True, "responseStatus": "declined"}]}
    assert linha_do_evento(ev) is None
    assert linha_do_evento({"id": "y", "status": "cancelled"}) is None


def test_desmarcar_calendario_esquece_os_eventos(mundo):
    svc, falso, g = mundo
    hoje = date.today()
    falso.por_google("trab@group.calendar.google.com", {"summary": "A", "start": {"date": str(hoje)},
                                                         "end": {"date": str(hoje + timedelta(days=1))}})
    a = marcar(g, "Trabalho")
    g.sincronizar()
    assert svc.calendario.ocorrencias(hoje, hoje)
    g.definir_calendario_ativo(a["id"], False)
    assert not svc.calendario.ocorrencias(hoje, hoje)


# ================= app -> Google =================
def test_envia_tarefas_como_eventos_no_calendario_tarefas(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    hoje = date.today()
    p = svc.criar_projeto("Faculdade")
    t1 = tarefa(svc, "Estudar", hoje, hora(14, 30), duracao_min=45, lembretes=[10, 0], notas="capítulo 3",
                projeto_id=p.id)
    t2 = tarefa(svc, "Pagar boleto", hoje + timedelta(days=2))
    t3 = tarefa(svc, "Viagem", hoje + timedelta(days=5), inicio=hoje + timedelta(days=3))
    r = g.sincronizar()
    assert r.enviados == 3
    cid, evs = falso.da_tarefa()
    por_titulo = {e["summary"]: e for e in evs.values()}
    e1 = por_titulo["Estudar"]
    assert e1["start"]["dateTime"].startswith(f"{hoje}T14:30") and e1["end"]["dateTime"].startswith(f"{hoje}T15:15")
    assert e1["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0},
                                                                  {"method": "popup", "minutes": 10}]}
    assert "capítulo 3" in e1["description"] and "Lista: Faculdade" in e1["description"]
    assert e1["extendedProperties"]["private"]["tarefa_uuid"] == t1.uuid
    e2 = por_titulo["Pagar boleto"]
    assert e2["start"] == {"date": str(hoje + timedelta(days=2))} and e2["end"] == {"date": str(hoje + timedelta(days=3))}
    e3 = por_titulo["Viagem"]
    assert e3["start"] == {"date": str(hoje + timedelta(days=3))} and e3["end"] == {"date": str(hoje + timedelta(days=6))}
    assert [a["nome"] for a in g.calendarios()].count("Tarefas") == 1


def test_segunda_sincronizacao_sem_mudancas_nao_chama_a_api_de_eventos(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    tarefa(svc, "Algo", date.today())
    g.sincronizar()
    falso.chamadas.clear()
    r = g.sincronizar()
    assert (r.enviados, r.atualizados, r.removidos, r.alteradas_no_google) == (0, 0, 0, 0)
    assert not [c for c in falso.chamadas if c[0] in ("POST", "PATCH", "DELETE")]


def test_editar_concluir_e_apagar_tarefa_atualiza_o_evento(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    t = tarefa(svc, "Ler", date.today(), hora(8, 0))
    g.sincronizar()
    cid, evs = falso.da_tarefa()
    ev_id = next(iter(evs))
    t.titulo = "Ler o artigo"
    svc.salvar(t)
    r = g.sincronizar()
    assert r.atualizados == 1 and evs[ev_id]["summary"] == "Ler o artigo"
    svc.alternar_conclusao(t.id)
    g.sincronizar()
    assert evs[ev_id]["summary"] == "✓ Ler o artigo"
    svc.apagar(t.id)
    r = g.sincronizar()
    assert r.removidos == 1 and evs[ev_id]["status"] == "cancelled"
    assert svc.banco.con.execute("SELECT COUNT(*) FROM ligacao_google").fetchone()[0] == 0


def test_tarefa_sem_data_ou_descartada_nao_vai_e_perder_a_data_remove_o_evento(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    svc.adicionar_rapido("Sem data")
    t = tarefa(svc, "Com data", date.today())
    assert g.sincronizar().enviados == 1
    t.prazo = None
    svc.salvar(t)
    assert g.sincronizar().removidos == 1


def test_enviar_desligado_nao_cria_calendario(mundo):
    svc, falso, g = mundo
    tarefa(svc, "X", date.today())
    g.sincronizar()
    assert not any(c[0] == "POST" for c in falso.chamadas)
    assert "Tarefas" not in [a["nome"] for a in g.calendarios()]


def test_calendario_tarefas_nao_aparece_duplicado_como_leitura(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    t = tarefa(svc, "Só uma vez", date.today())
    g.sincronizar()
    a = next(x for x in g.calendarios() if x["nome"] == "Tarefas")
    g.definir_calendario_ativo(a["id"], True)               # mesmo marcado, ele não é lido como evento externo
    g.sincronizar()
    ocs = svc.calendario.ocorrencias(date.today(), date.today())
    assert [o.titulo for o in ocs].count("Só uma vez") == 1


# ================= edição nos dois lados =================
def test_mudar_o_evento_no_google_muda_a_tarefa_sem_voltar_para_o_google(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    hoje = date.today()
    t = tarefa(svc, "Reunião", hoje, hora(10, 0))
    g.sincronizar()
    cid, evs = falso.da_tarefa()
    ev_id = next(iter(evs))
    amanha = hoje + timedelta(days=1)
    time.sleep(0.01)
    falso.por_google(cid, {"id": ev_id, "summary": "Reunião com cliente",
                           "start": {"dateTime": f"{amanha}T18:00:00-03:00"},
                           "end": {"dateTime": f"{amanha}T19:30:00-03:00"}})
    falso.chamadas.clear()
    r = g.sincronizar()
    novo = svc.banco.obter_tarefa(t.id)
    assert r.alteradas_no_google == 1
    assert (novo.titulo, novo.prazo, novo.prazo_hora, novo.duracao_min) == ("Reunião com cliente", amanha,
                                                                            hora(18, 0), 90)
    assert not [c for c in falso.chamadas if c[0] in ("PATCH", "POST")]       # nada voltou para o Google
    falso.chamadas.clear()
    g.sincronizar()
    assert not [c for c in falso.chamadas if c[0] in ("PATCH", "POST", "DELETE")]


def test_marcar_check_no_titulo_conclui_a_tarefa(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    t = tarefa(svc, "Treino", date.today())
    g.sincronizar()
    cid, evs = falso.da_tarefa()
    ev_id = next(iter(evs))
    falso.por_google(cid, {"id": ev_id, "summary": "✓ Treino"})
    g.sincronizar()
    assert svc.banco.obter_tarefa(t.id).concluida


def test_tarefa_mais_nova_que_o_evento_vence_o_conflito(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    t = tarefa(svc, "Original", date.today())
    g.sincronizar()
    cid, evs = falso.da_tarefa()
    ev_id = next(iter(evs))
    falso.por_google(cid, {"id": ev_id, "summary": "Editado no Google"})
    falso.eventos[cid][ev_id]["updated"] = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")
    t = svc.banco.obter_tarefa(t.id)
    t.titulo = "Editado no app"
    svc.salvar(t)
    g.sincronizar()
    assert svc.banco.obter_tarefa(t.id).titulo == "Editado no app"
    assert evs[ev_id]["summary"] == "Editado no app"


def test_apagar_o_evento_no_google_nao_apaga_a_tarefa_nem_recria_sozinho(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    t = tarefa(svc, "Dentista", date.today())
    g.sincronizar()
    cid, evs = falso.da_tarefa()
    ev_id = next(iter(evs))
    falso.apagar_por_google(cid, ev_id)
    g.sincronizar()
    assert svc.banco.obter_tarefa(t.id) is not None and svc.banco.obter_tarefa(t.id).apagada_em is None
    falso.chamadas.clear()
    g.sincronizar()
    assert not [c for c in falso.chamadas if c[0] == "POST"]               # não ressuscita
    t = svc.banco.obter_tarefa(t.id)
    t.prazo = date.today() + timedelta(days=3)                             # mudou a tarefa: aí sim recria
    svc.salvar(t)
    r = g.sincronizar()
    assert r.enviados == 1


def test_evento_criado_no_google_no_calendario_tarefas_vira_tarefa(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    g.sincronizar()
    cid, evs = falso.da_tarefa()
    amanha = date.today() + timedelta(days=1)
    falso.por_google(cid, {"summary": "Ideia do celular", "start": {"date": str(amanha)},
                           "end": {"date": str(amanha + timedelta(days=1))}})
    r = g.sincronizar()
    assert r.importados == 1
    achada = [t for t in svc.banco.consultar() if t.titulo == "Ideia do celular"]
    assert len(achada) == 1 and achada[0].prazo == amanha and achada[0].prazo_hora is None
    falso.chamadas.clear()
    g.sincronizar()
    assert len([t for t in svc.banco.consultar() if t.titulo == "Ideia do celular"]) == 1


# ================= conversões puras =================
def test_mudancas_do_evento_dia_inteiro_e_periodo():
    m = mudancas_do_evento({"summary": "✓ Viagem", "start": {"date": "2026-11-02"}, "end": {"date": "2026-11-06"}})
    assert m["concluida"] and m["titulo"] == "Viagem"
    assert (m["inicio"], m["prazo"], m["hora"]) == (date(2026, 11, 2), date(2026, 11, 5), None)
    m = mudancas_do_evento({"summary": "X", "start": {"date": "2026-11-02"}, "end": {"date": "2026-11-03"}})
    assert (m["inicio"], m["prazo"]) == (None, date(2026, 11, 2))


def test_corpo_evento_horario_respeita_o_fuso_local():
    from norteia.core.models import Tarefa
    t = Tarefa(titulo="Aula", prazo=date(2026, 10, 26), prazo_hora=hora(19, 0))
    c = corpo_evento(t)
    assert c["start"]["dateTime"] == "2026-10-26T19:00:00-03:00" and c["end"]["dateTime"] == "2026-10-26T20:00:00-03:00"
    assert hash_corpo(c) == hash_corpo(corpo_evento(t))


# ================= em arquivo / banco =================
def test_sincronizar_arquivo_usa_conexao_propria(tmp_path):
    caminho = tmp_path / "t.db"
    svc = Servico(Banco(caminho), pasta_dados=tmp_path)
    falso = GoogleFalso()
    g = Google(svc, transporte=falso, cofre=Cofre(svc.banco, usar_keyring=False))
    g.cliente.definir_credenciais("id", "seg")
    g.cliente.guardar_login({"refresh_token": "r", "access_token": "", "expira_em": 0})
    g.definir_enviar_tarefas(True)
    tarefa(svc, "Pelo arquivo", date.today())
    resultado = []
    t = threading.Thread(target=lambda: resultado.append(ga.sincronizar_arquivo(str(caminho), tmp_path, falso)))
    t.start()
    t.join(20)
    assert resultado and resultado[0].enviados == 1 and not resultado[0].erro
    assert svc.banco.con.execute("SELECT COUNT(*) FROM ligacao_google").fetchone()[0] == 1


def test_sair_apaga_calendarios_e_ligacoes(mundo):
    svc, falso, g = mundo
    g.definir_enviar_tarefas(True)
    tarefa(svc, "Algo", date.today())
    g.sincronizar()
    g.sair()
    assert not g.conectado and g.calendarios() == []
    assert svc.banco.con.execute("SELECT COUNT(*) FROM ligacao_google").fetchone()[0] == 0
    assert not g.enviar_tarefas
