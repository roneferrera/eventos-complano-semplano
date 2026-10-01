import os
import re
import io
import base64
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
import pandas as pd
import streamlit as st

# ==============================
# VERSÃO
# ==============================
VERSAO = "V1.8"

# ==============================
# EXIBIÇÃO
# True  -> mostra os modelos "Com plano de saúde" na barra lateral e nas instruções
# False -> oculta (a conversão dessas planilhas continua funcionando)
# ==============================
EXIBIR_MODELOS_PLANO = True

# ==============================
# LEIAUTE DO ARQUIVO DE ALOCAÇÃO
# Ordem: Código Empresa <TAB> Código Empregado <TAB> Código Serviço <TAB> Data da Troca
# ==============================
ALOC_SEPARADOR   = "\t"   # tabulação
ALOC_MAX_DIGITOS = 7
ALOC_TABELA      = "FOTROCAS_SERVICOS_IMPORTACAO"

# ==============================
# REGISTRO 11 — DIAS DE FALTAS / REEMBOLSO DE FALTAS
# Leiaute Domínio: 001-002 "11" | 003-010 Data AAAAMMDD | 011-011 Tipo (1-Normal, 2-DSR)
# Na célula do evento: datas DD/MM/AAAA separadas por ';' (ou quebra de linha / '|')
# Indicador DSR antes ou depois da data -> tipo 2
# Válido para TODOS os modelos
# ==============================
FALTA_SEPARADOR   = ";"
FALTA_TIPO_NORMAL = "1"
FALTA_TIPO_DSR    = "2"
NOMES_TIPO_FALTA  = {FALTA_TIPO_NORMAL: "Normal", FALTA_TIPO_DSR: "DSR"}

INDICADORES_DSR = {
    "dsr", "d", "descanso", "descansosemanal", "descansosemanalremunerado",
}
INDICADORES_NORMAL = {"", "n", "normal"}

# Células maiores que isso não são consideradas cabeçalho
LIMITE_CABECALHO = 40

# ==============================
# MODELOS DE PLANILHA (Leiaute 1 — horizontal)
# chave: (tem_plano, tem_servico)
# ==============================
MODELOS = {
    (False, False): "Importação de Eventos - Sem plano de saúde",
    (True,  False): "Importação de Eventos - Com plano de saúde",
    (False, True):  "Importação de Eventos - Serviço",
    (True,  True):  "Importação de Eventos - Com plano de saúde e serviço",
}

# (rótulo, arquivo base64 na pasta do app, nome do .bgr baixado, key, usa plano de saúde)
MODELOS_BGR = [
    ("Sem plano de saúde",           "bgr_base64_sem_plano.txt",
     "Importação de Eventos - Sem plano de saúde.bgr",           "btn_bgr_sem_plano",         False),
    ("Com plano de saúde",           "bgr_base64_com_plano.txt",
     "Importação de Eventos - Com plano de saúde.bgr",           "btn_bgr_com_plano",         True),
    ("Serviço",                      "bgr_base64_com_servico.txt",
     "Importação de Eventos - Serviço.bgr",                      "btn_bgr_servico",           False),
    ("Com plano de saúde e serviço", "bgr_base64_com_plano_servico.txt",
     "Importação de Eventos - Com plano de saúde e serviço.bgr", "btn_bgr_com_plano_servico", True),
]


# ==============================
# TEMA TR
# ==============================
def apply_tr_theme():
    st.markdown("""
        <style>
        html, body, [class*="css"] {
            font-family: 'Segoe UI', 'Arial', sans-serif;
            color: #444444;
        }
        h1, h2, h3 { color: #FF8000; font-weight: 700; }
        section[data-testid="stSidebar"] { background-color: #444444; color: #FFFFFF; }
        section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
        .stButton > button {
            background-color: #FF8000; color: #FFFFFF; border: none;
            border-radius: 4px; font-weight: bold;
        }
        .stButton > button:hover { background-color: #D64001; color: #FFFFFF; }
        .stDownloadButton > button {
            background-color: #FF8000; color: #FFFFFF; border: none;
            border-radius: 4px; font-weight: bold;
        }
        .stDownloadButton > button:hover { background-color: #D64001; color: #FFFFFF; }
        hr { border-color: #FF8000; }
        [data-testid="metric-container"] {
            background-color: #E9E9E9; border-left: 4px solid #FF8000;
            border-radius: 4px; padding: 10px;
        }
        .instrucoes-box {
            background-color: #E9E9E9; border-left: 4px solid #FF8000;
            border-radius: 4px; padding: 16px 20px; margin: 12px 0;
            color: #444444; font-family: 'Segoe UI', Arial, sans-serif;
        }
        .instrucoes-box h4 { color: #FF8000; margin-top: 16px; margin-bottom: 6px; }
        .instrucoes-box h4:first-child { margin-top: 0; }
        .instrucoes-box h5 { color: #444444; margin-top: 12px; margin-bottom: 4px; }
        .instrucoes-box table { border-collapse: collapse; width: 100%; margin: 6px 0 10px 0; }
        .instrucoes-box th, .instrucoes-box td {
            border: 1px solid #CCCCCC; padding: 6px 8px; text-align: left; vertical-align: top;
        }
        .instrucoes-box th { background-color: #FF8000; color: #FFFFFF; }
        .instrucoes-box details {
            background-color: #F5F5F5; border: 1px dashed #AAAAAA;
            border-radius: 4px; padding: 8px 12px; margin-top: 10px;
        }
        .instrucoes-box summary { cursor: pointer; font-weight: bold; color: #444444; }
        </style>
    """, unsafe_allow_html=True)


# ==============================
# CARREGAMENTO DOS MODELOS .BGR
# ==============================
def carregar_bgr_bytes(nome_arquivo_b64: str):
    caminho = os.path.join(os.path.dirname(__file__), nome_arquivo_b64)
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            b64 = f.read().strip()
        b64 = "".join(b64.split())
        return base64.b64decode(b64)
    except Exception:
        return None


# ==============================
# UTILITÁRIOS
# ==============================
_INVISIVEIS = {ord(c): None for c in "\u200b\u200c\u200d\u2060\ufeff\u00ad"}
_ESPACOS    = {ord(c): " " for c in "\u00a0\u202f\u2007\u2009\u200a\t"}


def limpar_invisiveis(s):
    return str(s).translate(_INVISIVEIS).translate(_ESPACOS).replace("\uff1b", ";")


def texto(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    s = limpar_invisiveis(v).strip()
    return "" if s.lower() == "nan" else s


def so_numeros(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return re.sub(r"\D", "", str(v))


def cod_num(v):
    """Código numérico tolerante a float do Excel (ex.: 2.0 -> '2')."""
    if isinstance(v, float) and not pd.isna(v) and v.is_integer():
        return str(int(v))
    return so_numeros(v)


def normalizar(v):
    s = texto(v).lower().strip()
    mapa = {
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e",
        "í": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for a, b in mapa.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s)


def zfill_num(v, tamanho):
    n = so_numeros(v)
    return (n or "0").zfill(tamanho)


def competencia_yyyymm(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    if isinstance(v, datetime):
        return f"{v.year:04d}{v.month:02d}"
    s = texto(v)
    if not s:
        return ""
    try:
        dt = pd.to_datetime(s, errors="raise")
        return f"{dt.year:04d}{dt.month:02d}"
    except Exception:
        pass
    nums = so_numeros(s)
    if len(nums) == 6:
        mm, yyyy = nums[:2], nums[2:]
        if mm.isdigit() and 1 <= int(mm) <= 12:
            return f"{yyyy}{mm}"
    if len(nums) >= 6:
        yyyy, mm = nums[:4], nums[4:6]
        if yyyy.isdigit() and mm.isdigit() and 1 <= int(mm) <= 12:
            return f"{yyyy}{mm}"
    return ""


def parse_data(v):
    """
    Converte a célula 'Data da Troca' em date.
    Retorna None se vazia. Lança ValueError se inválida.
    """
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, (datetime, date)):
        return date(v.year, v.month, v.day)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 1 <= v <= 2958465:
            d = datetime(1899, 12, 30) + timedelta(days=int(v))
            return d.date()
        raise ValueError("data inválida")
    s = texto(v)
    if not s:
        return None
    if s.isdigit() and len(s) == 5:
        d = datetime(1899, 12, 30) + timedelta(days=int(s))
        return d.date()
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})(?:\s+.*)?", s)
    if m:
        d, mth, y = map(int, m.groups())
        return date(y, mth, d)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", s)
    if m:
        y, mth, d = map(int, m.groups())
        return date(y, mth, d)
    raise ValueError("data inválida")


