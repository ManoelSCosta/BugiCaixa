"""Leitura e agrupamento de logs.

Reconhece os formatos mais comuns de log de aplicacao (Spring Boot / Logback /
Log4j, Python logging, .NET, nginx error, syslog, JSON por linha) sem
configuracao: basta a linha comecar com data/hora. Linhas que nao comecam com
data/hora (stack trace) sao anexadas ao evento anterior.

O arquivo e processado em fluxo: so os grupos de erro ficam na memoria.
"""

import gzip
import json
import re
from collections import Counter
from datetime import datetime

# --------------------------------------------------------------------------
# 1. LEITURA
# --------------------------------------------------------------------------

_FRACAO_TZ = r"(?:[.,](\d{1,9}))?(?:\s?(?:Z|[+-]\d{2}:?\d{2}))?"
TS_ISO_RE = re.compile(r"^\[?(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2}):(\d{2})" + _FRACAO_TZ + r"\]?")
TS_DMA_RE = re.compile(r"^\[?(\d{2})/(\d{2})/(\d{4})[ ,T]+(\d{2}):(\d{2}):(\d{2})" + _FRACAO_TZ + r"\]?")
TS_SYSLOG_RE = re.compile(r"^([A-Z][a-z]{2}) +(\d{1,2}) (\d{2}):(\d{2}):(\d{2})")
MESES = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}

NIVEL_RE = re.compile(
    r"(?<![\w.])(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|ERR|FATAL|SEVERE|CRITICAL|CRIT)(?![\w.])")
NIVEL_MIN_RE = re.compile(
    r"(?:\[|\blevel=|\blvl=)\"?(trace|debug|info|notice|warn|warning|error|err|fatal|severe|critical|crit)\"?\]?",
    re.I)
NIVEL_CANONICO = {
    "WARNING": "WARN", "NOTICE": "INFO", "ERR": "ERROR", "SEVERE": "ERROR",
    "CRITICAL": "FATAL", "CRIT": "FATAL",
}
# Depois do nivel: "[pid ---] [thread] logger : mensagem" ou "logger - mensagem"
ESTRUTURA_RE = re.compile(
    r"^\]?(?:\s+\d+\s+---)?(?:\s+\[[^\]]*\])*\s+(?P<logger>[\w$\[\]<>/-]*\.[\w$.\[\]<>/-]+)"
    r"\s+(?:[:\-]|---)(?:\s+(?P<msg>.*))?$")

LIMITE_TRACE = 200
JANELA_NIVEL = 100


def _fracao(txt):
    return int(txt[:6].ljust(6, "0")) if txt else 0


def _inicio_ts(linha):
    """(datetime, resto_da_linha) se a linha comeca com data/hora; senao None."""
    c = linha[:1]
    if not (c.isdigit() or c == "[" or c.isupper()):
        return None
    try:
        m = TS_ISO_RE.match(linha)
        if m:
            a, me, d, h, mi, s, fr = m.groups()
            return datetime(int(a), int(me), int(d), int(h), int(mi), int(s), _fracao(fr)), linha[m.end():]
        m = TS_DMA_RE.match(linha)
        if m:
            d, me, a, h, mi, s, fr = m.groups()
            return datetime(int(a), int(me), int(d), int(h), int(mi), int(s), _fracao(fr)), linha[m.end():]
        m = TS_SYSLOG_RE.match(linha)
        if m and m.group(1) in MESES:
            me, d, h, mi, s = m.groups()
            return (datetime(datetime.now().year, MESES[me], int(d), int(h), int(mi), int(s)),
                    linha[m.end():])
    except ValueError:
        pass
    return None


def _nivel(txt):
    n = (txt or "").upper()
    return NIVEL_CANONICO.get(n, n)


class Evento:
    __slots__ = ("ts", "nivel", "logger", "msg", "trace", "arquivo", "linha")

    def __init__(self, ts, nivel, logger, msg, arquivo, linha):
        self.ts = ts
        self.nivel = nivel
        self.logger = logger or ""
        self.msg = msg or ""
        self.trace = []
        self.arquivo = arquivo
        self.linha = linha

    @property
    def trace_txt(self):
        return "\n".join(self.trace)


