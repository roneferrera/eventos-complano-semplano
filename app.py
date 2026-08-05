import os
import re
import io
import base64
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
import pandas as pd
import streamlit as st

# ==============================
# VERSÃO
# ==============================
VERSAO = "V1.1"

# ==============================
# TEMA TR (espelho do RPA)
# ==============================
def apply_tr_theme():
    st.markdown("""
        <style>
        html, body, [class*="css"] {
            font-family: 'Segoe UI', 'Arial', sans-serif;
            color: #444444;
        }
        h1, h2, h3 {
            color: #FF8000;
            font-weight: 700;
        }
        section[data-testid="stSidebar"] {
            background-color: #444444;
            color: #FFFFFF;
        }
        section[data-testid="stSidebar"] * {
            color: #FFFFFF !important;
        }
        .stButton > button {
            background-color: #FF8000;
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            font-weight: bold;
        }
        .stButton > button:hover {
            background-color: #D64001;
            color: #FFFFFF;
        }
        .stDownloadButton > button {
            background-color: #FF8000;
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            font-weight: bold;
        }
        .stDownloadButton > button:hover {
            background-color: #D64001;
            color: #FFFFFF;
        }
        hr {
            border-color: #FF8000;
        }
        [data-testid="metric-container"] {
            background-color: #E9E9E9;
            border-left: 4px solid #FF8000;
            border-radius: 4px;
            padding: 10px;
        }
        .instrucoes-box {
            background-color: #E9E9E9;
            border-left: 4px solid #FF8000;
            border-radius: 4px;
            padding: 16px 20px;
            margin: 12px 0;
            color: #444444;
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        .instrucoes-box h4 {
            color: #FF8000;
            margin-top: 14px;
            margin-bottom: 6px;
        }
        .instrucoes-box h4:first-child {
            margin-top: 0;
        }
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
    except Exception as e:
        st.warning(f"⚠ Não foi possível carregar o modelo '{nome_arquivo_b64}': {e}")
        return None


# ==============================
# UTILITÁRIOS
# ==============================
def texto(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    s = str(v).strip()
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
    from datetime import datetime
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
LEIAUTES = {
    # -------------------------------------------------------
    # LEIAUTE 1 — Original (horizontal, eventos em colunas)
    # NADA alterado aqui
    # -------------------------------------------------------
    "importacao_arquivo_texto_lancamentos": {
        "nome": "Importação Arquivo Texto | De Lançamentos",
        "detector": {
            "cabecalho": ["tipo de", "codigo", "competencia", "codigo empresa"],
            "marcadores": ["folha", "colaboradores"],
        },
        "registros": {
            "10": [
                ("fixo",        2,  "10"),
                ("empregado",  10),
                ("competencia", 6),
                ("rubrica",     9),
                ("tpcalc",      2),
                ("valor",       9),
                ("empresa",    10),
            ],
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
        },
    },

    # -------------------------------------------------------
    # LEIAUTE 2 — Relação de Valores V2 (vertical)
    # Cada linha = um evento. Rubrica lida da coluna "Código Rubrica".
    # Aceita .xls e .xlsx.
    # -------------------------------------------------------
    "relacao_valores_vertical": {
        "nome": "Relação de Valores Para Folha de Pagamento V2 | Vertical",
        "detector": {
            # Marcador exclusivo deste leiaute: título na célula A1
            "cabecalho": ["relacao de valores para folha de pagamento"],
            # Colunas fixas características deste leiaute
            "marcadores": ["codigo rubrica", "descricao rubrica", "referencia"],
        },
        "registros": {
            "10": [
                ("fixo",        2,  "10"),
                ("empregado",  10),
                ("competencia", 6),
                ("rubrica",     9),
                ("tpcalc",      2),
                ("valor",       9),
                ("empresa",    10),
            ],
        },
    },
}


# ==============================
# DETECÇÃO DE LEIAUTE
# ==============================
def detectar_leiaute(df):
    """
    Varre todas as células do DataFrame, normaliza o texto e pontua
    cada leiaute pelos seus marcadores.

    Estratégia de desempate:
      - O Leiaute 2 tem o marcador "relacao de valores para folha de pagamento"
        que é o título da célula A1 — altamente específico.
      - O Leiaute 1 NÃO possui esse título, portanto os scores nunca colidem.
    """
    conteudo = []
    for i in range(len(df)):
        for x in df.iloc[i].tolist():
            t = normalizar(x)
            if t:
                conteudo.append(t)
    texto_total = " | ".join(conteudo)

    melhor, melhor_score = None, -1
    for chave, layout in LEIAUTES.items():
        score = 0
        det = layout.get("detector", {})

        for t in det.get("cabecalho", []):
            if t in texto_total:
                score += 2

        for t in det.get("marcadores", []):
            if t in texto_total:
                score += 3   # peso maior para marcadores de coluna específicos

        if score > melhor_score:
            melhor_score, melhor = score, chave

    if not melhor or melhor_score <= 0:
        raise ValueError(
            "Não foi possível identificar automaticamente o leiaute da planilha."
        )
    return melhor


# ==============================
# UTILITÁRIOS DE LAYOUT
# ==============================
def ajustar_campo_layout(nome, valor, tamanho):
    valor = "" if valor is None else str(valor)
    if nome in ("empregado", "empresa", "codigo_beneficiario"):
        return zfill_num(valor, tamanho)
    if nome in ("rubrica", "tpcalc", "cnpj_operadora", "competencia", "valor"):
        return so_numeros(valor).zfill(tamanho)
    if nome == "tipo_beneficiario":
        return texto(valor)[:tamanho].ljust(tamanho)
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
# LEITURA EXCEL  (.xlsx e .xls)
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
# METADADOS — compartilhado
# ==============================
def localizar_metadados(df):
    """
    Funciona para ambos os leiautes:
      - Leiaute 1: "Codigo Empresa" aparece numa célula, valor na próxima.
      - Leiaute 2: "Codigo Empresa:" na col-A, valor na col-C (índice 2).
    A varredura genérica por linha cobre os dois casos.
    """
    cod_empresa = competencia = ""
    for i in range(len(df)):
        row = df.iloc[i].tolist()
        row_norm = [normalizar(x) for x in row]
        for j, cel in enumerate(row_norm):
            # --- empresa ---
            if cel in ("codigo empresa:", "codigo empresa"):
                # tenta célula imediatamente à direita primeiro,
                # depois qualquer célula não vazia na mesma linha
                for k in range(j + 1, len(row)):
                    num = so_numeros(row[k])
                    if num:
                        cod_empresa = num.zfill(10)
                        break
            # --- competência ---
            if cel in ("competencia:", "competencia"):
                for k in range(j + 1, len(row)):
                    comp = competencia_yyyymm(row[k])
                    if comp:
                        competencia = comp
                        break
    return cod_empresa, competencia


# ==============================
# LEIAUTE 1 — funções exclusivas
# (código 100% idêntico ao V1.0)
# ==============================
def localizar_estrutura(df):
    cab1 = cab2 = linha_plano = linha_cnpj = linha_dados = None
    for i in range(len(df)):
        row = [normalizar(x) for x in df.iloc[i].tolist()]
        joined = " | ".join(row)
        if cab1 is None and "tipo de" in joined and "codigo" in joined:
            cab1 = i
            if i + 1 < len(df):
                cab2 = i + 1
            continue
        if "evento de plano de saude" in joined:
            linha_plano = i
            continue
        if "cnpj da operadora de plano de saude" in joined:
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


def detectar_colunas(df, cab1, cab2):
    linha1 = [texto(x) for x in df.iloc[cab1].tolist()]
    linha2 = [texto(x) for x in df.iloc[cab2].tolist()]
    col_tipo = col_emp = col_dep = col_nome = None
    eventos = {}
    for col in range(len(linha1)):
        a = normalizar(linha1[col])
        b = normalizar(linha2[col])
        combinado = f"{a} {b}".strip()
        if col_tipo is None and (
            "tipo de calculo" in combinado or
            (a == "tipo de" and b == "calculo")
        ):
            col_tipo = col; continue
        if col_emp is None and (
            "codigo empregado" in combinado or
            "codigo folha" in combinado or
            (a == "codigo" and b in ("empregado", "folha"))
        ):
            col_emp = col; continue
        if col_dep is None and (
            "codigo dependente" in combinado or
            (a == "codigo" and b == "dependente")
        ):
            col_dep = col; continue
        if col_nome is None and (
            "nome dos colaboradores" in combinado or
            (a == "nome dos" and b == "colaboradores")
        ):
            col_nome = col; continue
    col_tipo = col_tipo or 0
    col_emp  = col_emp  or 1
    col_dep  = col_dep  or 2
    col_nome = col_nome or 2
    inicio_eventos = max(col_nome + 1, 3)
    for col in range(inicio_eventos, len(linha2)):
        cod_evt  = so_numeros(linha2[col])
        desc_evt = texto(linha1[col])
        if cod_evt:
            eventos[col] = cod_evt
        elif not desc_evt and not texto(linha2[col]):
            continue
    for c in (col_tipo, col_emp, col_dep, col_nome):
        eventos.pop(c, None)
    return col_tipo, col_emp, col_dep, col_nome, eventos


def processar_leiaute_horizontal(df, layout, cod_empresa, competencia, log):
    """Leiaute 1 — lógica 100% idêntica ao V1.0, apenas isolada em função."""
    cab1, cab2, linha_plano, linha_cnpj, linha_dados = localizar_estrutura(df)
    if cab1 is None or cab2 is None:
        raise ValueError("Cabeçalho da planilha não encontrado.")
    if linha_dados is None:
        raise ValueError("Linhas de dados não encontradas.")

    col_tipo, col_emp, col_dep, col_nome, eventos = detectar_colunas(df, cab1, cab2)
    if not eventos:
        raise ValueError("Nenhum evento foi identificado no cabeçalho.")
    log.append(f"Colunas de eventos detectadas: {len(eventos)}")

    plano_saude    = {}
    cnpj_operadora = {}
    if linha_plano is not None:
        for col in eventos:
            plano_saude[col] = eh_sim(df.iloc[linha_plano, col])
    if linha_cnpj is not None:
        for col in eventos:
            cnpj_operadora[col] = so_numeros(df.iloc[linha_cnpj, col])

    linhas_saida     = []
    ultimo_empregado = ""
    total_saude      = defaultdict(int)
    reg10_saude      = {}
    reg20_saude      = {}
    reg25_saude      = defaultdict(list)
    qtd_normais = qtd_saude = 0

    for i in range(linha_dados, len(df)):
        row = df.iloc[i].tolist()
        if linha_vazia(row):
            continue

        tpcalc  = so_numeros(row[col_tipo]) if col_tipo < len(row) else ""
        cod_emp = so_numeros(row[col_emp])  if col_emp  < len(row) else ""
        cod_dep = so_numeros(row[col_dep])  if col_dep  < len(row) else ""

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
            valor = valor_para_layout(row[col], 9)
            if not valor or int(valor) == 0:
                continue

            if plano_saude.get(col, False):
                chave = (cod_emp, cod_evt, tpcalc or "11")
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
            else:
                linhas_saida.append(
                    montar_registro(layout, "10", {
                        "empregado":   cod_emp,
                        "competencia": competencia,
                        "rubrica":     cod_evt,
                        "tpcalc":      tpcalc or "11",
                        "valor":       valor,
                        "empresa":     cod_empresa,
                    })
                )
                qtd_normais += 1

    for chave in reg10_saude:
        linhas_saida.append(reg10_saude[chave])
        linhas_saida.append(reg20_saude[chave])
        for r25 in reg25_saude[chave]:
            linhas_saida.append(r25)

    return linhas_saida, qtd_normais, qtd_saude


# ==============================
# LEIAUTE 2 — funções exclusivas
# ==============================
def localizar_cabecalho_vertical(df):
    """
    Localiza as duas linhas de cabeçalho do Leiaute 2.

    Estrutura real do arquivo (baseada no .xls fornecido):
      Linha cab1 → col0:"Tipo de"  col1:"Código"  col2:"Nome dos"  col3:"Código"   col4:"Descrição"  col5:"Referência"
      Linha cab2 → col0:"Calculo"  col1:"Folha"   col2:"Colaboradores" col3:"Rubrica" col4:"Rubrica"  col5:"Valor"

    A rubrica de cada evento vem da coluna "Código Rubrica" (col3 no exemplo),
    não de um cabeçalho horizontal — esse é o ponto central deste leiaute.

    Retorna: (linha_dados, dict_colunas)
      linha_dados  → índice da primeira linha de dados
      dict_colunas → {col_tipo, col_emp, col_rubrica, col_valor}
    """
    for i in range(len(df) - 1):
        linha_a = [normalizar(x) for x in df.iloc[i].tolist()]
        linha_b = [normalizar(x) for x in df.iloc[i + 1].tolist()]

        # Combina as duas linhas célula a célula para detectar cabeçalhos duplos
        combinadas = [f"{a} {b}".strip() for a, b in zip(linha_a, linha_b)]

        col_tipo    = None
        col_emp     = None
        col_rubrica = None
        col_valor   = None

        for col, comb in enumerate(combinadas):
            a = linha_a[col]
            b = linha_b[col]

            if col_tipo is None and (
                "tipo de calculo" in comb
                or (a == "tipo de" and b == "calculo")
            ):
                col_tipo = col
                continue

            if col_emp is None and (
                "codigo folha" in comb
                or "codigo empregado" in comb
                or (a == "codigo" and b in ("folha", "empregado"))
            ):
                col_emp = col
                continue

            # "Código Rubrica" — marcador principal do Leiaute 2
            if col_rubrica is None and (
                "codigo rubrica" in comb
                or (a == "codigo" and b == "rubrica")
            ):
                col_rubrica = col
                continue

            # "Referência Valor" ou só "Referência" / "Valor"
            if col_valor is None and (
                "referencia valor" in comb
                or "referencia" in comb
                or b in ("valor", "referencia")
                or a in ("referencia", "valor")
            ):
                col_valor = col
                continue

        # Cabeçalho válido: precisa de tipo + empregado + rubrica + valor
        if None not in (col_tipo, col_emp, col_rubrica, col_valor):
            return i + 2, {          # i+2 → pula as duas linhas de cabeçalho
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
    """
    Leiaute 2 — cada linha da planilha é um evento de um colaborador.
    A rubrica vem da coluna 'Código Rubrica' (não do cabeçalho horizontal).
    Gera apenas Registro 10. Linhas com valor vazio ou zero são ignoradas.
    """
    linha_dados, cols = localizar_cabecalho_vertical(df)

    col_tipo    = cols["col_tipo"]
    col_emp     = cols["col_emp"]
    col_rubrica = cols["col_rubrica"]   # ← ponto central do Leiaute 2
    col_valor   = cols["col_valor"]

    log.append(
        f"Colunas detectadas → "
        f"tipo:{col_tipo} | emp:{col_emp} | rubrica:{col_rubrica} | valor:{col_valor}"
    )

    linhas_saida  = []
    qtd_normais   = 0
    qtd_ignoradas = 0

    for i in range(linha_dados, len(df)):
        row = df.iloc[i].tolist()
        if linha_vazia(row):
            continue

        tpcalc  = so_numeros(row[col_tipo])    if col_tipo    < len(row) else ""
        cod_emp = so_numeros(row[col_emp])     if col_emp     < len(row) else ""
        # Rubrica lida diretamente da célula da linha — diferencial do Leiaute 2
        rubrica = so_numeros(row[col_rubrica]) if col_rubrica < len(row) else ""
        valor   = valor_para_layout(row[col_valor], 9) if col_valor < len(row) else ""

        # Ignora linhas sem tipo de cálculo ou sem código de empregado
        if not tpcalc or not cod_emp:
            continue

        # Ignora linhas sem código de rubrica
        if not rubrica:
            continue

        # Ignora linhas com valor vazio ou zero
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
        qtd_normais += 1

    if qtd_ignoradas:
        log.append(f"Linhas ignoradas (valor vazio/zero): {qtd_ignoradas}")

    return linhas_saida, qtd_normais, 0   # 0 = sem eventos de saúde neste leiaute


# ==============================
# PROCESSAMENTO PRINCIPAL
# ==============================
def processar_bytes(arquivo_bytes, log):
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

        # ── Roteamento por leiaute detectado ───────────────────────────────
        if leiaute_chave == "importacao_arquivo_texto_lancamentos":
            linhas_saida, qtd_normais, qtd_saude = processar_leiaute_horizontal(
                df, layout, cod_empresa, competencia, log
            )

        elif leiaute_chave == "relacao_valores_vertical":
            linhas_saida, qtd_normais, qtd_saude = processar_leiaute_vertical(
                df, layout, cod_empresa, competencia, log
            )

        else:
            raise ValueError(f"Leiaute '{leiaute_chave}' sem processador definido.")
        # ───────────────────────────────────────────────────────────────────

        log.append(f"Eventos normais : {qtd_normais}")
        log.append(f"Eventos saúde   : {qtd_saude}")
        log.append(f"Total de linhas : {len(linhas_saida)}")

        return linhas_saida, {"empresa": cod_empresa, "competencia": competencia}

    except Exception as e:
        log.append(f"ERRO: {e}")
        return None, None


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

    # ---------- cabeçalho ----------
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
                O leiaute é identificado <b>automaticamente</b>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- sidebar ----------
    with st.sidebar:
        st.markdown("### 📥 Modelos de Planilha")
        st.markdown(
            "Baixe o modelo correspondente ao seu tipo de lançamento "
            "e importe no **Domínio Sistemas**."
        )

        bgr_sem = carregar_bgr_bytes("bgr_base64_sem_plano.txt")
        if bgr_sem is not None:
            st.download_button(
                label="⬇ Relação De Valores — Sem Plano.bgr",
                data=bgr_sem,
                file_name="Relação De Valores Para Folha De Pagamento - Sem plano.bgr",
                mime="application/octet-stream",
                use_container_width=True,
                key="btn_bgr_sem_plano",
            )
        else:
            st.info("Modelo 'Sem Plano' indisponível.")

        bgr_com = carregar_bgr_bytes("bgr_base64_com_plano.txt")
        if bgr_com is not None:
            st.download_button(
                label="⬇ Relação De Valores — Com Plano.bgr",
                data=bgr_com,
                file_name="Relação De Valores Para Folha De Pagamento - Com plano.bgr",
                mime="application/octet-stream",
                use_container_width=True,
                key="btn_bgr_com_plano",
            )
        else:
            st.info("Modelo 'Com Plano' indisponível.")

        st.markdown("---")
        st.markdown("### ℹ Sobre")
        st.markdown(f"**Versão:** {VERSAO}")
        st.markdown("**Thomson Reuters**")
        st.markdown("**Domínio Sistemas**")

    # ---------- instruções ----------
    with st.expander("📖 **Instruções de Uso** — clique para expandir", expanded=False):
        st.markdown(
            """
            <div class="instrucoes-box">

            <h4>🔹 Leiautes suportados</h4>
            <ul>
                <li><b>Leiaute 1 — Horizontal</b>: eventos em colunas, gerado pelo
                    Domínio via <code>.bgr</code>. Suporta plano de saúde
                    (registros 10 + 20 + 25).</li>
                <li><b>Leiaute 2 — Vertical (V2)</b>: cada linha é um evento;
                    colunas fixas <em>Tipo de Cálculo | Código Folha | Nome |
                    Código Rubrica | Descrição Rubrica | Referência/Valor</em>.
                    Aceita <code>.xls</code> e <code>.xlsx</code>.
                    Gera apenas Registro 10.</li>
            </ul>
            <p>O sistema identifica o leiaute <b>automaticamente</b> ao carregar o arquivo.</p>

            <h4>🔹 Passo 1 — Baixar o modelo de planilha</h4>
            <p>No menu lateral, escolha o modelo adequado:</p>
            <ul>
                <li><b>Sem Plano</b> → lançamentos sem plano de saúde.</li>
                <li><b>Com Plano</b> → lançamentos com plano de saúde
                    (gera registros 10 + 20 + 25).</li>
            </ul>

            <h4>🔹 Passo 2 — Importar o modelo no Domínio Sistemas</h4>
            <ol>
                <li>Abra o <b>Domínio Sistemas / Folha</b>.</li>
                <li>Acesse <b>Utilitários → Gerador de Relatórios → Importar</b>.</li>
                <li>Selecione o arquivo <code>.bgr</code> baixado.</li>
            </ol>

            <h4>🔹 Passo 3 — Preencher e exportar a planilha</h4>
            <ol>
                <li>Execute o relatório no Domínio com a empresa e competência desejadas.</li>
                <li>Exporte o resultado em formato <b>Excel (.xlsx ou .xls)</b>.</li>
            </ol>

            <h4>🔹 Passo 4 — Gerar o arquivo TXT</h4>
            <ol>
                <li>Faça o <b>upload</b> do Excel exportado.</li>
                <li>Clique em <b>▶ Gerar arquivo TXT</b>.</li>
                <li>Baixe o arquivo gerado com o botão <b>⬇ Baixar arquivo TXT</b>.</li>
            </ol>

            <h4>🔹 Passo 5 — Importar no Domínio</h4>
            <p>Folha → <b>Utilitários → Importação → de Arquivo Texto →
            De Lançamentos</b>.</p>

            <hr>

            <h4>⚠ Observações</h4>
            <ul>
                <li>Eventos de plano de saúde (Leiaute 1) geram registros
                    <b>10 + 20 + 25</b> com valor acumulado (titular + dependentes).</li>
                <li>Eventos normais geram apenas o registro <b>10</b>.</li>
                <li>Linhas com <b>valor vazio ou zero</b> são ignoradas automaticamente.</li>
                <li>O arquivo de saída é codificado em <b>UTF-8</b>.</li>
            </ul>

            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ---------- estado ----------
    if "log_conv"  not in st.session_state:
        st.session_state.log_conv  = [f"Aplicação pronta. Versão: {VERSAO}"]
    if "txt_conv"  not in st.session_state:
        st.session_state.txt_conv  = None
    if "nome_conv" not in st.session_state:
        st.session_state.nome_conv = "Eventos.txt"

    # ---------- upload ----------
    arquivo = st.file_uploader(
        "Excel de origem (.xlsx ou .xls)",
        type=["xlsx", "xls"],
        help=(
            "Leiaute 1 (horizontal, eventos em colunas) ou "
            "Leiaute 2 V2 (vertical, uma linha por evento). "
            "O formato é detectado automaticamente."
        ),
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
        st.session_state.log_conv  = ["Campos limpos."]
        st.session_state.txt_conv  = None
        st.session_state.nome_conv = "Eventos.txt"
        st.rerun()

    if gerar and arquivo is not None:
        st.session_state.log_conv  = ["Iniciando processamento..."]
        st.session_state.txt_conv  = None
        st.session_state.nome_conv = "Eventos.txt"

        linhas, meta = processar_bytes(arquivo.read(), st.session_state.log_conv)

        if linhas and meta:
            conteudo = "\n".join(linhas) + "\n"
            st.session_state.txt_conv  = conteudo.encode("utf-8", errors="replace")
            emp  = meta["empresa"]
            comp = meta["competencia"]
            st.session_state.nome_conv = f"{emp}_Eventos_{comp}.txt"
            st.session_state.log_conv.append("Arquivo TXT gerado com sucesso.")

        st.rerun()

    # ---------- download do TXT ----------
    if st.session_state.txt_conv is not None:
        st.success("✅ Arquivo gerado com sucesso!")
        st.download_button(
            label="⬇ Baixar arquivo TXT",
            data=st.session_state.txt_conv,
            file_name=st.session_state.nome_conv,
            mime="text/plain",
            use_container_width=True,
            type="primary",
        )

    # ---------- métricas ----------
    log = st.session_state.log_conv
    normais = saude = total = None
    for linha in log:
        if "Eventos normais" in linha:
            try: normais = int(linha.split(":")[-1].strip())
            except Exception: pass
        if "Eventos saúde" in linha:
            try: saude = int(linha.split(":")[-1].strip())
            except Exception: pass
        if "Total de linhas" in linha:
            try: total = int(linha.split(":")[-1].strip())
            except Exception: pass

    if normais is not None:
        c1, c2, c3 = st.columns(3)
        c1.metric("Eventos normais", normais)
        c2.metric("Eventos saúde",   saude)
        c3.metric("Total de linhas", total)

    # ---------- log ----------
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