# ==============================
# FALTAS — REGISTRO 11 (todos os modelos)
# ==============================
_RE_DATA_FALTA = re.compile(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})")
_RE_SEP_FALTA  = re.compile(r"[;\n\r|]+")


def _tipo_por_indicador(parte, resto):
    """Define o tipo da falta pelo texto que sobra ao redor da data."""
    resto_norm = normalizar(resto)
    if re.search(r"\d", resto_norm):
        raise ValueError(f"'{parte}' contém números além da data")
    indicador = re.sub(r"[^a-z]", "", resto_norm)      # 'd.s.r.' / '(dsr)' -> 'dsr'
    if indicador in INDICADORES_DSR:
        return FALTA_TIPO_DSR
    if indicador in INDICADORES_NORMAL:
        return FALTA_TIPO_NORMAL
    raise ValueError(
        f"indicador '{resto_norm.strip()}' em '{parte}' não reconhecido "
        f"(escreva DSR para falta de DSR ou deixe somente a data para Normal)"
    )


def extrair_datas_falta(v):
    """
    Lê a célula de um evento e verifica se contém datas de falta/reembolso.
    - None  -> célula sem datas (valor numérico comum).
    - lista [(date, tipo)] -> uma entrada por data.
    - ValueError -> conteúdo inválido (nunca assume Normal silenciosamente).
    """
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, (datetime, date)):                 # data única convertida pelo Excel
        return [(date(v.year, v.month, v.day), FALTA_TIPO_NORMAL)]

    s = texto(v)
    if not s:
        return None
    if not _RE_DATA_FALTA.search(s):
        if "dsr" in re.sub(r"[^a-z]", "", normalizar(s)):
            raise ValueError(f"'{s}' indica DSR, mas não contém data (use DD/MM/AAAA DSR)")
        return None

    itens = []
    for parte in _RE_SEP_FALTA.split(s):
        parte = parte.strip()
        if not parte:
            continue
        datas = list(_RE_DATA_FALTA.finditer(parte))
        if not datas:
            raise ValueError(
                f"'{parte}' não contém uma data válida "
                f"(use DD/MM/AAAA separadas por '{FALTA_SEPARADOR}')"
            )
        if len(datas) > 1:
            raise ValueError(
                f"'{parte}' contém mais de uma data — separe as datas com '{FALTA_SEPARADOR}'"
            )
        m = datas[0]
        d, mth, y = map(int, m.groups())
        try:
            dt = date(y, mth, d)
        except ValueError:
            raise ValueError(f"'{m.group(0)}' não é uma data existente")
        resto = parte[:m.start()] + " " + parte[m.end():]
        tipo = _tipo_por_indicador(parte, resto)
        itens.append((dt, tipo))
    return itens or None


def descrever_faltas(faltas):
    return ", ".join(
        f"{dt.strftime('%d/%m/%Y')} ({NOMES_TIPO_FALTA[t]})" for dt, t in faltas
    )


def contar_dsr(faltas):
    return sum(1 for _, t in faltas if t == FALTA_TIPO_DSR)


def validar_faltas(faltas, vistas, linha_excel, cod_evt, cod_emp, competencia, avisos):
    """Datas repetidas -> erro. Datas após a competência -> aviso."""
    erros = []
    posteriores = []
    for dt_f, _ in faltas:
        if dt_f in vistas:
            erros.append(
                f"Linha {linha_excel}, evento {cod_evt}: data de falta "
                f"{dt_f.strftime('%d/%m/%Y')} informada mais de uma vez para o "
                f"empregado {cod_emp.lstrip('0')}."
            )
        vistas.add(dt_f)
        if competencia and (dt_f.year * 100 + dt_f.month) > int(competencia):
            posteriores.append(dt_f.strftime("%d/%m/%Y"))
    if posteriores:
        avisos.append(
            f"AVISO linha {linha_excel}, evento {cod_evt}: data(s) de falta posterior(es) "
            f"à competência {competencia[4:]}/{competencia[:4]}: {', '.join(posteriores)}."
        )
    return erros


def montar_registros_falta(layout, faltas):
    """Um Registro 11 para cada data informada."""
    return [
        montar_registro(layout, "11", {
            "data_falta": dt_f.strftime("%Y%m%d"),
            "tipo_falta": tipo,
        })
        for dt_f, tipo in faltas
    ]


def eh_sim(v):
    return normalizar(v) in ("sim", "s")


def linha_vazia(valores):
    return all(normalizar(x) == "" for x in valores)


def valor_para_layout(v, tamanho=9):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    if isinstance(v, (int, float)):
        dec = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return str(int(dec * 100)).zfill(tamanho)
    s = texto(v).strip()
    if not s:
        return ""
    try:
        s_norm = s.replace(".", "").replace(",", ".") if "," in s else s
        dec = Decimal(s_norm).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return str(int(dec * 100)).zfill(tamanho)
    except (InvalidOperation, ValueError):
        nums = re.sub(r"[^0-9]", "", s)
        return nums.zfill(tamanho) if nums else ""


# ==============================
# LEIAUTES
# ==============================
_REG_10 = [
    ("fixo",        2,  "10"),
    ("empregado",  10),
    ("competencia", 6),
    ("rubrica",     9),
    ("tpcalc",      2),
    ("valor",       9),
    ("empresa",    10),
]

_REG_11 = [
    ("fixo",        2, "11"),
    ("data_falta",  8),        # AAAAMMDD
    ("tipo_falta",  1),        # 1-Normal | 2-DSR
]

LEIAUTES = {
    "importacao_arquivo_texto_lancamentos": {
        "nome": "Importação Arquivo Texto | De Lançamentos",
        "registros": {
            "10": _REG_10,
            "11": _REG_11,
            "20": [
                ("fixo",            2, "20"),
                ("cnpj_operadora", 14),
            ],
            "25": [
                ("fixo",                2, "25"),
                ("tipo_beneficiario",   1),
                ("codigo_beneficiario", 10),
                ("valor",               9),
            ],
            "40": [
                ("fixo",     2, "40"),
                ("servico", 10),
                ("rubrica",  9),
                ("valor",    9),
            ],
        },
    },
    "relacao_valores_vertical": {
        "nome": "Relação de Valores Para Folha de Pagamento V2 | Vertical",
        "registros": {
            "10": _REG_10,
            "11": _REG_11,
        },
    },
}


