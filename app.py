import streamlit as st
import pandas as pd
import os

# Configuração da página
st.set_page_config(page_title="Calculadora Salarial MINC/IPHAN", layout="wide")

# --- FUNÇÕES DE AUXÍLIO E FORMATAÇÃO ---

def limpar_valor(valor):
    """Converte valores do CSV para float."""
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try:
            return float(v)
        except ValueError:
            return 0.0
    return float(valor) if valor is not None else 0.0

def formatar_br(valor):
    """Formata float para o padrão brasileiro: 7.157,49"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- FUNÇÕES DE CÁLCULO DE IRPF (LEI 15.270/2025) ---

def aplicar_reducao_art3a(rendimento, imposto_bruto):
    if rendimento <= 5000.00:
        return min(312.89, imposto_bruto)
    elif 5000.00 < rendimento <= 7350.00:
        reducao = 978.62 - (0.133145 * rendimento)
        return max(0.0, min(reducao, imposto_bruto))
    return 0.0

def calcular_irpf_bruto(base_mensal):
    if base_mensal <= 2259.20:
        return 0.0, 0.0, 0.0
    elif base_mensal <= 2828.65:
        return (base_mensal * 0.075) - 169.44, 7.5, 169.44
    elif base_mensal <= 3751.05:
        return (base_mensal * 0.15) - 381.44, 15.0, 381.44
    elif base_mensal <= 4664.68:
        return (base_mensal * 0.225) - 662.77, 22.5, 662.77
    else:
        return (base_mensal * 0.275) - 896.00, 27.5, 896.00

# --- CARREGAMENTO DE DADOS (APENAS VERSÃO PL) ---

@st.cache_data
def carregar_dados_pl():
    # Mapeamento apenas para os arquivos da Versão Alternativa (PL)
    arquivos_pl = {
        "SUPERIOR": "tabela_superior(1).csv",
        "INTERMEDIÁRIO": "tabela_intermediario(1).csv",
        "AUXILIAR": "tabela_auxiliar(1).csv"
    }

    dfs = []
    cols_numericas = ['vb', 'gdac', 'gdac_80', 'gdac_100', 'auxilio_alimentacao', 'ativo_80', 'ativo_100']

    for nivel, path in arquivos_pl.items():
        if os.path.exists(path):
            temp_df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
            for col in cols_numericas:
                if col in temp_df.columns:
                    temp_df[col] = temp_df[col].apply(limpar_valor)

            temp_df['nivel_data'] = nivel
            dfs.append(temp_df)

    return pd.concat(dfs, ignore_index=True) if dfs else None

df_pl = carregar_dados_pl()

# --- INTERFACE ---

st.title("⚖️ Calculadora Salarial MINC/IPHAN")
st.subheader("Simulador: PL nº 5.874/2025 & Lei nº 15.270/2025")

if df_pl is None:
    st.error("Erro: Arquivos da Versão PL não encontrados (ex: tabela_superior(1).csv).")
    st.stop()

# Sidebar
st.sidebar.header("Configurações do Servidor")
st.sidebar.info("Utilizando: Versão do PL nº 5.874/2025")

nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])
ano_base = st.sidebar.radio("Ano Base para Cálculo", [2025, 2026])

df_filtrado = df_pl[df_pl['nivel_data'] == nivel_sel]

classe_sel = st.sidebar.selectbox("Classe", sorted(df_filtrado['classe'].unique(), reverse=True))
padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_filtrado[df_filtrado['classe'] == classe_sel]['padrao'].unique()))
pontos_gdac = st.sidebar.select_slider("Pontos GDAC", options=[80, 100], value=80)

tem_pre_escolar = st.sidebar.checkbox("Auxílio Pré-Escolar (+ R$ 321,00)")
valor_funcao = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=50.0)

# --- PROCESSAMENTO ---

def calcular_totais(row, ano):
    vb = float(row['vb'])
    gdac = float(row['gdac_80'] if pontos_gdac == 80 else row['gdac_100'])
    alim = float(row['auxilio_alimentacao'])
    pre = 321.00 if tem_pre_escolar else 0.0

    rendimento_mensal = vb + gdac + alim + valor_funcao + pre

    imp_bruto, aliq, deducao = calcular_irpf_bruto(rendimento_mensal)
    reducao = aplicar_reducao_art3a(rendimento_mensal, imp_bruto) if ano == 2026 else 0.0

    irpf_final = max(0.0, imp_bruto - reducao)
    return {
        "VB": vb, "GDAC": gdac, "Alim": alim, "Pre": pre, "Funcao": valor_funcao,
        "Mensal_Bruto": rendimento_mensal, "IR_Final": irpf_final,
        "Reducao": reducao, "Mensal_Liquido": rendimento_mensal - irpf_final, "Aliq": aliq
    }

try:
    # Filtro para as duas vigências dentro do PL
    row_25 = df_filtrado[(df_filtrado['classe'] == classe_sel) & (df_filtrado['padrao'] == padrao_sel) & (df_filtrado['vigencia'] == "01/01/2025")].iloc[0]
    row_26 = df_filtrado[(df_filtrado['classe'] == classe_sel) & (df_filtrado['padrao'] == padrao_sel) & (df_filtrado['vigencia'] == "01/04/2026")].iloc[0]

    res_25 = calcular_totais(row_25, 2025)
    res_26 = calcular_totais(row_26, 2026)
    res_atual = res_25 if ano_base == 2025 else res_26
except IndexError:
    st.error("Dados não encontrados para esta Classe/Padrão no arquivo do PL.")
    st.stop()

# --- EXIBIÇÃO ---

tab1, tab2 = st.tabs(["📊 Calculadora Mensal", "🔄 Comparativo Jan/25 vs Abr/26"])

with tab1:
    m1, m2, m3 = st.columns(3)
    m1.metric("Valor Mensal Bruto", f"R$ {formatar_br(res_atual['Mensal_Bruto'])}")
    m2.metric("IRPF Mensal Final", f"R$ {formatar_br(res_atual['IR_Final'])}",
              delta=f"-R$ {formatar_br(res_atual['Reducao'])}" if ano_base == 2026 and res_atual['Reducao'] > 0 else None, delta_color="inverse")
    m3.metric("Valor Mensal Líquido", f"R$ {formatar_br(res_atual['Mensal_Liquido'])}")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.info("**Composição do Rendimento**")
        st.write(f"Vencimento Básico: R$ {formatar_br(res_atual['VB'])}")
        st.write(f"GDAC ({pontos_gdac} pts): R$ {formatar_br(res_atual['GDAC'])}")
        st.write(f"Auxílio Alimentação: R$ {formatar_br(res_atual['Alim'])}")
        if valor_funcao > 0: st.write(f"Função: R$ {formatar_br(valor_funcao)}")
        if tem_pre_escolar: st.write(f"Pré-Escolar: R$ 321,00")
        st.markdown(f"**Total Mensal Bruto: R$ {formatar_br(res_atual['Mensal_Bruto'])}**")

    with c2:
        st.warning("**Detalhamento IRPF**")
        st.write(f"Alíquota Aplicada: {res_atual['Aliq']}%")
        if ano_base == 2026:
            st.success(f"Redução Lei 15.270: R$ {formatar_br(res_atual['Reducao'])}")
        else:
            st.write("Redução 2026: R$ 0,00 (Ano base 2025)")
        st.markdown(f"**Retenção Final de IR: R$ {formatar_br(res_atual['IR_Final'])}**")

with tab2:
    st.markdown("### Comparativo de Rendimentos (Base PL nº 5.874/2025)")
    comp_df = pd.DataFrame({
        "Rubrica": ["Vencimento Básico", "GDAC", "Auxílio Alimentação", "Valor Mensal Bruto", "IRPF Final", "Valor Mensal Líquido"],
        "Jan/2025 (R$)": [formatar_br(res_25['VB']), formatar_br(res_25['GDAC']), formatar_br(res_25['Alim']), formatar_br(res_25['Mensal_Bruto']), formatar_br(res_25['IR_Final']), formatar_br(res_25['Mensal_Liquido'])],
        "Abr/2026 (R$)": [formatar_br(res_26['VB']), formatar_br(res_26['GDAC']), formatar_br(res_26['Alim']), formatar_br(res_26['Mensal_Bruto']), formatar_br(res_26['IR_Final']), formatar_br(res_26['Mensal_Liquido'])]
    })
    st.table(comp_df)

# --- RODAPÉ ---
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; font-size: 0.85em;'>"
    "Elaboração: GT de Elaboração de Emendas e Comando de Acompanhamento da Negociação"
    "</div>",
    unsafe_allow_html=True
)