def _primeiro(d, chaves):
    for k in chaves:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _evento_json(linha, arquivo, n):
    """Log estruturado, um objeto JSON por linha (Logstash, ECS, pino, zap...)."""
    try:
        d = json.loads(linha)
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    msg = _primeiro(d, ("message", "msg", "log", "text"))
    nivel = _primeiro(d, ("level", "severity", "log.level", "levelname", "lvl"))
    if msg is None and nivel is None:
        return None
    bruto = _primeiro(d, ("@timestamp", "timestamp", "time", "ts", "datetime", "date"))
    ts = None
    if isinstance(bruto, (int, float)):
        try:
            ts = datetime.fromtimestamp(bruto / 1000.0 if bruto > 1e11 else bruto)
        except (ValueError, OverflowError, OSError):
            ts = None
    elif isinstance(bruto, str):
        ini = _inicio_ts(bruto)
        ts = ini[0] if ini else None
    ev = Evento(ts, _nivel(str(nivel)) if nivel is not None else "",
                str(_primeiro(d, ("logger_name", "logger", "name", "log.logger")) or ""),
                str(msg if msg is not None else ""), arquivo, n)
    pilha = _primeiro(d, ("stack_trace", "stacktrace", "exception", "exc_info", "stack", "error.stack_trace"))
    if pilha:
        if not isinstance(pilha, str):
            pilha = json.dumps(pilha, ensure_ascii=False)
        ev.trace = pilha.splitlines()[:LIMITE_TRACE]
    return ev


def interpretar_linha(linha, arquivo="", n=0):
    """Evento se a linha inicia um registro de log; None se e continuacao."""
    if linha[:1] == "{":
        return _evento_json(linha, arquivo, n)
    ini = _inicio_ts(linha)
    if ini is None:
        return None
    ts, resto = ini
    cabeca = resto[:JANELA_NIVEL]
    m = NIVEL_RE.search(cabeca) or NIVEL_MIN_RE.search(cabeca)
    if not m:
        return Evento(ts, "", "", resto.strip(" \t-:|"), arquivo, n)
    depois = resto[m.end():]
    e = ESTRUTURA_RE.match(depois)
    if e:
        return Evento(ts, _nivel(m.group(1)), e.group("logger"), e.group("msg") or "", arquivo, n)
    return Evento(ts, _nivel(m.group(1)), "", depois.lstrip("] \t-:|"), arquivo, n)


def _abrir(caminho):
    with open(caminho, "rb") as f:
        compactado = f.read(2) == b"\x1f\x8b"
    if compactado:
        return gzip.open(caminho, "rt", encoding="utf-8", errors="replace")
    return open(caminho, "r", encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# 2. NORMALIZACAO / ASSINATURA
# --------------------------------------------------------------------------

SUBS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?\b"), "<DATA>"),
    (re.compile(r"\b\d{2}/\d{2}/\d{4}\b"), "<DATA>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "<EMAIL>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IP>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"@[0-9a-f]{5,16}\b"), "@<HEX>"),
    (re.compile(r"'[^']{0,120}'"), "'<VAL>'"),
    (re.compile(r'"[^"]{0,120}"'), '"<VAL>"'),
    (re.compile(r"\b\d+([.,]\d+)?\b"), "<N>"),
    (re.compile(r"\s+"), " "),
]

EXC_RE = re.compile(r"\b((?:[a-zA-Z_]\w*\.)+[A-Z]\w*(?:Exception|Error|Throwable))\b")
FRAME_RE = re.compile(r"^\s*at\s+([\w$.]+)\.([\w$<>]+)\(([^)]*)\)")
CAUSED_RE = re.compile(r"^\s*Caused by:\s*(\S+)")
PY_FRAME_RE = re.compile(r'^\s*File "([^"]+)", line (\d+), in (\S+)')
PY_EXC_RE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt))(?::|\s*$)")