# ==============================
# DETECÇÃO DE LEIAUTE
# ==============================
def detectar_leiaute(df):
    for i in range(len(df) - 1):
        linha_a = [normalizar(x) for x in df.iloc[i].tolist()]
        linha_b = [normalizar(x) for x in df.iloc[i + 1].tolist()]
        combinadas = [
            f"{a} {b}".strip()
            for a, b in zip(linha_a, linha_b)
            if len(a) <= LIMITE_CABECALHO and len(b) <= LIMITE_CABECALHO
        ]
        tem_codigo_rubrica = any("codigo rubrica" in c for c in combinadas)
        tem_referencia     = any(
            "referencia valor" in c or "referencia" in c or
            c.strip() in ("referencia", "valor")
            for c in combinadas
        )
        if tem_codigo_rubrica and tem_referencia:
            return "relacao_valores_vertical"
    return "importacao_arquivo_texto_lancamentos"


# ==============================
# UTILITÁRIOS DE LAYOUT
# ==============================
def ajustar_campo_layout(nome, valor, tamanho):
    valor = "" if valor is None else str(valor)
    if nome in ("empregado", "empresa", "codigo_beneficiario", "servico"):
        return zfill_num(valor, tamanho)
    if nome in ("rubrica", "tpcalc", "cnpj_operadora", "competencia", "valor",
                "data_falta", "tipo_falta"):
        return so_numeros(valor).zfill(tamanho)
    return texto(valor)[:tamanho].ljust(tamanho)


def montar_registro(layout, tipo_registro, dados):
    if tipo_registro not in layout["registros"]:
        raise ValueError(f"Registro {tipo_registro} não definido no leiaute.")
    partes = []
    for campo in layout["registros"][tipo_registro]:
        nome, tamanho = campo[0], campo[1]
        if nome == "fixo":
            partes.append(str(campo[2]).zfill(tamanho))
        else:
            partes.append(ajustar_campo_layout(nome, dados.get(nome, ""), tamanho))
    return "".join(partes)


# ==============================
# LEITURA EXCEL (.xlsx e .xls)
# ==============================
def carregar_excel(arquivo_bytes):
    try:
        df = pd.read_excel(io.BytesIO(arquivo_bytes), sheet_name=0,
                           header=None, dtype=object)
    except Exception:
        df = pd.read_excel(io.BytesIO(arquivo_bytes), sheet_name=0,
                           header=None, dtype=object, engine="xlrd")
    return df.fillna("")


# ==============================
# METADADOS
# ==============================
def localizar_metadados(df):
    cod_empresa = competencia = ""
    for i in range(len(df)):
        row = df.iloc[i].tolist()
        row_norm = [normalizar(x) for x in row]
        for j, cel in enumerate(row_norm):
            if cel in ("codigo empresa:", "codigo empresa"):
                for k in range(j + 1, len(row)):
                    num = so_numeros(row[k])
                    if num:
                        cod_empresa = num.zfill(10)
                        break
            if cel in ("competencia:", "competencia"):
                for k in range(j + 1, len(row)):
                    comp = competencia_yyyymm(row[k])
                    if comp:
                        competencia = comp
                        break
    return cod_empresa, competencia


# ==============================
# LEIAUTE 1 — funções exclusivas
# ==============================
def localizar_estrutura(df):
    cab1 = cab2 = linha_plano = linha_cnpj = linha_dados = None
    for i in range(len(df)):
        row = [normalizar(x) for x in df.iloc[i].tolist()]
        celulas = [c for c in row if c and len(c) <= LIMITE_CABECALHO]

        if cab1 is None:
            if any(c.startswith("tipo de") for c in celulas) and \
               any(c.startswith("codigo") for c in celulas):
                cab1 = i
                if i + 1 < len(df):
                    cab2 = i + 1
            continue

        if linha_plano is None and any("evento de plano de saude" in c for c in celulas):
            linha_plano = i
            continue
        if linha_cnpj is None and any("cnpj da operadora de plano de saude" in c for c in celulas):
            linha_cnpj = i
            continue

    if cab2 is not None:
        for i in range(cab2 + 1, len(df)):
            row = df.iloc[i].tolist()
            v0 = so_numeros(row[0]) if len(row) > 0 else ""
            v1 = so_numeros(row[1]) if len(row) > 1 else ""
            v2 = so_numeros(row[2]) if len(row) > 2 else ""
            if v0 and (v1 or v2):
                linha_dados = i
                break
    return cab1, cab2, linha_plano, linha_cnpj, linha_dados


_ALVOS_SERVICO = ("servico", "tomador", "obra")


def _primeiro_termo(b):
    return b.split("/")[0].strip()


def _eh_col_codigo_servico(a, b, comb):
    return (
        comb.startswith(("codigo servico", "codigo do servico",
                         "codigo tomador", "codigo obra"))
        or (a == "codigo" and _primeiro_termo(b) in _ALVOS_SERVICO)
    )


def _eh_col_descricao_servico(a, b, comb):
    return (
        comb.startswith(("descricao servico", "descricao do servico",
                         "nome do servico", "nome servico",
                         "descricao tomador", "descricao obra"))
        or (a in ("descricao", "nome do", "nome") and _primeiro_termo(b) in _ALVOS_SERVICO)
    )


def detectar_colunas(df, cab1, cab2):
    linha1 = [texto(x) for x in df.iloc[cab1].tolist()]
    linha2 = [texto(x) for x in df.iloc[cab2].tolist()]
    col_tipo = col_emp = col_dep = col_nome = None
    col_serv = col_desc_serv = col_data = None
    eventos = {}
    for col in range(len(linha1)):
        a = normalizar(linha1[col])
        b = normalizar(linha2[col])
        if len(a) > LIMITE_CABECALHO or len(b) > LIMITE_CABECALHO:
            continue
        combinado = f"{a} {b}".strip()

        if col_tipo is None and (
            "tipo de calculo" in combinado or (a == "tipo de" and b == "calculo")
        ):
            col_tipo = col; continue
        if col_emp is None and (
            "codigo empregado" in combinado or "codigo folha" in combinado or
            (a == "codigo" and b in ("empregado", "folha"))
        ):
            col_emp = col; continue
        if col_dep is None and (
            "codigo dependente" in combinado or (a == "codigo" and b == "dependente")
        ):
            col_dep = col; continue
        if col_nome is None and (
            "nome dos colaboradores" in combinado or
            (a == "nome dos" and b == "colaboradores")
        ):
            col_nome = col; continue
        if col_serv is None and _eh_col_codigo_servico(a, b, combinado):
            col_serv = col; continue
        if col_desc_serv is None and _eh_col_descricao_servico(a, b, combinado):
            col_desc_serv = col; continue
        if col_data is None and (
            "data da troca" in combinado or combinado == "data troca" or
            (a == "data da" and b == "troca")
        ):
            col_data = col; continue

    col_tipo = col_tipo if col_tipo is not None else 0
    col_emp  = col_emp  if col_emp  is not None else 1
    if col_nome is None:
        col_nome = (col_dep if col_dep is not None else col_emp) + 1

    inicio_eventos = max(col_nome + 1, 3)
    for col in range(inicio_eventos, len(linha2)):
        cod_evt = so_numeros(linha2[col])
        if cod_evt and len(texto(linha2[col])) <= LIMITE_CABECALHO:
            eventos[col] = cod_evt

    for c in (col_tipo, col_emp, col_dep, col_nome,
              col_serv, col_desc_serv, col_data):
        if c is not None:
            eventos.pop(c, None)

    return col_tipo, col_emp, col_dep, col_nome, col_serv, col_desc_serv, col_data, eventos


