import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Consolidador GOINFRA Profissional", layout="wide")
st.title("📑 Consolidador de Histórico e Curva ABC")

uploaded_files = st.sidebar.file_uploader(
    "Carregue as medições (.xls ou .xlsx)",
    type=["xls", "xlsx"],
    accept_multiple_files=True
)

# ==============================
# Funções auxiliares
# ==============================

def extrair_id_medicao(file):
    try:
        file.seek(0)
        engine = "xlrd" if file.name.endswith(".xls") else "openpyxl"

        df_cabecalho = pd.read_excel(
            file,
            nrows=12,
            usecols="J",
            header=None,
            engine=engine
        )

        texto_j12 = str(df_cabecalho.iloc[11, 0]).strip()

        numeros = re.findall(r"(\d+)", texto_j12)

        if numeros:
            num = int(numeros[0])
            return num, f"BM_{num:02d}"

        return 999, "BM_Erro"

    except:
        return 999, "BM_Erro"


def formatar_br(valor):

    if pd.isna(valor) or valor == 0:
        return "0,00"

    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def carregar_planilha(file):

    file.seek(0)

    engine = "xlrd" if file.name.endswith(".xls") else "openpyxl"

    return pd.read_excel(file, skiprows=25, engine=engine)


# ==============================
# Processamento principal
# ==============================

