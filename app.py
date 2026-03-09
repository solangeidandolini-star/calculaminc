import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO E SUPORTE ---
st.set_page_config(page_title="Simulador Salarial IPHAN", layout="wide", page_icon="🏛️")

def formatar_br(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try: return float(v)
        except: return 0.0
    return float(valor) if valor is not None else 0.0

# --- 2. CÁLCULOS TRIBUTÁRIOS ---
def calcular_irpf(base_mensal, cenario_nome):
    if base_mensal <= 2259.20: bruto, aliq = 0.0, 0.0
    elif base_mensal <= 2828.65: bruto, aliq = (base_mensal * 0.075) - 169.44, 7.5
    elif base_mensal <= 3751.05: bruto, aliq = (base_mensal * 0.15) - 381.44, 15.0
    elif base_mensal <= 4664.68: bruto, aliq = (base_mensal * 0.225) - 662.77, 22.5
    else: bruto, aliq = (base_mensal * 0.275) - 896.00, 27.5
    
    reducao = 0.0
    if "2026" in cenario_nome or "PL" in cenario_nome:
        if base_mensal <= 5000.00: reducao = min(312.89, bruto)
        elif base_mensal <= 7350.00: reducao = max(0.0, min(978.62 - (0.133145 * base_mensal), bruto))
    
    return max(0.0, bruto - reducao), aliq, reducao

# --- 3. CARREGAMENTO DOS DADOS ---
@st.cache_data
def carregar_dados():
    niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
    sufixos = {"-2025": "Vigente 2025", "-2026": "Vigente 2026", "-PL": "Proposta PL"}
    dfs = []
    for nome_n, prefixo in niveis.items():
        for suf, cenario in sufixos.items():
            path = f"tabela_{prefixo}{suf}.csv"
            if os.path.exists(path):
                df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
                df['nivel_ref'] = nome_n
                df['cenario_ref'] = cenario
                for col in ['vb', 'gdac_80', 'gdac_100', 'gdac_50']:
                    if col in df.columns: df[col] = df[col].apply(limpar_valor)
                dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else None

df_total = carregar_dados()

# --- 4. BARRA LATERAL ---
st.sidebar.header("⚙️ Parâmetros")
vinculo = st.sidebar.radio("Situação", ["Ativo", "Aposentado/Pensionista"])
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])