def processar_leiaute_horizontal(df, layout, cod_empresa, competencia, log):
    """
    Leiaute 1 — modelos (todos com regra de faltas / Registro 11):
    - Sem plano de saúde            -> 10 (+ 11)
    - Com plano de saúde            -> 10 (+ 11) + 20 + 25 (eventos de plano, sem faltas)
    - Serviço                       -> 10 (total) + 11 + 40 (por serviço) + Alocacao.txt
    - Com plano de saúde e serviço  -> todas as regras acima
    """
    cab1, cab2, linha_plano, linha_cnpj, linha_dados = localizar_estrutura(df)
    if cab1 is None or cab2 is None:
        raise ValueError("Cabeçalho da planilha não encontrado.")
    if linha_dados is None:
        raise ValueError("Linhas de dados não encontradas.")

    (col_tipo, col_emp, col_dep, col_nome,
     col_serv, col_desc_serv, col_data, eventos) = detectar_colunas(df, cab1, cab2)
    if not eventos:
        raise ValueError("Nenhum evento foi identificado no cabeçalho.")
    if col_data is not None and col_serv is None:
        raise ValueError(
            "A coluna 'Data da Troca' foi encontrada, mas a coluna 'Código Serviço' não. "
            "Verifique o cabeçalho da planilha."
        )

    tem_plano = (linha_plano is not None) or (col_dep is not None)
    tem_serv  = col_serv is not None
    modelo    = MODELOS[(tem_plano, tem_serv)]
    log.append(f"Modelo identificado: {modelo}")
    log.append(f"Colunas de eventos detectadas: {len(eventos)}")

    def _desc_col(c):
        return f"col {c + 1}" if c is not None else "não encontrada"

    if tem_plano:
        log.append(
            f"Plano de saúde → Código Dependente: {_desc_col(col_dep)}"
            f" | Linha 'Evento de Plano': {'sim' if linha_plano is not None else 'não encontrada'}"
            f" | Linha 'CNPJ Operadora': {'sim' if linha_cnpj is not None else 'não encontrada'}"
        )
    if tem_serv:
        log.append(
            f"Serviço → Código Serviço: {_desc_col(col_serv)}"
            f" | Descrição Serviço: {_desc_col(col_desc_serv)} (só conferência)"
            f" | Data da Troca: {_desc_col(col_data)}"
        )

    plano_saude    = {}
    cnpj_operadora = {}
    if linha_plano is not None:
        for col in eventos:
            plano_saude[col] = eh_sim(df.iloc[linha_plano, col])
    if linha_cnpj is not None:
        for col in eventos:
            cnpj_operadora[col] = so_numeros(df.iloc[linha_cnpj, col])

    itens_saida        = []
    blocos_rateio      = {}
    linha_com_serv     = {}
    linha_sem_serv     = {}
    alocacoes          = {}
    datas_falta_vistas = defaultdict(set)
    erros              = []
    avisos             = []
    info_faltas        = []
    ultimo_empregado   = ""
    total_saude        = defaultdict(int)
    reg10_saude        = {}
    reg20_saude        = {}
    reg25_saude        = defaultdict(list)
    qtd_normais = qtd_saude = qtd_serv_saude_ignorado = qtd_reg11 = qtd_dsr = 0

    for i in range(linha_dados, len(df)):
        row = df.iloc[i].tolist()
        if linha_vazia(row):
            continue
        linha_excel = i + 1

        tpcalc  = so_numeros(row[col_tipo]) if col_tipo < len(row) else ""
        cod_emp = so_numeros(row[col_emp])  if col_emp  < len(row) else ""
        cod_dep = (so_numeros(row[col_dep])
                   if (col_dep is not None and col_dep < len(row)) else "")
        cod_emp_proprio = cod_emp

        cod_serv = ""
        if col_serv is not None and col_serv < len(row):
            cod_serv = cod_num(row[col_serv]).lstrip("0")
        raw_data = row[col_data] if (col_data is not None and col_data < len(row)) else ""

        linha_dependente = (not cod_emp_proprio) and bool(cod_dep)
        if linha_dependente and (cod_serv or texto(raw_data)):
            erros.append(
                f"Linha {linha_excel}: Código Serviço/Data da Troca informados em linha de "
                f"dependente ({cod_dep}). Informe-os somente na linha do titular "
                f"(Código Empregado)."
            )
            continue

        # ---------- ALOCAÇÃO ----------
        if col_data is not None:
            dt_troca = None
            try:
                dt_troca = parse_data(raw_data)
            except ValueError:
                erros.append(
                    f"Linha {linha_excel}: Data da troca invalida ({texto(raw_data)}). "
                    f"Informe no formato DD/MM/AAAA."
                )
            if dt_troca is not None:
                emp_aloc = cod_emp_proprio.lstrip("0")
                if not emp_aloc:
                    erros.append(f"Linha {linha_excel}: Codigo do empregado nao informado.")
                elif not cod_serv:
                    erros.append(
                        f"Linha {linha_excel}: Codigo do servico nao informado "
                        f"(Data da Troca preenchida)."
                    )
                elif len(emp_aloc) > ALOC_MAX_DIGITOS or len(cod_serv) > ALOC_MAX_DIGITOS:
                    erros.append(
                        f"Linha {linha_excel}: codigo do empregado/servico com mais de "
                        f"{ALOC_MAX_DIGITOS} digitos."
                    )
                else:
                    chave_aloc = (int(emp_aloc), dt_troca)
                    existente = alocacoes.get(chave_aloc)
                    if existente and existente[0] != cod_serv:
                        erros.append(
                            f"Linha {linha_excel}: Empregado {emp_aloc} com dois servicos "
                            f"diferentes na mesma data ({dt_troca.strftime('%d/%m/%Y')}): "
                            f"servico {existente[0]} (linha {existente[1]}) e servico {cod_serv}."
                        )
                    elif not existente:
                        alocacoes[chave_aloc] = (cod_serv, linha_excel)

                    if competencia and (dt_troca.year * 100 + dt_troca.month) > int(competencia):
                        avisos.append(
                            f"AVISO linha {linha_excel}: data da troca "
                            f"{dt_troca.strftime('%d/%m/%Y')} posterior à competência "
                            f"{competencia[4:]}/{competencia[:4]}."
                        )

        # ---------- LANÇAMENTOS ----------
        if not tpcalc:
            continue
        if cod_emp:
            ultimo_empregado = cod_emp
        elif cod_dep and ultimo_empregado:
            cod_emp = ultimo_empregado
        if not cod_emp and not cod_dep:
            continue

        for col, cod_evt in eventos.items():
            if col >= len(row):
                continue
            celula = row[col]
            chave  = (cod_emp, cod_evt, tpcalc or "11")

            # ---- Datas de falta/reembolso (Registro 11) ----
            try:
                faltas = extrair_datas_falta(celula)
            except ValueError as e:
                erros.append(f"Linha {linha_excel}, evento {cod_evt}: {e}.")
                continue

            if faltas:
                if plano_saude.get(col, False):
                    erros.append(
                        f"Linha {linha_excel}, evento {cod_evt}: datas de falta não são "
                        f"permitidas em evento de plano de saúde."
                    )
                    continue
                if linha_dependente:
                    erros.append(
                        f"Linha {linha_excel}, evento {cod_evt}: datas de falta informadas em "
                        f"linha de dependente. Informe-as na linha do titular."
                    )
                    continue
                erros.extend(validar_faltas(
                    faltas, datas_falta_vistas[chave], linha_excel,
                    cod_evt, cod_emp, competencia, avisos,
                ))
                info_faltas.append(
                    f"Faltas → linha {linha_excel}, empregado {cod_emp.lstrip('0')}, "
                    f"evento {cod_evt}: {descrever_faltas(faltas)}"
                )
                valor = str(len(faltas) * 100).zfill(9)    # 1,00 por dia
            else:
                faltas = []
                valor = valor_para_layout(celula, 9)
                if not valor or int(valor) == 0:
                    continue

            if plano_saude.get(col, False):
                if cod_serv:
                    qtd_serv_saude_ignorado += 1
                total_saude[chave] += int(valor)
                reg10_saude[chave] = montar_registro(layout, "10", {
                    "empregado":   cod_emp,
                    "competencia": competencia,
                    "rubrica":     cod_evt,
                    "tpcalc":      tpcalc or "11",
                    "valor":       str(total_saude[chave]).zfill(9),
                    "empresa":     cod_empresa,
                })
                reg20_saude[chave] = montar_registro(layout, "20", {
                    "cnpj_operadora": cnpj_operadora.get(col, ""),
                })
                tipo_ben = "D" if cod_dep else "T"
                cod_ben  = cod_dep if cod_dep else cod_emp
                reg25_saude[chave].append(
                    montar_registro(layout, "25", {
                        "tipo_beneficiario":   tipo_ben,
                        "codigo_beneficiario": cod_ben,
                        "valor": valor,
                    })
                )
                qtd_saude += 1

            elif cod_serv:
                linha_com_serv.setdefault(chave, linha_excel)
                bloco = blocos_rateio.get(chave)
                if bloco is None:
                    bloco = {
                        "empregado": cod_emp,
                        "rubrica":   cod_evt,
                        "tpcalc":    tpcalc or "11",
                        "total":     0,
                        "servicos":  {},
                        "faltas":    [],
                    }
                    blocos_rateio[chave] = bloco
                    itens_saida.append(bloco)
                bloco["total"] += int(valor)
                bloco["servicos"][cod_serv] = bloco["servicos"].get(cod_serv, 0) + int(valor)
                bloco["faltas"].extend(faltas)

            else:
                linha_sem_serv.setdefault(chave, linha_excel)
                itens_saida.append(
                    montar_registro(layout, "10", {
                        "empregado":   cod_emp,
                        "competencia": competencia,
                        "rubrica":     cod_evt,
                        "tpcalc":      tpcalc or "11",
                        "valor":       valor,
                        "empresa":     cod_empresa,
                    })
                )
                regs11 = montar_registros_falta(layout, faltas)
                itens_saida.extend(regs11)
                qtd_reg11 += len(regs11)
                qtd_dsr   += contar_dsr(faltas)
                qtd_normais += 1

    for chave in sorted(set(linha_com_serv) & set(linha_sem_serv)):
        emp, rub, _ = chave
        erros.append(
            f"Empregado {emp.lstrip('0')}, rubrica {rub}: há lançamentos com e sem "
            f"Código Serviço (linhas {linha_com_serv[chave]} e {linha_sem_serv[chave]}). "
            f"Informe o serviço em todas as linhas da rubrica ou em nenhuma."
        )

    empresa_aloc = cod_empresa.lstrip("0")
    if alocacoes and len(empresa_aloc) > ALOC_MAX_DIGITOS:
        erros.append(f"Codigo da empresa com mais de {ALOC_MAX_DIGITOS} digitos.")

    log.extend(info_faltas)
    log.extend(avisos)
    if qtd_serv_saude_ignorado:
        log.append(
            f"AVISO: {qtd_serv_saude_ignorado} lançamento(s) de plano de saúde com "
            f"Código Serviço — rateio não aplicado a eventos de plano de saúde."
        )

    if erros:
        for e in erros:
            log.append(f"ERRO: {e}")
        raise ValueError(
            f"{len(erros)} inconsistência(s) encontrada(s). Nenhum arquivo foi gerado — "
            f"corrija a planilha e gere novamente."
        )

    # ---------- Montagem do arquivo de eventos ----------
    linhas_saida = []
    qtd_reg40 = 0
    for item in itens_saida:
        if isinstance(item, str):
            linhas_saida.append(item)
            continue
        linhas_saida.append(
            montar_registro(layout, "10", {
                "empregado":   item["empregado"],
                "competencia": competencia,
                "rubrica":     item["rubrica"],
                "tpcalc":      item["tpcalc"],
                "valor":       str(item["total"]).zfill(9),
                "empresa":     cod_empresa,
            })
        )
        regs11 = montar_registros_falta(layout, item["faltas"])
        linhas_saida.extend(regs11)
        qtd_reg11 += len(regs11)
        qtd_dsr   += contar_dsr(item["faltas"])
        for serv, v in item["servicos"].items():
            linhas_saida.append(
                montar_registro(layout, "40", {
                    "servico": serv,
                    "rubrica": item["rubrica"],
                    "valor":   str(v).zfill(9),
                })
            )
            qtd_reg40 += 1

    for chave in reg10_saude:
        linhas_saida.append(reg10_saude[chave])
        linhas_saida.append(reg20_saude[chave])
        for r25 in reg25_saude[chave]:
            linhas_saida.append(r25)

    linhas_aloc = []
    for (emp, dt), (serv, _) in sorted(alocacoes.items(), key=lambda x: x[0]):
        linhas_aloc.append(ALOC_SEPARADOR.join([
            empresa_aloc,
            str(emp),
            serv,
            dt.strftime("%d/%m/%Y"),
        ]))

    extras = {
        "modelo":     modelo,
        "alocacao":   linhas_aloc,
        "qtd_rateio": len(blocos_rateio),
        "qtd_reg40":  qtd_reg40,
        "qtd_reg11":  qtd_reg11,
        "qtd_dsr":    qtd_dsr,
    }
    return linhas_saida, qtd_normais, qtd_saude, extras