if uploaded_files:

    processados = []

    for file in uploaded_files:

        ordem, label = extrair_id_medicao(file)

        processados.append({
            "file": file,
            "ordem": ordem,
            "label": label
        })

    processados = sorted(processados, key=lambda x: x["ordem"])

    # ==============================
    # 1. Estrutura base (última medição)
    # ==============================

    try:

        ultimo_item = processados[-1]

        df_m = carregar_planilha(ultimo_item["file"])

        linha_corte = df_m[
            df_m.iloc[:, 0]
            .astype(str)
            .str.contains("TOTAL MÃO-DE-OBRA", case=False, na=False)
        ].index

        if not linha_corte.empty:
            df_m = df_m.iloc[:linha_corte[0]]

        df_m.columns = [str(c).strip().upper() for c in df_m.columns]

        df_m = df_m.loc[:, ~df_m.columns.str.contains("UNNAMED|NAN", case=False)]

        c_cod = df_m.columns[0]
        c_serv = df_m.columns[1]

        c_unid = next((c for c in df_m.columns if "UNID" in c), df_m.columns[2])

        c_precu = next((c for c in df_m.columns if "UNIT" in c), df_m.columns[3])

        c_qtd_orc = next(
            (
                c for c in df_m.columns
                if "CONTRATADA" in c or "QTD. ORC" in c
            ),
            df_m.columns[4]
        )

        resultado = df_m[
            [c_cod, c_serv, c_unid, c_precu, c_qtd_orc]
        ].copy()

        resultado.columns = [
            "COD",
            "SERVICO",
            "UNID",
            "PRECO_UNIT",
            "QTD_ORC"
        ]

        resultado["ID_LINHA"] = resultado.index

    except Exception as e:

        st.error(f"Erro na estrutura mestre: {e}")

        st.stop()

    # ==============================
    # 2. Integração das medições
    # ==============================

    for item in processados:

        try:

            df_bm = carregar_planilha(item["file"])

            df_bm.columns = [str(c).strip().upper() for c in df_bm.columns]

            label = item["label"]

            cols_med = [
                c for c in df_bm.columns if "DA MEDIÇÃO" in c
            ]

            c_reaj = next(
                (
                    c for c in df_bm.columns
                    if "REAJUSTE" in c or "REAJUSTAMENTO" in c
                ),
                None
            )

            med_cols = pd.DataFrame(index=df_bm.index)

            if len(cols_med) >= 2:

                med_cols[f"QTD_{label}"] = pd.to_numeric(
                    df_bm[cols_med[0]],
                    errors="coerce"
                ).fillna(0)

                med_cols[f"VALOR_{label}"] = pd.to_numeric(
                    df_bm[cols_med[1]],
                    errors="coerce"
                ).fillna(0)

            if c_reaj:

                med_cols[f"REAJ_{label}"] = pd.to_numeric(
                    df_bm[c_reaj],
                    errors="coerce"
                ).fillna(0)

            med_cols["ID_LINHA"] = med_cols.index

            resultado = pd.merge(
                resultado,
                med_cols,
                on="ID_LINHA",
                how="left"
            )

        except Exception as e:

            st.warning(f"Erro ao processar {item['label']}: {e}")

    # ==============================
    # 3. Consolidação final
    # ==============================

    resultado = resultado.drop(columns=["ID_LINHA"]).fillna(0)

    c_qtds = [c for c in resultado.columns if "QTD_" in c]
    c_vals = [c for c in resultado.columns if "VALOR_" in c]
    c_reajs = [c for c in resultado.columns if "REAJ_" in c]

    resultado["QTD_ACUMULADA"] = resultado[c_qtds].sum(axis=1)

    resultado["VALOR_ACUMULADO"] = resultado[c_vals].sum(axis=1)

    resultado["REAJUSTE_ACUMULADO"] = resultado[c_reajs].sum(axis=1)

    resultado["TOTAL_GERAL"] = (
        resultado["VALOR_ACUMULADO"]
        + resultado["REAJUSTE_ACUMULADO"]
    )

    # ==============================
    # Tela histórico
    # ==============================

    st.subheader(
        f"✅ Histórico Consolidado ({len(processados)} medições)"
    )

    colunas_numericas = resultado.select_dtypes(
        include=["float64", "int64"]
    ).columns

    format_dict_br = {col: formatar_br for col in colunas_numericas}

    def format_rows(row):

        if row["PRECO_UNIT"] == 0:

            return [
                "background-color: #f0f2f6; font-weight: bold"
            ] * len(row)

        return [""] * len(row)

    st.dataframe(
        resultado
        .style
        .apply(format_rows, axis=1)
        .format(format_dict_br),
        use_container_width=True
    )

    # ==============================
    # Curva ABC
    # ==============================

    st.divider()

    st.subheader("📈 Análise Curva ABC")

    abc = resultado[resultado["PRECO_UNIT"] > 0].copy()

    abc = abc[abc["TOTAL_GERAL"] > 0.01]

    if not abc.empty:

        abc = abc.sort_values(
            by="TOTAL_GERAL",
            ascending=False
        )

        total_global_abc = max(
            abc["TOTAL_GERAL"].sum(),
            1
        )

        abc["%_SIMPLES"] = (
            abc["TOTAL_GERAL"]
            / total_global_abc
        ) * 100

        abc["%_ACUMULADO"] = abc["%_SIMPLES"].cumsum()

        def classificar_abc(p):

            if p <= 80:
                return "A"

            if p <= 95:
                return "B"

            return "C"

        abc["CLASSE"] = abc["%_ACUMULADO"].apply(classificar_abc)

        # métricas

        m1, m2, m3 = st.columns(3)

        m1.metric(
            "Total Serviços",
            f"R$ {formatar_br(total_global_abc)}"
        )

        m2.metric(
            "Total Reajuste",
            f"R$ {formatar_br(resultado['REAJUSTE_ACUMULADO'].sum())}"
        )

        m3.metric(
            "Itens Classe A",
            f"{len(abc[abc['CLASSE']=='A'])}"
        )

           # ==============================
    # Exportação
    # ==============================

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        resultado.to_excel(
            writer,
            sheet_name="Historico",
            index=False
        )

        if not abc.empty:

            abc.to_excel(
                writer,
                sheet_name="Curva_ABC",
                index=False
            )

    st.sidebar.divider()

    st.sidebar.download_button(
        "📥 Baixar Excel",
        output.getvalue(),
        "relatorio_goinfra.xlsx"
    )

    csv = resultado.to_csv(index=False).encode("utf-8")

    st.sidebar.download_button(
        "📥 Baixar CSV",
        csv,
        "relatorio_goinfra.csv",
        "text/csv"
    )