if df_total is not None:
    df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
    
    cenarios_ordem = ["Vigente 2025", "Vigente 2026", "Proposta PL"]
    cenario_foco = st.sidebar.selectbox("Cenário para Detalhamento (Aba 1)", cenarios_ordem)
    
    classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
    padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))

    st.sidebar.markdown("---")
    func_input = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01, format="%.2f")
    saude_input = st.sidebar.number_input("Ressarcimento Saúde (R$)", min_value=0.0, step=0.01, format="%.2f")

    pre_input = 0.0
    if vinculo == "Ativo":
        pontos = st.sidebar.select_slider("Pontos GDAC", [80, 100], 100)
        if st.sidebar.checkbox("Auxílio Pré-Escolar (+484,90)"): pre_input = 484.90
    else:
        pontos = 50

    # --- 5. CÁLCULO ---
    def calcular(nome_cenario):
        try:
            linha = df_nivel[(df_nivel['cenario_ref'] == nome_cenario) & 
                             (df_nivel['classe'] == classe_sel) & 
                             (df_nivel['padrao'] == padrao_sel)].iloc[0]
            vb = linha['vb']
            gdac = linha['gdac_80'] if pontos == 80 else (linha['gdac_100'] if pontos == 100 else linha['gdac_50'])
            alim = 1175.0 if vinculo == "Ativo" else 0.0
            
            # Base do IR inclui apenas VB + GDAC + FUNÇÃO
            base_irpf = vb + gdac + func_input
            ir_v, aliq_v, red_v = calcular_irpf(base_irpf, nome_cenario)
            
            # Bruto Total
            bruto_v = vb + gdac + alim + func_input + pre_input + saude_input
            
            return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func_input, "PRE": pre_input, 
                    "SAUDE": saude_input, "BRUTO": bruto_v, "IR": ir_v, "LIQ": bruto_v - ir_v, "RED": red_v, "ALIQ": aliq_v}
        except: return None

    res_25 = calcular("Vigente 2025")
    res_26 = calcular("Vigente 2026")
    res_pl = calcular("Proposta PL")

    # --- 6. INTERFACE ---
    st.title("🏛️ Simulador Salarial MINC/IPHAN")

    tab1, tab2 = st.tabs(["🎯 Calculadora Individual", "⚖️ Comparativo Cronológico"])

    with tab1:
        res = {"Vigente 2025": res_25, "Vigente 2026": res_26, "Proposta PL": res_pl}[cenario_foco]
        
        if res:
            st.subheader(f"Detalhamento: {cenario_foco}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Bruto Total", f"R$ {formatar_br(res['BRUTO'])}")
            m2.metric("IRPF Retido", f"R$ {formatar_br(res['IR'])}", 
                      delta=f"- R$ {formatar_br(res['RED'])}" if res['RED'] > 0 else None, delta_color="inverse")
            m3.metric("Líquido Estimado", f"R$ {formatar_br(res['LIQ'])}")
            
            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Composição da Remuneração:**")
                st.write(f"Vencimento Básico: **R$ {formatar_br(res['VB'])}**")
                st.write(f"GDAC ({pontos} pts): **R$ {formatar_br(res['GDAC'])}**")
                if res['ALIM'] > 0:
                    st.write(f"Auxílio Alimentação: **R$ {formatar_br(res['ALIM'])}**")
                
                # --- AQUI ESTAVA O PROBLEMA: ADICIONADAS AS VARIÁVEIS EXTERNAS ---
                if res['FUNC'] > 0:
                    st.write(f"Função Comissionada: **R$ {formatar_br(res['FUNC'])}**")
                if res['PRE'] > 0:
                    st.success(f"Auxílio Pré-Escolar: **R$ {formatar_br(res['PRE'])}**")
                if res['SAUDE'] > 0:
                    st.write(f"Ressarcimento Saúde: **R$ {formatar_br(res['SAUDE'])}**")

            with col_b:
                st.write("**Tributação:**")
                st.write(f"Alíquota Aplicada: **{res['ALIQ']}%**")
                if res['RED'] > 0:
                    st.info(f"Redução Lei 15.270: **R$ {formatar_br(res['RED'])}**")
        else:
            st.error("Dados não encontrados.")

    with tab2:
        st.subheader("Evolução: 2025 ➔ 2026 ➔ PL")
        if res_25 and res_26 and res_pl:
            # Soma das rubricas variáveis para simplificar a tabela
            def soma_vars(r): return r['ALIM'] + r['FUNC'] + r['PRE'] + r['SAUDE']
            
            tabela = [
                ["Vencimento Básico", formatar_br(res_25['VB']), formatar_br(res_26['VB']), formatar_br(res_pl['VB'])],
                ["GDAC", formatar_br(res_25['GDAC']), formatar_br(res_26['GDAC']), formatar_br(res_pl['GDAC'])],
                ["Auxílios / Função / Saúde", formatar_br(soma_vars(res_25)), formatar_br(soma_vars(res_26)), formatar_br(soma_vars(res_pl))],
                ["---", "---", "---", "---"],
                ["TOTAL BRUTO", formatar_br(res_25['BRUTO']), formatar_br(res_26['BRUTO']), formatar_br(res_pl['BRUTO'])],
                ["IRPF Retido", f"- {formatar_br(res_25['IR'])}", f"- {formatar_br(res_26['IR'])}", f"- {formatar_br(res_pl['IR'])}"],
                ["LÍQUIDO FINAL", f"**{formatar_br(res_25['LIQ'])}**", f"**{formatar_br(res_26['LIQ'])}**", f"**{formatar_br(res_pl['LIQ'])}**"]
            ]
            st.table(pd.DataFrame(tabela, columns=["Item", "Atual (2025)", "Vigente (2026)", "Proposta PL"]))
            
            ganho_total = res_pl['LIQ'] - res_25['LIQ']
            st.success(f"📈 Ganho Acumulado (Hoje ➔ PL): **R$ {formatar_br(ganho_total)}**")