# ==============================
# LEIAUTE 2 — funções exclusivas
# ==============================
def localizar_cabecalho_vertical(df):
    for i in range(len(df) - 1):
        linha_a = [normalizar(x) for x in df.iloc[i].tolist()]
        linha_b = [normalizar(x) for x in df.iloc[i + 1].tolist()]
        combinadas = [f"{a} {b}".strip() for a, b in zip(linha_a, linha_b)]

        col_tipo = col_emp = col_rubrica = col_valor = None

        for col, comb in enumerate(combinadas):
            a = linha_a[col]
            b = linha_b[col]
            if len(a) > LIMITE_CABECALHO or len(b) > LIMITE_CABECALHO:
                continue
            if col_tipo is None and (
                "tipo de calculo" in comb or (a == "tipo de" and b == "calculo")
            ):
                col_tipo = col
                continue
            if col_emp is None and (
                "codigo folha" in comb or "codigo empregado" in comb or
                (a == "codigo" and b in ("folha", "empregado"))
            ):
                col_emp = col
                continue
            if col_rubrica is None and (
                "codigo rubrica" in comb or (a == "codigo" and b == "rubrica")
            ):
                col_rubrica = col
                continue
            if col_valor is None and (
                "referencia valor" in comb or "referencia" in comb or
                b in ("valor", "referencia") or a in ("referencia", "valor")
            ):
                col_valor = col
                continue

        if None not in (col_tipo, col_emp, col_rubrica, col_valor):
            return i + 2, {
                "col_tipo":    col_tipo,
                "col_emp":     col_emp,
                "col_rubrica": col_rubrica,
                "col_valor":   col_valor,
            }

    raise ValueError(
        "Cabeçalho do Leiaute V2 não encontrado. "
        "Verifique se as colunas 'Código Rubrica' e 'Referência/Valor' estão presentes."
    )