# Erro real escondido em registro INFO: log de acesso que grava toda chamada
# HTTP em INFO, independentemente do status.
RESPONSE_ERRO_RE = re.compile(r"\|\s*Response:\s*(5\d\d)\b")
REQUEST_RE = re.compile(r"\|\s*Request:\s*(\S+)\s+(\S+)")

PACOTES_FRAMEWORK = (
    "java.", "javax.", "jakarta.", "sun.", "jdk.", "org.springframework.",
    "org.apache.", "org.hibernate.", "org.eclipse.", "ch.qos.", "org.slf4j.",
    "com.zaxxer.", "io.netty.", "org.glassfish.", "reactor.", "com.fasterxml.",
    "kotlin.", "kotlinx.", "scala.", "System.", "Microsoft.",
)
PASTAS_BIBLIOTECA_PY = ("site-packages", "dist-packages", "/lib/python", "\\lib\\")

NIVEIS_PROBLEMA = {"ERROR", "FATAL"}


def normalizar(texto):
    t = texto.strip()[:2000]
    for rgx, rep in SUBS:
        t = rgx.sub(rep, t)
    return t.strip()[:300]


def _traceback_python(evento):
    return any(l.startswith("Traceback (most recent call last)") for l in evento.trace[:5]) \
        or "Traceback (most recent call last)" in evento.msg


def primeiro_frame_da_app(evento):
    """Ponto do codigo da aplicacao (nao de framework) onde o erro estourou."""
    if _traceback_python(evento):
        achado = None
        for linha in evento.trace:
            m = PY_FRAME_RE.match(linha)
            if m and not any(p in m.group(1) for p in PASTAS_BIBLIOTECA_PY):
                arq = m.group(1).replace("\\", "/").rsplit("/", 1)[-1]
                achado = "%s (%s:%s)" % (m.group(3), arq, m.group(2))
        return achado  # em Python o frame mais interno vem por ultimo
    for linha in evento.trace:
        m = FRAME_RE.match(linha)
        if m and not m.group(1).startswith(PACOTES_FRAMEWORK):
            return "%s.%s(%s)" % (m.group(1), m.group(2), m.group(3))
    return None


def causa_raiz(evento):
    ultima = None
    for linha in evento.trace:
        m = CAUSED_RE.match(linha)
        if m:
            ultima = m.group(1).rstrip(":")
    return ultima


def excecao_do_evento(evento):
    """Excecao de topo: mais estavel que a causa raiz, que varia com a
    profundidade do trace capturado no arquivo."""
    m = EXC_RE.search(evento.msg)
    if m:
        return m.group(1)
    for linha in evento.trace[:3]:
        if CAUSED_RE.match(linha):
            break
        m = EXC_RE.search(linha)
        if m:
            return m.group(1)
    if _traceback_python(evento):
        for linha in reversed(evento.trace):
            m = PY_EXC_RE.match(linha)
            if m:
                return m.group(1)
    return causa_raiz(evento)


def resposta_http_erro(evento):
    m = RESPONSE_ERRO_RE.search(evento.msg) or RESPONSE_ERRO_RE.search(evento.trace_txt)
    return m.group(1) if m else None


def requisicao_do_evento(evento):
    m = REQUEST_RE.search(evento.msg) or REQUEST_RE.search(evento.trace_txt)
    return "%s %s" % (m.group(1), m.group(2)) if m else None


def possui_indicio_de_erro(evento):
    """Erro real dentro de um evento que a aplicacao registrou como INFO."""
    return bool(excecao_do_evento(evento)) or bool(resposta_http_erro(evento))


