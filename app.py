import os
import re
import io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
import pandas as pd
import streamlit as st

# ==============================
# VERSÃO
# ==============================
VERSAO = "V1.0"

# ==============================
# TEMA (espelho do RPA)
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
    "importacao_arquivo_texto_lancamentos": {
        "nome": "Importação Arquivo Texto | De Lançamentos",
        "detector": {
            "cabecalho": ["tipo de", "codigo", "competencia", "codigo empresa"],
            "marcadores": ["folha", "colaboradores"],
        },
        "registros": {
            "10": [
                ("fixo",       2,  "10"),
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
                ("fixo",               2, "25"),
                ("tipo_beneficiario",  1),
                ("codigo_beneficiario",10),
                ("valor",              9),
            ],
        },
    }
}


def detectar_leiaute(df):
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
                score += 1
        if score > melhor_score:
            melhor_score, melhor = score, chave
    if not melhor or melhor_score <= 0:
        raise ValueError("Não foi possível identificar automaticamente o leiaute da planilha.")
    return melhor


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
# LEITURA EXCEL
# ==============================
def carregar_excel(arquivo_bytes):
    # Tenta xlsx primeiro, depois xls
    try:
        df = pd.read_excel(io.BytesIO(arquivo_bytes), sheet_name=0, header=None, dtype=object)
    except Exception:
        df = pd.read_excel(io.BytesIO(arquivo_bytes), sheet_name=0, header=None,
                           dtype=object, engine="xlrd")
    return df.fillna("")


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
        if col_tipo is None and ("tipo de calculo" in combinado or (a == "tipo de" and b == "calculo")):
            col_tipo = col; continue
        if col_emp is None and ("codigo empregado" in combinado or "codigo folha" in combinado
                                or (a == "codigo" and b in ("empregado", "folha"))):
            col_emp = col; continue
        if col_dep is None and ("codigo dependente" in combinado or (a == "codigo" and b == "dependente")):
            col_dep = col; continue
        if col_nome is None and ("nome dos colaboradores" in combinado or (a == "nome dos" and b == "colaboradores")):
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

        linhas_saida   = []
        ultimo_empregado = ""
        total_saude    = defaultdict(int)
        reg10_saude    = {}
        reg20_saude    = {}
        reg25_saude    = defaultdict(list)
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
                    # ---- plano de saúde ----
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
                    reg25_saude[chave].append(
                        montar_registro(layout, "25", {
                            "tipo_beneficiario":   "D" if cod_dep else "T",
                            "codigo_beneficiario": cod_dep if cod_dep else cod_emp,
                            "valor": valor,
                        })
                    )
                    qtd_saude += 1

                else:
                    # ---- evento normal ----
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

        # grava registros de saúde ao final (valor total acumulado)
        for chave in reg10_saude:
            linhas_saida.append(reg10_saude[chave])
            linhas_saida.append(reg20_saude[chave])
            for r25 in reg25_saude[chave]:
                linhas_saida.append(r25)

        log.append(f"Eventos normais : {qtd_normais}")
        log.append(f"Eventos saúde   : {qtd_saude}")
        log.append(f"Total de linhas : {len(linhas_saida)}")

        return linhas_saida, {
            "empresa":    cod_empresa,
            "competencia": competencia,
        }

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

    # ---- cabeçalho ----
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
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- sidebar ----
    with st.sidebar:
        st.markdown("### ℹ Sobre")
        st.markdown(f"**Versão:** {VERSAO}")
        st.markdown("**Thomson Reuters**")
        st.markdown("**Domínio Sistemas**")
        st.markdown("---")
        st.markdown(
            "Converte a planilha de eventos (com ou sem plano de saúde) "
            "para o formato de importação do Domínio Folha."
        )

    # ---- instruções ----
    with st.expander("📖 **Instruções de Uso** — clique para expandir", expanded=False):
        st.markdown(
            """
            <div class="instrucoes-box">

            <h4>🔹 Passo 1 — Preparar a planilha</h4>
            <p>Use a planilha no formato padrão do Domínio com cabeçalho de duas linhas
            (Tipo de Cálculo, Código Empregado, Código Dependente, Nome dos Colaboradores
            e colunas de eventos a partir da coluna D).</p>

            <h4>🔹 Passo 2 — Plano de saúde (opcional)</h4>
            <p>Se houver eventos de plano de saúde, preencha a linha
            <b>Evento de Plano de Saúde</b> com <b>Sim</b> nas colunas correspondentes
            e a linha <b>CNPJ da Operadora</b> com o CNPJ de cada operadora.</p>

            <h4>🔹 Passo 3 — Gerar o TXT</h4>
            <ol>
                <li>Faça o upload do arquivo Excel.</li>
                <li>Clique em <b>▶ Gerar arquivo TXT</b>.</li>
                <li>Baixe o arquivo gerado.</li>
            </ol>

            <h4>🔹 Passo 4 — Importar no Domínio</h4>
            <p>No módulo Folha: <b>Utilitários → Importação → de Arquivo Texto →
            De Lançamentos</b>.</p>

            <hr>

            <h4>⚠ Observações</h4>
            <ul>
                <li>Eventos de plano de saúde geram registros <b>10 + 20 + 25</b>
                    com valor acumulado (titular + dependentes).</li>
                <li>Eventos normais geram apenas o registro <b>10</b>.</li>
                <li>O arquivo de saída é codificado em <b>UTF-8</b>.</li>
            </ul>

            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ---- estado ----
    if "log_conv"  not in st.session_state:
        st.session_state.log_conv  = [f"Aplicação pronta. Versão: {VERSAO}"]
    if "txt_conv"  not in st.session_state:
        st.session_state.txt_conv  = None
    if "nome_conv" not in st.session_state:
        st.session_state.nome_conv = "Eventos.txt"

    # ---- upload ----
    arquivo = st.file_uploader(
        "Excel de origem",
        type=["xlsx", "xls"],
        help="Planilha de eventos no formato padrão do Domínio Sistemas",
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

    # ---- download ----
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

    # ---- métricas (só quando há resultado) ----
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
        c1.metric("Eventos normais",  normais)
        c2.metric("Eventos saúde",    saude)
        c3.metric("Total de linhas",  total)

    # ---- log ----
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