def processar_leiaute_vertical(df, layout, cod_empresa, competencia, log):
    linha_dados, cols = localizar_cabecalho_vertical(df)

    col_tipo    = cols["col_tipo"]
    col_emp     = cols["col_emp"]
    col_rubrica = cols["col_rubrica"]
    col_valor   = cols["col_valor"]

    log.append(f"Modelo identificado: {layout['nome']}")
    log.append(
        f"Colunas detectadas → "
        f"tipo:{col_tipo} | emp:{col_emp} | rubrica:{col_rubrica} | valor:{col_valor}"
    )

    linhas_saida       = []
    qtd_normais        = 0
    qtd_ignoradas      = 0
    qtd_reg11          = 0
    qtd_dsr            = 0
    erros              = []
    avisos             = []
    info_faltas        = []
    datas_falta_vistas = defaultdict(set)

    for i in range(linha_dados, len(df)):
        row = df.iloc[i].tolist()
        if linha_vazia(row):
            continue
        linha_excel = i + 1

        tpcalc  = so_numeros(row[col_tipo])    if col_tipo    < len(row) else ""
        cod_emp = so_numeros(row[col_emp])     if col_emp     < len(row) else ""
        rubrica = so_numeros(row[col_rubrica]) if col_rubrica < len(row) else ""
        celula  = row[col_valor] if col_valor < len(row) else ""

        if not tpcalc or not cod_emp or not rubrica:
            continue

        try:
            faltas = extrair_datas_falta(celula)
        except ValueError as e:
            erros.append(f"Linha {linha_excel}, rubrica {rubrica}: {e}.")
            continue

        if faltas:
            erros.extend(validar_faltas(
                faltas, datas_falta_vistas[(cod_emp, rubrica, tpcalc)], linha_excel,
                rubrica, cod_emp, competencia, avisos,
            ))
            info_faltas.append(
                f"Faltas → linha {linha_excel}, empregado {cod_emp.lstrip('0')}, "
                f"rubrica {rubrica}: {descrever_faltas(faltas)}"
            )
            valor = str(len(faltas) * 100).zfill(9)
        else:
            faltas = []
            valor = valor_para_layout(celula, 9)
            if not valor or int(valor) == 0:
                qtd_ignoradas += 1
                continue

        linhas_saida.append(
            montar_registro(layout, "10", {
                "empregado":   cod_emp,
                "competencia": competencia,
                "rubrica":     rubrica,
                "tpcalc":      tpcalc,
                "valor":       valor,
                "empresa":     cod_empresa,
            })
        )
        regs11 = montar_registros_falta(layout, faltas)
        linhas_saida.extend(regs11)
        qtd_reg11 += len(regs11)
        qtd_dsr   += contar_dsr(faltas)
        qtd_normais += 1

    if qtd_ignoradas:
        log.append(f"Linhas ignoradas (valor vazio/zero): {qtd_ignoradas}")
    log.extend(info_faltas)
    log.extend(avisos)
    if erros:
        for e in erros:
            log.append(f"ERRO: {e}")
        raise ValueError(
            f"{len(erros)} inconsistência(s) encontrada(s). Nenhum arquivo foi gerado — "
            f"corrija a planilha e gere novamente."
        )

    return linhas_saida, qtd_normais, 0, {
        "modelo": layout["nome"], "alocacao": [], "qtd_rateio": 0,
        "qtd_reg40": 0, "qtd_reg11": qtd_reg11, "qtd_dsr": qtd_dsr,
    }


# ==============================
# PROCESSAMENTO PRINCIPAL
# ==============================
def processar_bytes(arquivo_bytes, log):
    """Retorna (linhas_eventos, meta, linhas_alocacao)."""
    try:
        df = carregar_excel(arquivo_bytes)

        leiaute_chave = detectar_leiaute(df)
        layout = LEIAUTES[leiaute_chave]
        log.append(f"Leiaute detectado: {layout['nome']}")

        cod_empresa, competencia = localizar_metadados(df)
        if not cod_empresa:
            raise ValueError("Código da empresa não encontrado.")
        if not competencia:
            raise ValueError("Competência não encontrada.")
        log.append(f"Empresa: {cod_empresa}  |  Competência: {competencia}")

        if leiaute_chave == "importacao_arquivo_texto_lancamentos":
            linhas_saida, qtd_normais, qtd_saude, extras = processar_leiaute_horizontal(
                df, layout, cod_empresa, competencia, log
            )
        elif leiaute_chave == "relacao_valores_vertical":
            linhas_saida, qtd_normais, qtd_saude, extras = processar_leiaute_vertical(
                df, layout, cod_empresa, competencia, log
            )
        else:
            raise ValueError(f"Leiaute '{leiaute_chave}' sem processador definido.")

        log.append(f"Eventos normais : {qtd_normais}")
        log.append(f"Eventos c/ rateio: {extras['qtd_rateio']}")
        log.append(f"Registros 11 (faltas): {extras['qtd_reg11']}")
        log.append(f"Faltas DSR (tipo 2): {extras['qtd_dsr']}")
        log.append(f"Registros 40    : {extras['qtd_reg40']}")
        log.append(f"Eventos plano de saúde: {qtd_saude}")
        log.append(f"Total de linhas : {len(linhas_saida)}")
        log.append(f"Alocações       : {len(extras['alocacao'])}")

        meta = {
            "empresa":     cod_empresa,
            "competencia": competencia,
            "modelo":      extras["modelo"],
        }
        return linhas_saida, meta, extras["alocacao"]

    except Exception as e:
        log.append(f"ERRO: {e}")
        return None, None, None