def assinatura(evento):
    """Identidade estavel do problema, ignorando valores variaveis."""
    exc = excecao_do_evento(evento)
    frame = primeiro_frame_da_app(evento)
    if exc and frame:
        return "%s @ %s" % (exc.split(".")[-1], frame)
    if exc:
        return "%s :: %s" % (exc.split(".")[-1], normalizar(evento.msg)[:120])
    http_erro = resposta_http_erro(evento)
    if http_erro:
        req = requisicao_do_evento(evento)
        if req:
            return "HTTP %s @ %s" % (http_erro, req)
        return "HTTP %s :: %s" % (http_erro, normalizar(evento.msg)[:120])
    if evento.logger:
        return "%s :: %s" % (evento.logger.split(".")[-1], normalizar(evento.msg)[:160])
    return normalizar(evento.msg)[:180] or "(mensagem vazia)"


# --------------------------------------------------------------------------
# 3. AGREGACAO
# --------------------------------------------------------------------------

class Grupo:
    def __init__(self, assinatura_):
        self.assinatura = assinatura_
        self.ocorrencias = 0
        self.reclassificados = 0
        self.primeira = None
        self.ultima = None
        self.exemplo = None
        self.arquivos = Counter()
        self.por_hora = Counter()  # chave "AAAA-MM-DD HH"

    def add(self, ev, reclassificado):
        self.ocorrencias += 1
        if reclassificado:
            self.reclassificados += 1
        self.arquivos[ev.arquivo] += 1
        if ev.ts:
            if self.primeira is None or ev.ts < self.primeira:
                self.primeira = ev.ts
            if self.ultima is None or ev.ts > self.ultima:
                self.ultima = ev.ts
            self.por_hora[ev.ts.strftime("%Y-%m-%d %H")] += 1
        if self.exemplo is None or len(ev.trace) > len(self.exemplo.trace):
            self.exemplo = ev


class Analise:
    """Acumula o resultado de um ou mais arquivos de log."""

    def __init__(self):
        self.grupos = {}          # (nivel_efetivo, assinatura) -> Grupo
        self.niveis = Counter()   # nivel declarado -> eventos
        self.eventos = 0
        self.linhas = 0
        self.linhas_soltas = 0    # linhas antes do primeiro registro reconhecido
        self.inicio = None
        self.fim = None
        self.arquivos = []        # (nome, tamanho, eventos)

    def adicionar_arquivo(self, caminho, nome, tamanho=0):
        antes = self.eventos
        atual = None
        with _abrir(caminho) as f:
            for n, bruta in enumerate(f, 1):
                linha = bruta.rstrip("\r\n")
                if not linha.strip():
                    continue
                self.linhas += 1
                ev = interpretar_linha(linha, nome, n)
                if ev is not None:
                    if atual is not None:
                        self._registrar(atual)
                    atual = ev
                elif atual is None:
                    self.linhas_soltas += 1
                elif len(atual.trace) < LIMITE_TRACE:
                    atual.trace.append(linha[:2000])
        if atual is not None:
            self._registrar(atual)
        self.arquivos.append((nome, tamanho, self.eventos - antes))

    def _registrar(self, ev):
        self.eventos += 1
        self.niveis[ev.nivel or "(sem nível)"] += 1
        if ev.ts:
            if self.inicio is None or ev.ts < self.inicio:
                self.inicio = ev.ts
            if self.fim is None or ev.ts > self.fim:
                self.fim = ev.ts
        if ev.nivel in NIVEIS_PROBLEMA:
            efetivo, reclass = "ERROR", False
        elif ev.nivel == "WARN":
            # WARN fica como a aplicacao decidiu, mesmo citando excecao.
            efetivo, reclass = "WARN", False
        elif possui_indicio_de_erro(ev):
            efetivo, reclass = "ERROR", True
        else:
            return
        chave = (efetivo, assinatura(ev))
        g = self.grupos.get(chave)
        if g is None:
            g = self.grupos[chave] = Grupo(chave[1])
        g.add(ev, reclass)

    def do_nivel(self, nivel):
        """Grupos de um nivel, do mais frequente para o menos."""
        return sorted(((k, g) for k, g in self.grupos.items() if k[0] == nivel),
                      key=lambda kv: (-kv[1].ocorrencias, kv[0][1]))

    def contagens(self):
        return {"%s|%s" % k: g.ocorrencias for k, g in self.grupos.items()}
