"""Integração com o Google Calendar pela API oficial (v3), sem bibliotecas externas.

Dois sentidos:
  * Google -> app: os calendários que você marcar aparecem no calendário, somente leitura.
  * App -> Google: as tarefas com data viram eventos num calendário próprio chamado "Tarefas". Se você mexer num
    desses eventos no Google (título, dia, hora, "✓"), a tarefa muda aqui; vale a alteração mais recente.

Segurança: o login é feito no navegador (nunca passa senha pelo app). A chave de renovação fica no cofre de
credenciais do sistema (Windows: Gerenciador de Credenciais) quando a biblioteca `keyring` existe, ou na tabela
`meta` local. Nada disso vai para o servidor de sincronização.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from datetime import date, datetime, time as hora_t, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from .models import Tarefa, agora_utc

URL_AUTORIZACAO = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_API = "https://www.googleapis.com/calendar/v3"
ESCOPO = "https://www.googleapis.com/auth/calendar"
NOME_CALENDARIO_TAREFAS = "Tarefas"
DURACAO_PADRAO_MIN = 60
JANELA_ANTES_DIAS = 60
JANELA_DEPOIS_DIAS = 400
RECARGA_COMPLETA_DIAS = 14
PREFIXO_FEITA = "✓ "


class ErroGoogle(Exception):
    def __init__(self, mensagem: str, status: int = 0):
        super().__init__(mensagem)
        self.status = status


class SemAutorizacao(ErroGoogle):
    """O Google recusou a chave guardada: é preciso entrar de novo."""


# ---------------------------------------------------------------- transporte HTTP
def transporte_padrao(metodo: str, url: str, cabecalhos: dict, corpo: bytes | None = None, timeout: int = 30):
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        dados, status = e.read(), e.code
    except urllib.error.URLError as e:
        raise ErroGoogle(f"Sem conexão com o Google ({e.reason}).") from e
    except OSError as e:
        raise ErroGoogle(f"Sem conexão com o Google ({e}).") from e
    try:
        return status, (json.loads(dados) if dados else {})
    except ValueError:
        return status, {}


# ---------------------------------------------------------------- cofre de credenciais
class Cofre:
    SERVICO = "app-tarefas-google"
    PREFIXO_META = "google_cofre_"     # reserva quando não há cofre do sistema (só neste banco local)

    def __init__(self, banco, usar_keyring: bool = True):
        self.banco = banco
        self._kr = None
        if usar_keyring:
            try:
                import keyring  # noqa: PLC0415
                self._kr = keyring
            except Exception:  # noqa: BLE001
                self._kr = None

    def ler(self, chave: str) -> str:
        if self._kr is not None:
            try:
                v = self._kr.get_password(self.SERVICO, chave)
                if v:
                    return v
            except Exception:  # noqa: BLE001
                pass
        return self.banco.meta(self.PREFIXO_META + chave, "") or ""

    def gravar(self, chave: str, valor: str) -> None:
        if self._kr is not None:
            try:
                self._kr.set_password(self.SERVICO, chave, valor)
                self.banco.definir_meta(self.PREFIXO_META + chave, "")
                return
            except Exception:  # noqa: BLE001
                pass
        self.banco.definir_meta(self.PREFIXO_META + chave, valor)

    def apagar(self, chave: str) -> None:
        if self._kr is not None:
            try:
                self._kr.delete_password(self.SERVICO, chave)
            except Exception:  # noqa: BLE001
                pass
        self.banco.definir_meta(self.PREFIXO_META + chave, "")


# ---------------------------------------------------------------- login no navegador (OAuth + PKCE)
def _pkce() -> tuple[str, str]:
    verificador = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return verificador, desafio


_PAGINA_OK = ("<html><head><meta charset='utf-8'><title>Norteia</title></head><body style='font-family:sans-serif;"
              "background:#1c1c1c;color:#e8e8e8;text-align:center;padding-top:80px'><h2>Tudo certo!</h2>"
              "<p>O Google Calendar foi conectado. Pode fechar esta aba e voltar para o Norteia.</p></body></html>")
_PAGINA_ERRO = ("<html><head><meta charset='utf-8'><title>Norteia</title></head><body style='font-family:sans-serif;"
                "background:#1c1c1c;color:#e8e8e8;text-align:center;padding-top:80px'><h2>Não deu certo</h2>"
                "<p>{msg}</p></body></html>")


def login_pelo_navegador(client_id: str, client_secret: str, abrir=webbrowser.open, transporte=transporte_padrao,
                         tempo_limite: int = 180, ao_abrir=None) -> dict:
    """Abre o navegador, espera você aprovar e devolve {"refresh_token", "access_token", "expira_em"}.

    `abrir(url)` é injetável para testes. `ao_abrir(url)` avisa a tela de que o navegador foi aberto.
    """
    verificador, desafio = _pkce()
    estado = secrets.token_urlsafe(16)
    resultado: dict = {}

    class Receptor(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q or "error" in q:
                if q.get("state", [""])[0] != estado:
                    resultado["erro"] = "Resposta com identificador inesperado. Tente de novo."
                elif "error" in q:
                    resultado["erro"] = ("Você não autorizou o acesso." if q["error"][0] == "access_denied"
                                         else f"O Google respondeu: {q['error'][0]}")
                else:
                    resultado["codigo"] = q["code"][0]
                corpo = (_PAGINA_ERRO.format(msg=resultado["erro"]) if "erro" in resultado else _PAGINA_OK).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *_):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Receptor)
    servidor.timeout = 0.5
    porta = servidor.server_address[1]
    redirecionar = f"http://127.0.0.1:{porta}"
    url = URL_AUTORIZACAO + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirecionar, "response_type": "code", "scope": ESCOPO,
        "code_challenge": desafio, "code_challenge_method": "S256", "access_type": "offline",
        "prompt": "consent", "state": estado})
    try:
        abrir(url)
        if ao_abrir:
            ao_abrir(url)
        limite = time.monotonic() + tempo_limite
        while not resultado and time.monotonic() < limite:
            servidor.handle_request()
    finally:
        servidor.server_close()
    if "erro" in resultado:
        raise ErroGoogle(resultado["erro"])
    if "codigo" not in resultado:
        raise ErroGoogle("O login demorou demais e foi cancelado. Tente de novo.")
    corpo = urllib.parse.urlencode({
        "code": resultado["codigo"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirecionar, "grant_type": "authorization_code", "code_verifier": verificador}).encode()
    status, dados = transporte("POST", URL_TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, corpo)
    if status != 200 or "access_token" not in dados:
        raise ErroGoogle("O Google não aceitou o código de login: "
                         + str(dados.get("error_description") or dados.get("error") or status), status)
    if not dados.get("refresh_token"):
        raise ErroGoogle("O Google não devolveu a autorização permanente. Remova o acesso do app em "
                         "myaccount.google.com/permissions e tente de novo.")
    return {"refresh_token": dados["refresh_token"], "access_token": dados["access_token"],
            "expira_em": time.time() + int(dados.get("expires_in", 3600))}


# ---------------------------------------------------------------- cliente da API
class ClienteGoogle:
    def __init__(self, banco, transporte=transporte_padrao, cofre: Cofre | None = None, relogio=time.time):
        self.banco = banco
        self.transporte = transporte
        self.cofre = cofre or Cofre(banco)
        self.relogio = relogio
        self._acesso = ""
        self._acesso_ate = 0.0

    # credenciais do projeto do Google Cloud (o "Client ID" e o "Client secret" que você cria uma vez)
    @property
    def client_id(self) -> str:
        return self.banco.meta("google_client_id", "") or ""

    @property
    def client_secret(self) -> str:
        return self.cofre.ler("client_secret")

    def definir_credenciais(self, client_id: str, client_secret: str) -> None:
        self.banco.definir_meta("google_client_id", client_id.strip())
        self.cofre.gravar("client_secret", client_secret.strip())

    @property
    def configurado(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def conectado(self) -> bool:
        return bool(self.cofre.ler("refresh_token"))

    def guardar_login(self, dados: dict) -> None:
        self.cofre.gravar("refresh_token", dados["refresh_token"])
        self._acesso, self._acesso_ate = dados.get("access_token", ""), dados.get("expira_em", 0.0)

    def desconectar(self) -> None:
        """Esquece o login (os eventos já baixados e as ligações com as tarefas ficam até você limpar)."""
        self.cofre.apagar("refresh_token")
        self._acesso, self._acesso_ate = "", 0.0

    # ---- chamadas
    def _token(self) -> str:
        if self._acesso and self.relogio() < self._acesso_ate - 60:
            return self._acesso
        refresh = self.cofre.ler("refresh_token")
        if not refresh:
            raise SemAutorizacao("Conecte sua conta do Google primeiro.")
        corpo = urllib.parse.urlencode({
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
        status, dados = self.transporte("POST", URL_TOKEN, {"Content-Type": "application/x-www-form-urlencoded"},
                                        corpo)
        if status in (400, 401) and dados.get("error") in ("invalid_grant", "invalid_client", "unauthorized_client"):
            raise SemAutorizacao("O Google pediu para você entrar de novo (a autorização expirou ou foi removida).",
                                 status)
        if status != 200 or "access_token" not in dados:
            raise ErroGoogle("Não consegui renovar o acesso ao Google: "
                             + str(dados.get("error_description") or dados.get("error") or status), status)
        self._acesso = dados["access_token"]
        self._acesso_ate = self.relogio() + int(dados.get("expires_in", 3600))
        return self._acesso

    def _chamar(self, metodo: str, caminho: str, params: dict | None = None, corpo: dict | None = None) -> dict:
        url = URL_API + caminho
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        dados = json.dumps(corpo).encode() if corpo is not None else None
        for tentativa in (1, 2):
            cab = {"Authorization": "Bearer " + self._token(), "Accept": "application/json"}
            if dados is not None:
                cab["Content-Type"] = "application/json"
            status, resposta = self.transporte(metodo, url, cab, dados)
            if status == 401 and tentativa == 1:
                self._acesso, self._acesso_ate = "", 0.0       # token velho: renova e tenta de novo
                continue
            break
        if status in (200, 201, 204):
            return resposta
        msg = (resposta.get("error", {}) or {}) if isinstance(resposta.get("error"), dict) else {}
        texto = msg.get("message") or str(resposta.get("error") or status)
        if status == 401:
            raise SemAutorizacao("O Google recusou o acesso. Entre de novo.", status)
        if status == 403 and "rate" in texto.lower():
            raise ErroGoogle("O Google limitou as chamadas por um instante. Tente em alguns minutos.", status)
        raise ErroGoogle(f"Google Calendar: {texto}", status)

    def listar_calendarios(self) -> list[dict]:
        saida, pagina = [], None
        while True:
            r = self._chamar("GET", "/users/me/calendarList", {"maxResults": 250, "pageToken": pagina,
                                                                 "minAccessRole": "reader"})
            saida += r.get("items", [])
            pagina = r.get("nextPageToken")
            if not pagina:
                return saida

    def eventos(self, calendario: str, sync_token: str | None = None, ini: date | None = None,
                fim: date | None = None) -> tuple[list[dict], str]:
        """Todos os eventos (já com as repetições separadas). Com `sync_token`, só o que mudou desde a última vez.
        Devolve (eventos, novo_sync_token). Lança ErroGoogle(status=410) se o token não vale mais."""
        itens, pagina, novo = [], None, ""
        cal = urllib.parse.quote(calendario, safe="")
        while True:
            params = {"singleEvents": "true", "showDeleted": "true", "maxResults": 250, "pageToken": pagina}
            if sync_token:
                params["syncToken"] = sync_token
            else:
                if ini:
                    params["timeMin"] = datetime.combine(ini, hora_t(0, 0)).astimezone().isoformat()
                if fim:
                    params["timeMax"] = datetime.combine(fim, hora_t(0, 0)).astimezone().isoformat()
            r = self._chamar("GET", f"/calendars/{cal}/events", params)
            itens += r.get("items", [])
            pagina = r.get("nextPageToken")
            if not pagina:
                novo = r.get("nextSyncToken", "")
                return itens, novo

    def criar_calendario(self, nome: str) -> dict:
        return self._chamar("POST", "/calendars", corpo={"summary": nome, "description":
                            "Criado pelo app Tarefas. As tarefas com data aparecem aqui."})

    def inserir_evento(self, calendario: str, corpo: dict) -> dict:
        corpo = dict(corpo)
        for lado in ("start", "end"):  # ao criar, campos nulos não fazem sentido (só no PATCH)
            if lado in corpo:
                corpo[lado] = {k: v for k, v in corpo[lado].items() if v is not None}
        return self._chamar("POST", f"/calendars/{urllib.parse.quote(calendario, safe='')}/events", corpo=corpo)

    def alterar_evento(self, calendario: str, evento: str, corpo: dict) -> dict:
        return self._chamar("PATCH", f"/calendars/{urllib.parse.quote(calendario, safe='')}/events/"
                            f"{urllib.parse.quote(evento, safe='')}", corpo=corpo)

    def apagar_evento(self, calendario: str, evento: str) -> None:
        try:
            self._chamar("DELETE", f"/calendars/{urllib.parse.quote(calendario, safe='')}/events/"
                         f"{urllib.parse.quote(evento, safe='')}")
        except ErroGoogle as e:
            if e.status not in (404, 410):          # já tinha sumido: tudo certo
                raise


# ---------------------------------------------------------------- conversões (funções puras)
def _para_local(texto: str) -> datetime:
    """Horário do Google (com fuso) -> horário local do computador, sem fuso."""
    dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _de_local(d: date, h: hora_t) -> str:
    return datetime.combine(d, h).astimezone().isoformat(timespec="seconds")


def linha_do_evento(ev: dict) -> dict | None:
    """Evento do Google -> linha da tabela `evento_externo` (None se não deve aparecer)."""
    if ev.get("status") == "cancelled" or "start" not in ev:
        return None
    for p in ev.get("attendees", []) or []:
        if p.get("self") and p.get("responseStatus") == "declined":
            return None
    s, e = ev["start"], ev.get("end") or ev["start"]
    if "date" in s:
        inicio, fim, inteiro = s["date"], e.get("date") or s["date"], 1
    else:
        inicio = _para_local(s["dateTime"]).isoformat(timespec="seconds")
        fim = _para_local(e.get("dateTime") or s["dateTime"]).isoformat(timespec="seconds")
        inteiro = 0
    return {"uid": ev["id"], "titulo": ev.get("summary") or "(Sem título)", "inicio": inicio, "fim": fim,
            "dia_inteiro": inteiro, "local": ev.get("location") or "", "link": ev.get("htmlLink") or ""}


def corpo_evento(t: Tarefa, nome_lista: str = "") -> dict:
    """Tarefa -> corpo do evento que vai para o Google."""
    titulo = (PREFIXO_FEITA if t.concluida else "") + t.titulo
    if t.prazo_hora is None:
        inicio_dia = t.inicio or t.prazo
        inicio = {"date": inicio_dia.isoformat(), "dateTime": None}
        fim = {"date": (t.prazo + timedelta(days=1)).isoformat(), "dateTime": None}
    else:
        ini_dt = datetime.combine(t.prazo, t.prazo_hora).astimezone()
        fim_dt = ini_dt + timedelta(minutes=t.duracao_min or DURACAO_PADRAO_MIN)
        inicio = {"dateTime": ini_dt.isoformat(timespec="seconds"), "date": None}
        fim = {"dateTime": fim_dt.isoformat(timespec="seconds"), "date": None}
    partes = [t.notas.strip()] if t.notas.strip() else []
    if nome_lista:
        partes.append(f"Lista: {nome_lista}")
    lembretes = [{"method": "popup", "minutes": m} for m in sorted(set(t.lembretes)) if 0 <= m <= 40320][:5]
    return {
        "summary": titulo, "description": "\n\n".join(partes), "start": inicio, "end": fim,
        "reminders": {"useDefault": False, "overrides": lembretes},
        "extendedProperties": {"private": {"tarefa_uuid": t.uuid, "origem": "app-tarefas"}},
    }


def hash_corpo(corpo: dict) -> str:
    return hashlib.sha1(json.dumps(corpo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _momento(ev: dict, lado: str) -> tuple[date, hora_t | None]:
    v = ev[lado]
    if "date" in v:
        return date.fromisoformat(v["date"]), None
    dt = _para_local(v["dateTime"])
    return dt.date(), dt.time().replace(second=0, microsecond=0)


def mudancas_do_evento(ev: dict) -> dict:
    """O que o evento do Google diz sobre a tarefa: título, concluída, prazo, hora, início e duração."""
    resumo = ev.get("summary") or ""
    feita = resumo.startswith(PREFIXO_FEITA.strip())
    titulo = resumo[len(PREFIXO_FEITA.strip()):].lstrip() if feita else resumo
    d_ini, h_ini = _momento(ev, "start")
    if h_ini is None:
        d_fim = _momento(ev, "end")[0] - timedelta(days=1)
        prazo, inicio, hora, duracao = max(d_fim, d_ini), (d_ini if d_fim > d_ini else None), None, 0
    else:
        d_fim, h_fim = _momento(ev, "end")
        minutos = int((datetime.combine(d_fim, h_fim or hora_t(0, 0))
                       - datetime.combine(d_ini, h_ini)).total_seconds() // 60)
        prazo, inicio, hora = d_ini, None, h_ini
        duracao = 0 if minutos in (0, DURACAO_PADRAO_MIN) else max(15, minutos)
    return {"titulo": titulo.strip() or "(Sem título)", "concluida": feita, "prazo": prazo, "inicio": inicio,
            "hora": hora, "duracao_min": duracao}


def _instante(texto: str | None) -> datetime | None:
    if not texto:
        return None
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass
class Resumo:
    eventos_lidos: int = 0
    enviados: int = 0
    atualizados: int = 0
    removidos: int = 0
    importados: int = 0          # eventos novos do calendário "Tarefas" que viraram tarefa
    alteradas_no_google: int = 0  # tarefas que mudaram porque você mexeu no evento
    avisos: list[str] = field(default_factory=list)
    erro: str = ""

    def total_mudancas(self) -> int:
        return (self.eventos_lidos + self.enviados + self.atualizados + self.removidos + self.importados
                + self.alteradas_no_google)


# ---------------------------------------------------------------- sincronização
class Google:
    """Fachada usada pela tela: `servico.google`."""

    def __init__(self, servico, transporte=transporte_padrao, cofre: Cofre | None = None):
        self.servico = servico
        self.banco = servico.banco
        self.cliente = ClienteGoogle(self.banco, transporte, cofre)

    # ---- estado
    @property
    def configurado(self) -> bool:
        return self.cliente.configurado

    @property
    def conectado(self) -> bool:
        return self.cliente.conectado

    @property
    def conta(self) -> str:
        return self.banco.meta("google_conta", "") or ""

    @property
    def enviar_tarefas(self) -> bool:
        return self.banco.meta("google_enviar", "0") == "1"

    def definir_enviar_tarefas(self, ligado: bool) -> None:
        self.banco.definir_meta("google_enviar", "1" if ligado else "0")

    def calendarios(self) -> list[dict]:
        return self.servico.assinaturas("google")

    def definir_calendario_ativo(self, assinatura_id: int, ativo: bool) -> None:
        self.banco.con.execute("UPDATE assinatura SET ativa=? WHERE id=?", (int(ativo), assinatura_id))
        if not ativo:       # desmarcar esquece os eventos e o ponto de sincronização
            self.banco.con.execute("DELETE FROM evento_externo WHERE assinatura_id=?", (assinatura_id,))
            self.banco.con.execute("UPDATE assinatura SET sync_token='', completa_em=NULL WHERE id=?",
                                   (assinatura_id,))
        self.banco.con.commit()

    def entrar(self, abrir=webbrowser.open, ao_abrir=None, transporte=None) -> None:
        """Login no navegador. Bloqueia até você aprovar (rode numa thread)."""
        if not self.cliente.configurado:
            raise ErroGoogle("Informe o Client ID e o Client secret do Google Cloud primeiro.")
        dados = login_pelo_navegador(self.cliente.client_id, self.cliente.client_secret, abrir=abrir,
                                     transporte=transporte or self.cliente.transporte, ao_abrir=ao_abrir)
        self.cliente.guardar_login(dados)
        self.banco.definir_meta("google_conta", "")

    def sair(self, apagar_eventos: bool = True) -> None:
        self.cliente.desconectar()
        self.definir_enviar_tarefas(False)
        con = self.banco.con
        if apagar_eventos:
            con.execute("DELETE FROM assinatura WHERE origem='google'")
            con.execute("DELETE FROM ligacao_google")
            for k in ("google_cal_tarefas", "google_sync_tarefas", "google_conta"):
                self.banco.definir_meta(k, "")
        con.commit()

    # ---- ciclo completo
    def sincronizar(self) -> Resumo:
        """Faz tudo: lista calendários, lê o que você marcou, devolve edições do Google para as tarefas e envia as
        tarefas. Bloqueia (rode numa thread; ver `sincronizar_arquivo`)."""
        r = Resumo()
        if not self.conectado:
            r.erro = "Conta do Google não conectada."
            return r
        try:
            self._atualizar_calendarios()
            if self.enviar_tarefas:
                self._garantir_calendario_tarefas()
                self._puxar_calendario_tarefas(r)
                self._enviar(r)
            for ass in self.calendarios():
                if ass["ativa"] and ass["ref"] != self.banco.meta("google_cal_tarefas", ""):
                    try:
                        self._puxar_assinatura(ass, r)
                    except SemAutorizacao:
                        raise
                    except ErroGoogle as e:          # um calendário com problema não derruba os outros
                        self._erro_assinatura(ass, e)
                        r.avisos.append(f"{ass['nome']}: {e}")
        except SemAutorizacao as e:
            r.erro = str(e)
        except ErroGoogle as e:
            r.erro = str(e)
        self.banco.definir_meta("google_ultima_sync", agora_utc().isoformat())
        self.banco.definir_meta("google_ultimo_erro", r.erro)
        return r

    # ---- calendários da conta
    def _atualizar_calendarios(self) -> None:
        con = self.banco.con
        existentes = {a["ref"]: a for a in self.calendarios()}
        vistos = set()
        for c in self.cliente.listar_calendarios():
            vistos.add(c["id"])
            nome = c.get("summaryOverride") or c.get("summary") or c["id"]
            cor = c.get("backgroundColor") or "#4dd0b1"
            if c.get("primary") and not self.conta:
                self.banco.definir_meta("google_conta", c["id"])
            if c["id"] in existentes:
                con.execute("UPDATE assinatura SET nome=?, cor=? WHERE id=?",
                            (nome, cor, existentes[c["id"]]["id"]))
            else:       # calendário novo começa desligado: você escolhe o que quer ver
                con.execute("INSERT INTO assinatura(nome, url, cor, origem, ref, ativa) VALUES (?,?,?,?,?,0)",
                            (nome, "google://" + c["id"], cor, "google", c["id"]))
        for ref, a in existentes.items():
            if ref not in vistos:
                con.execute("DELETE FROM assinatura WHERE id=?", (a["id"],))
        con.commit()

    # ---- Google -> app
    def _puxar_assinatura(self, ass: dict, r: Resumo) -> None:
        con = self.banco.con
        token = ass["sync_token"] or None
        completa = ass["completa_em"]
        if token and completa and (datetime.now() - datetime.fromisoformat(completa)).days >= RECARGA_COMPLETA_DIAS:
            token = None                    # de vez em quando refaz tudo, para a janela de datas acompanhar o tempo
        hoje = date.today()
        ini, fim = hoje - timedelta(days=JANELA_ANTES_DIAS), hoje + timedelta(days=JANELA_DEPOIS_DIAS)
        try:
            itens, novo = self.cliente.eventos(ass["ref"], token, ini, fim)
        except ErroGoogle as e:
            if e.status != 410 or token is None:
                raise
            token = None                    # o ponto de sincronização venceu: recomeça do zero
            itens, novo = self.cliente.eventos(ass["ref"], None, ini, fim)
        if token is None:
            con.execute("DELETE FROM evento_externo WHERE assinatura_id=?", (ass["id"],))
        for ev in itens:
            con.execute("DELETE FROM evento_externo WHERE assinatura_id=? AND uid=?", (ass["id"], ev.get("id", "")))
            linha = linha_do_evento(ev)
            if linha is None:
                continue
            con.execute(
                "INSERT INTO evento_externo(assinatura_id, uid, titulo, inicio, fim, dia_inteiro, regra, local, link)"
                " VALUES (?,?,?,?,?,?,NULL,?,?)",
                (ass["id"], linha["uid"], linha["titulo"], linha["inicio"], linha["fim"], linha["dia_inteiro"],
                 linha["local"], linha["link"]))
        r.eventos_lidos += len(itens)
        con.execute("UPDATE assinatura SET sync_token=?, ultima_sync=?, erro='', completa_em=? WHERE id=?",
                    (novo or "", agora_utc().isoformat(),
                     datetime.now().isoformat() if token is None else (completa or datetime.now().isoformat()),
                     ass["id"]))
        con.commit()

    def _erro_assinatura(self, ass: dict, e: ErroGoogle) -> None:
        self.banco.con.execute("UPDATE assinatura SET erro=? WHERE id=?", (str(e), ass["id"]))
        self.banco.con.commit()

    # ---- calendário "Tarefas"
    def _garantir_calendario_tarefas(self) -> str:
        atual = self.banco.meta("google_cal_tarefas", "") or ""
        if atual:
            return atual
        for a in self.calendarios():       # já existe um com esse nome? reaproveita (reinstalação)
            if a["nome"] == NOME_CALENDARIO_TAREFAS:
                self.banco.definir_meta("google_cal_tarefas", a["ref"])
                return a["ref"]
        novo = self.cliente.criar_calendario(NOME_CALENDARIO_TAREFAS)
        self.banco.definir_meta("google_cal_tarefas", novo["id"])
        self.banco.definir_meta("google_sync_tarefas", "")
        self._atualizar_calendarios()
        return novo["id"]

    def _ligacoes(self) -> dict[str, dict]:
        return {l["tarefa_uuid"]: dict(l) for l in self.banco.con.execute("SELECT * FROM ligacao_google")}

    def _salvar_ligacao(self, uuid: str, evento_id: str, corpo_hash: str, etag: str) -> None:
        self.banco.con.execute(
            "INSERT INTO ligacao_google(tarefa_uuid, evento_id, corpo_hash, etag) VALUES (?,?,?,?) "
            "ON CONFLICT(tarefa_uuid) DO UPDATE SET evento_id=excluded.evento_id, corpo_hash=excluded.corpo_hash, "
            "etag=excluded.etag", (uuid, evento_id, corpo_hash, etag))
        self.banco.con.commit()

    def _nome_da_lista(self, t: Tarefa, projetos: dict) -> str:
        p = projetos.get(t.projeto_id)
        return p.nome if p else ""

    def _tarefas_para_enviar(self) -> list[Tarefa]:
        projetos_ok = {p.id for p in self.banco.listar_projetos()}
        sql = "apagada_em IS NULL AND prazo IS NOT NULL AND pai_id IS NULL AND descartada_em IS NULL"
        return [t for t in self.banco.consultar(sql)
                if (t.projeto_id is None or t.projeto_id in projetos_ok)]

    def _enviar(self, r: Resumo) -> None:
        cal = self.banco.meta("google_cal_tarefas", "")
        projetos = {p.id: p for p in self.banco.listar_projetos()}
        ligacoes = self._ligacoes()
        atuais = set()
        for t in self._tarefas_para_enviar():
            atuais.add(t.uuid)
            corpo = corpo_evento(t, self._nome_da_lista(t, projetos))
            h = hash_corpo(corpo)
            lig = ligacoes.get(t.uuid)
            if lig is None or (lig["evento_id"] == "" and lig["corpo_hash"] != h):
                ev = self.cliente.inserir_evento(cal, corpo)
                self._salvar_ligacao(t.uuid, ev["id"], h, ev.get("etag", ""))
                r.enviados += 1
            elif lig["evento_id"] == "":
                continue                       # você apagou o evento no Google e a tarefa não mudou desde então
            elif lig["corpo_hash"] != h:
                try:
                    ev = self.cliente.alterar_evento(cal, lig["evento_id"], corpo)
                except ErroGoogle as e:
                    if e.status not in (404, 410):
                        raise
                    ev = self.cliente.inserir_evento(cal, corpo)       # o evento sumiu: recria
                self._salvar_ligacao(t.uuid, ev["id"], h, ev.get("etag", ""))
                r.atualizados += 1
        for uuid, lig in ligacoes.items():
            if uuid in atuais:
                continue
            if lig["evento_id"]:
                self.cliente.apagar_evento(cal, lig["evento_id"])
                r.removidos += 1
            self.banco.con.execute("DELETE FROM ligacao_google WHERE tarefa_uuid=?", (uuid,))
        self.banco.con.commit()

    def _puxar_calendario_tarefas(self, r: Resumo) -> None:
        """Edições feitas no Google nos eventos do calendário "Tarefas" voltam para as tarefas."""
        cal = self.banco.meta("google_cal_tarefas", "")
        token = self.banco.meta("google_sync_tarefas", "") or None
        try:
            itens, novo = self.cliente.eventos(cal, token)
        except ErroGoogle as e:
            if e.status != 410:
                raise
            itens, novo = self.cliente.eventos(cal, None)
        ligacoes = self._ligacoes()
        por_evento = {l["evento_id"]: u for u, l in ligacoes.items() if l["evento_id"]}
        projetos = {p.id: p for p in self.banco.listar_projetos()}
        for ev in itens:
            uuid = ((ev.get("extendedProperties") or {}).get("private") or {}).get("tarefa_uuid") \
                or por_evento.get(ev.get("id"))
            if ev.get("status") == "cancelled":
                lig = ligacoes.get(uuid or "")
                if lig and lig["evento_id"] == ev.get("id"):
                    t = self.banco.obter_tarefa_por_uuid(uuid)
                    h = hash_corpo(corpo_evento(t, self._nome_da_lista(t, projetos))) if t else lig["corpo_hash"]
                    self._salvar_ligacao(uuid, "", h, "")        # apagado no Google: não recria sozinho
                continue
            if "start" not in ev:
                continue
            lig = ligacoes.get(uuid or "")
            if lig is None:
                if uuid:
                    continue                                     # evento de uma tarefa que este aparelho não tem
                self._importar_evento(ev, projetos, r)
                continue
            if ev.get("etag") and ev.get("etag") == lig["etag"]:
                continue                                         # é só o eco do que nós mesmos enviamos
            t = self.banco.obter_tarefa_por_uuid(uuid)
            if t is None or t.apagada_em is not None:
                continue
            esperado = corpo_evento(t, self._nome_da_lista(t, projetos))
            m = mudancas_do_evento(ev)
            igual = (m["titulo"] == t.titulo and m["concluida"] == t.concluida and m["prazo"] == t.prazo
                     and m["hora"] == t.prazo_hora and (m["inicio"] or None) == (t.inicio or None))
            if igual:
                self._salvar_ligacao(uuid, ev["id"], lig["corpo_hash"], ev.get("etag", ""))
                continue
            atualizado_google = _instante(ev.get("updated"))
            t_atual = t.atualizada_em if t.atualizada_em.tzinfo else t.atualizada_em.replace(tzinfo=timezone.utc)
            if atualizado_google is not None and atualizado_google <= t_atual and lig["corpo_hash"] != hash_corpo(esperado):
                continue                                         # a tarefa é mais nova: ela vai sobrescrever o evento
            self._aplicar_na_tarefa(t, m)
            r.alteradas_no_google += 1
            novo_corpo = corpo_evento(self.banco.obter_tarefa(t.id), self._nome_da_lista(t, projetos))
            self._salvar_ligacao(uuid, ev["id"], hash_corpo(novo_corpo), ev.get("etag", ""))
        self.banco.definir_meta("google_sync_tarefas", novo or "")

    def _aplicar_na_tarefa(self, t: Tarefa, m: dict) -> None:
        t.titulo = m["titulo"]
        t.prazo, t.inicio, t.prazo_hora, t.duracao_min = m["prazo"], m["inicio"], m["hora"], m["duracao_min"]
        t = self.servico.salvar(t)
        if m["concluida"] != t.concluida:
            self.servico.alternar_conclusao(t.id)

    def _importar_evento(self, ev: dict, projetos: dict, r: Resumo) -> None:
        """Evento criado à mão no calendário "Tarefas" do Google vira tarefa (e passa a ser acompanhado)."""
        m = mudancas_do_evento(ev)
        t = Tarefa(titulo=m["titulo"], prazo=m["prazo"], prazo_hora=m["hora"], inicio=m["inicio"],
                   duracao_min=m["duracao_min"], ordem=self.banco.proxima_ordem())
        t = self.banco.salvar_tarefa(t)
        if m["concluida"]:
            self.servico.alternar_conclusao(t.id)
        t = self.banco.obter_tarefa(t.id)
        cal = self.banco.meta("google_cal_tarefas", "")
        corpo = corpo_evento(t, "")
        novo = self.cliente.alterar_evento(cal, ev["id"], {
            "extendedProperties": corpo["extendedProperties"]})
        self._salvar_ligacao(t.uuid, ev["id"], hash_corpo(corpo), novo.get("etag", ev.get("etag", "")))
        r.importados += 1


def sincronizar_arquivo(caminho: str, pasta_dados=None, transporte=transporte_padrao) -> Resumo:
    """Roda a sincronização numa conexão própria do banco (para usar numa thread sem travar a tela)."""
    from .db import Banco  # noqa: PLC0415
    from .servico import Servico  # noqa: PLC0415
    servico = Servico(Banco(caminho), pasta_dados=pasta_dados)
    try:
        g = Google(servico, transporte)
        return g.sincronizar()
    finally:
        servico.banco.fechar()