# ==============================
# INSTRUÇÕES DE USO
# Ordem: passos -> como preencher -> observações -> detalhes técnicos (fim, recolhido)
# ==============================
def montar_instrucoes():
    plano = EXIBIR_MODELOS_PLANO
    p = []

    p.append('<div class="instrucoes-box">')

    # ---------------- PASSOS ----------------
    p.append("<h4>🔹 Passo 1 — Baixar o modelo de planilha</h4>")
    p.append("<p>Na barra lateral, baixe o arquivo <code>.bgr</code> do modelo desejado:</p>")
    p.append("<ul>")
    p.append("<li><b>Sem plano de saúde</b> — lançamentos comuns da folha (horas, faltas, valores).</li>")
    if plano:
        p.append("<li><b>Com plano de saúde</b> — quando houver valores de plano de saúde "
                 "por titular e dependentes.</li>")
    p.append("<li><b>Serviço</b> — quando houver alocação e/ou rateio de valores por serviço "
             "(tomador/obra).</li>")
    if plano:
        p.append("<li><b>Com plano de saúde e serviço</b> — junta as duas situações acima.</li>")
    p.append("</ul>")

    p.append("<h4>🔹 Passo 2 — Importar o modelo no Domínio</h4>")
    p.append("<p>Utilitários → Gerador de Relatórios → Importar → selecione o "
             "<code>.bgr</code> baixado.</p>")

    p.append("<h4>🔹 Passo 3 — Preencher e exportar a planilha</h4>")
    p.append("<p>Execute o relatório em <b>Utilitários → Gerador de Relatórios</b>, informe a "
             "empresa, a competência e as rubricas desejadas e exporte em "
             "<b>Excel (.xlsx ou .xls)</b>.</p>")
    p.append("<p>Os dados de alocação e/ou rateio de valores são lançados na própria planilha. "
             "Se o colaborador tiver <b>mais de um serviço</b> na competência, "
             "<b>duplique a linha desse colaborador</b> na planilha — uma linha para cada serviço.</p>")
    p.append("<p>Os valores informados em cada evento serão lançados para o "
             "<b>serviço correspondente daquela linha</b>.</p>")

    p.append("<h4>🔹 Passo 4 — Gerar os arquivos TXT</h4>")
    p.append("<p>Faça o upload no campo indicado desta página, clique em "
             "<b>▶ Gerar arquivo TXT</b> e baixe os arquivos.</p>")

    p.append("<h4>🔹 Passo 5 — Importar no Domínio</h4>")
    p.append("<ol>")
    p.append(
        "<li><b>Alocacao.txt</b> (se gerado) → Folha → Utilitários → Importação → "
        "de Arquivo Texto → <b>De Tabela</b>.<br>"
        "Selecione o <b>Nome do Layout</b>, se já foi salvo anteriormente para alocação de serviço.<br>"
        f"Selecione a tabela <code>{ALOC_TABELA}</code> "
        "(Descrição: <i>Tabela de Importação de Trocas de Serviço</i>).<br>"
        "Informe o diretório de origem do arquivo TXT gerado nesta página e o nome do arquivo "
        "na linha correspondente da tabela.</li>"
    )
    p.append(
        "<li><b>Eventos</b> → Folha → Utilitários → Importação → de Arquivo Texto → "
        "<b>De Lançamentos</b>.<br>"
        "Importe os eventos <b>somente após</b> a importação ou digitação da alocação dos "
        "serviços da competência.</li>"
    )
    p.append("</ol>")

    p.append("<hr>")

    # ---------------- COMO PREENCHER ----------------
    p.append("<h4>📝 Como preencher a planilha</h4>")

    p.append("<h5>Horas, dias e valores</h5>")
    p.append("<ul>")
    p.append("<li>Horas: respeite o formato já usado na empresa. Ex.: uma hora e meia = "
             "<code>1,30</code> em minutos ou <code>1,50</code> em decimais.</li>")
    p.append("<li>Dias: use vírgula como separador. Ex.: uma falta = <code>1,00</code>.</li>")
    p.append("<li>Células vazias ou com zero são ignoradas.</li>")
    p.append("</ul>")

    p.append("<h5>Faltas com data (inclusive DSR)</h5>")
    p.append("<ul>")
    p.append("<li>Na coluna do evento de faltas, em vez da quantidade, você pode informar as "
             "<b>datas no formato DD/MM/AAAA, separadas por ponto e vírgula (;)</b>. "
             "Ex.: <code>02/01/2026;03/01/2026</code>.</li>")
    p.append("<li>Para falta de <b>DSR</b>, escreva <code>DSR</code> junto da data. "
             "Ex.: <code>02/01/2026 DSR;03/01/2026</code>.</li>")
    p.append("<li>Somente a data = falta normal.</li>")
    p.append("<li>A quantidade de dias é calculada automaticamente (1,00 por data).</li>")
    p.append("<li>Não repita a mesma data para o mesmo colaborador e evento.</li>")
    p.append("<li>Após gerar, confira no log a lista de datas com o tipo (Normal/DSR).</li>")
    p.append("</ul>")

    p.append("<h5>Serviços (modelos com serviço)</h5>")
    p.append("<ul>")
    p.append("<li><b>Código Serviço</b>: código do serviço em que o valor da linha será lançado.</li>")
    p.append("<li><b>Descrição Serviço</b>: apenas para conferência; não é importada.</li>")
    p.append("<li><b>Data da Troca</b>: data em que o colaborador passou a atuar no serviço. "
             "Quando preenchida, gera o arquivo de alocação.</li>")
    p.append("<li>Código Serviço em branco: lançamento normal, sem vínculo com serviço.</li>")
    p.append("<li>Se uma rubrica do colaborador tiver serviço em uma linha, informe o serviço "
             "em todas as linhas dessa rubrica.</li>")
    p.append("<li>Pré-requisitos no Domínio: serviços cadastrados e "
             "<b>Parâmetros → Geral → Cálculo → Rateio por serviço = Sim</b>.</li>")
    p.append("</ul>")

    if plano:
        p.append("<h5>Plano de saúde (modelos com plano de saúde)</h5>")
        p.append("<ul>")
        p.append("<li>Na linha <b>Evento de Plano de Saúde</b>, marque <b>Sim</b> nas colunas "
                 "dos eventos de plano e informe o <b>CNPJ da Operadora</b> logo abaixo.</li>")
        p.append("<li>Titular na linha com Código Empregado; dependentes nas linhas seguintes, "
                 "com Código Dependente.</li>")
        p.append("<li>Eventos de plano de saúde <b>não são rateados</b> por serviço e "
                 "não aceitam datas de falta.</li>")
        p.append("<li>No modelo com serviço, informe serviço e data da troca "
                 "<b>somente na linha do titular</b>.</li>")
        p.append("</ul>")

    # ---------------- OBSERVAÇÕES ----------------
    p.append("<h4>⚠ Observações</h4>")
    p.append("<ul>")
    p.append("<li>Se houver qualquer erro, <b>nenhum arquivo é gerado</b>: corrija a planilha "
             "conforme o log e gere novamente.</li>")
    p.append("<li>Um colaborador não pode ter dois serviços diferentes na mesma data da troca.</li>")
    p.append("<li>Linhas repetidas (mesmo colaborador, serviço e data) geram uma única alocação.</li>")
    p.append(f"<li>Códigos de empresa, empregado e serviço na alocação: até "
             f"<b>{ALOC_MAX_DIGITOS} dígitos</b>.</li>")
    p.append("<li>Confira se as datas informadas pertencem à competência da planilha.</li>")
    p.append("</ul>")

    # ---------------- DETALHES TÉCNICOS (FIM) ----------------
    p.append("<details>")
    p.append("<summary>🔧 Detalhes técnicos dos arquivos (leiautes) — para consulta do suporte</summary>")

    p.append("<h5>Registros gerados por modelo</h5>")
    p.append("<table>")
    p.append("<tr><th>Modelo</th><th>Arquivo de eventos</th><th>Alocação</th></tr>")
    p.append("<tr><td>Sem plano de saúde</td><td>10 + 11</td><td>—</td></tr>")
    if plano:
        p.append("<tr><td>Com plano de saúde</td><td>10 + 11 + 20 + 25</td><td>—</td></tr>")
    p.append("<tr><td>Serviço</td><td>10 + 11 + 40</td><td>Alocacao.txt</td></tr>")
    if plano:
        p.append("<tr><td>Com plano de saúde e serviço</td><td>10 + 11 + 20 + 25 + 40</td>"
                 "<td>Alocacao.txt</td></tr>")
    p.append("<tr><td>Vertical V2 (Relação de Valores)</td><td>10 + 11</td><td>—</td></tr>")
    p.append("</table>")

    p.append("<h5>Significado dos registros</h5>")
    p.append("<ul>")
    p.append("<li><b>10</b> — lançamento do evento (empregado, competência, rubrica, "
             "tipo de cálculo, valor, empresa).</li>")
    p.append("<li><b>11</b> — dias de faltas / reembolso de faltas: "
             "posições 001-002 = <code>11</code>, 003-010 = data <code>AAAAMMDD</code>, "
             "011 = tipo (<code>1</code> Normal | <code>2</code> DSR). "
             "Um registro por data, logo abaixo do registro 10.</li>")
    if plano:
        p.append("<li><b>20</b> — CNPJ da operadora de plano de saúde.</li>")
        p.append("<li><b>25</b> — beneficiário do plano (T = titular, D = dependente) e valor.</li>")
    p.append("<li><b>40</b> — valor da rubrica por serviço; o registro 10 traz o total.</li>")
    p.append("</ul>")

    p.append("<h5>Leiaute do Alocacao.txt</h5>")
    p.append("<p>Campos separados por <b>tabulação</b>, nesta ordem: "
             "<code>Código Empresa | Código Empregado | Código Serviço | Data da Troca (DD/MM/AAAA)</code>. "
             f"Ao criar o layout em <b>De Tabela</b> pela primeira vez, use a tabela "
             f"<code>{ALOC_TABELA}</code> com os campos nessa ordem e salve o layout para "
             "as próximas importações.</p>")
    p.append("</details>")

    p.append("</div>")

    # Remove recuos e linhas em branco (evita que o Markdown trate trechos como bloco de código)
    html = "\n".join(p)
    return "\n".join(l.strip() for l in html.splitlines() if l.strip())


# ==============================
# INTERFACE STREAMLIT
# ==============================
def main():
    st.set_page_config(
        page_title="Domínio Sistemas | Thomson Reuters",
        page_icon="🟠",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_tr_theme()

    st.markdown(
        f"""
        <div style="background:#444444; padding:24px 28px 18px 28px; border-radius:8px;
                    border-top:6px solid #FF8000; margin-bottom:28px;">
            <h2 style="color:#FF8000; margin:0; font-family:'Segoe UI',Arial,sans-serif;">
                📊 Conversor de Eventos &nbsp;|&nbsp; {VERSAO}
            </h2>
            <p style="color:#DDDDDD; margin:6px 0 0 0; font-family:'Segoe UI',Arial,sans-serif;">
                Selecione o Excel de origem e clique em
                <strong>Gerar arquivo TXT</strong>.
                O modelo da planilha é identificado <b>automaticamente</b>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### 📥 Modelos de Planilha")
        st.markdown(
            "Baixe o modelo correspondente ao seu tipo de lançamento "
            "e importe no **Domínio Sistemas** (veja o Passo 2 das instruções)."
        )
        for rotulo, arq_b64, nome_bgr, chave, usa_plano in MODELOS_BGR:
            if usa_plano and not EXIBIR_MODELOS_PLANO:
                continue
            dados_bgr = carregar_bgr_bytes(arq_b64)
            if dados_bgr is not None:
                st.download_button(
                    label=f"⬇ {rotulo}.bgr",
                    data=dados_bgr,
                    file_name=nome_bgr,
                    mime="application/octet-stream",
                    use_container_width=True,
                    key=chave,
                )
            else:
                st.info(f"Modelo '{rotulo}' indisponível.")

        st.markdown("---")
        st.markdown("### ℹ Sobre")
        st.markdown(f"**Versão:** {VERSAO}")
        st.markdown("**Thomson Reuters**")
        st.markdown("**Domínio Sistemas**")

    with st.expander("📖 **Instruções de Uso** — clique para expandir", expanded=False):
        st.markdown(montar_instrucoes(), unsafe_allow_html=True)

    st.markdown("---")

    defaults = {
        "log_conv":    [f"Aplicação pronta. Versão: {VERSAO}"],
        "txt_conv":    None,
        "nome_conv":   "Eventos.txt",
        "txt_aloc":    None,
        "nome_aloc":   "Alocacao.txt",
        "modelo_conv": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    modelos_ajuda = (
        "Sem plano de saúde, Com plano de saúde, Serviço, Com plano de saúde e serviço "
        "ou Vertical V2." if EXIBIR_MODELOS_PLANO else
        "Sem plano de saúde, Serviço ou Vertical V2."
    )
    arquivo = st.file_uploader(
        "Excel de origem (.xlsx ou .xls)",
        type=["xlsx", "xls"],
        help=f"{modelos_ajuda} Detectado automaticamente.",
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        gerar = st.button(
            "▶ Gerar arquivo TXT",
            disabled=(arquivo is None),
            use_container_width=True,
            type="primary",
        )
    with col2:
        limpar = st.button("🗑 Limpar", use_container_width=True)

    if limpar:
        for k, v in defaults.items():
            st.session_state[k] = v
        st.session_state.log_conv = ["Campos limpos."]
        st.rerun()

    if gerar and arquivo is not None:
        st.session_state.log_conv    = [f"Iniciando processamento... ({VERSAO})"]
        st.session_state.txt_conv    = None
        st.session_state.txt_aloc    = None
        st.session_state.nome_conv   = "Eventos.txt"
        st.session_state.nome_aloc   = "Alocacao.txt"
        st.session_state.modelo_conv = None

        linhas, meta, aloc = processar_bytes(arquivo.read(), st.session_state.log_conv)

        if meta:
            emp, comp = meta["empresa"], meta["competencia"]
            st.session_state.modelo_conv = meta["modelo"]
            if linhas:
                conteudo = "\n".join(linhas) + "\n"
                st.session_state.txt_conv  = conteudo.encode("utf-8", errors="replace")
                st.session_state.nome_conv = f"{emp}_Eventos_{comp}.txt"
                st.session_state.log_conv.append("Arquivo de eventos gerado com sucesso.")
            if aloc:
                conteudo_aloc = "\n".join(aloc) + "\n"
                st.session_state.txt_aloc  = conteudo_aloc.encode("utf-8", errors="replace")
                st.session_state.nome_aloc = f"{emp}_Alocacao_{comp}.txt"
                st.session_state.log_conv.append(
                    "Arquivo de alocação gerado com sucesso (separado por tabulação)."
                )
            if not linhas and not aloc:
                st.session_state.log_conv.append("Nenhum lançamento ou alocação encontrado.")

        st.rerun()

    if st.session_state.txt_conv is not None or st.session_state.txt_aloc is not None:
        modelo_txt = (f" — modelo: **{st.session_state.modelo_conv}**"
                      if st.session_state.modelo_conv else "")
        st.success(f"✅ Arquivo(s) gerado(s) com sucesso{modelo_txt}")
        d1, d2 = st.columns(2)
        with d1:
            if st.session_state.txt_conv is not None:
                st.download_button(
                    label="⬇ Baixar TXT de Eventos",
                    data=st.session_state.txt_conv,
                    file_name=st.session_state.nome_conv,
                    mime="text/plain",
                    use_container_width=True,
                    type="primary",
                    key="dl_eventos",
                )
        with d2:
            if st.session_state.txt_aloc is not None:
                st.download_button(
                    label="⬇ Baixar TXT de Alocação",
                    data=st.session_state.txt_aloc,
                    file_name=st.session_state.nome_aloc,
                    mime="text/plain",
                    use_container_width=True,
                    type="primary",
                    key="dl_alocacao",
                )
        if st.session_state.txt_aloc is not None:
            st.info(
                "ℹ Importe primeiro o arquivo de **Alocação** (De Tabela → "
                f"`{ALOC_TABELA}`) e depois o de **Eventos** (De Lançamentos)."
            )

        if st.session_state.txt_conv is not None:
            with st.expander("🔎 Pré-visualizar TXT de Eventos"):
                linhas_prev = st.session_state.txt_conv.decode(
                    "utf-8", errors="replace").splitlines()
                st.code("\n".join(linhas_prev[:500]), language=None)
                if len(linhas_prev) > 500:
                    st.caption(f"Exibindo 500 de {len(linhas_prev)} linhas.")

    log = st.session_state.log_conv

    def ler_metrica(rotulo):
        for linha in log:
            if linha.startswith(rotulo):
                try:
                    return int(linha.split(":")[-1].strip())
                except Exception:
                    return None
        return None

    normais = ler_metrica("Eventos normais")
    if normais is not None:
        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
        c1.metric("Eventos normais",        normais)
        c2.metric("Eventos c/ rateio",      ler_metrica("Eventos c/ rateio"))
        c3.metric("Faltas com data",        ler_metrica("Registros 11"))
        c4.metric("Faltas DSR",             ler_metrica("Faltas DSR"))
        c5.metric("Eventos plano de saúde", ler_metrica("Eventos plano de saúde"))
        c6.metric("Total de linhas",        ler_metrica("Total de linhas"))
        c7.metric("Alocações",              ler_metrica("Alocações"))

    st.markdown("**Log de processamento**")
    log_texto = "\n".join(log)
    tem_erro  = any(str(l).startswith("ERRO") for l in log)
    cor_borda = "#D32F2F" if tem_erro else "#388E3C"

    st.markdown(
        f"""
        <div style="background:#FCFCFC; border:1px solid {cor_borda};
                    border-radius:6px; padding:14px;
                    font-family:Consolas,monospace; font-size:13px;
                    white-space:pre-wrap; max-height:340px;
                    overflow-y:auto; color:#1F1F1F;">
{log_texto}
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
