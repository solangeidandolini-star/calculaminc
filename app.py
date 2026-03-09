import streamlit as st
import pandas as pd
import os

# 1. Configuração da Página
st.set_page_config(page_title="Calculadora Salarial MINC/IPHAN", page_icon="🔍", layout="wide")

# --- FUNÇÕES DE SUPORTE ---

def limpar_valor(valor):
    """Trata strings monetárias e converte para float."""
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try:
            return float(v)
        except ValueError:
            return 0.0
    return float(valor) if valor is not None else 0.0

def formatar_br(valor):
    """Formata para o padrão brasileiro: 1.234,56"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- CÁLCULO DE IRPF (LEI 15.270/2025) ---

def aplicar_reducao_art3a(rendimento, imposto_bruto):
    if rendimento <= 5000.00:
        return min(312.89, imposto_bruto)
    elif 5000.00 < rendimento <= 7350.00:
        reducao = 978.62 - (0.133145 * rendimento)
        return max(0.0, min(reducao, imposto_bruto))
    return 0.0

def calcular_irpf_bruto(base_mensal):
    if base_mensal <= 2259.20: return 0.0, 0.0, 0.0
    elif base_mensal <= 2828.65: return (base_mensal * 0.075) - 169.44, 7.5, 169.44
    elif base_mensal <= 3751.05: return (base_mensal * 0.15) - 381.44, 15.0, 381.44
    elif base_mensal <= 4664.68: return (base_mensal * 0.225) - 662.77, 22.5, 662.77
    else: return (base_mensal * 0.275) - 896.00, 27.5, 896.00

# --- CARREGAMENTO DOS DADOS ---

@st.cache_data
def carregar_dados_pl():
    arquivos = {
        "SUPERIOR": "tabela_superior(1).csv",
        "INTERMEDIÁRIO": "tabela_intermediario(1).csv",
        "AUXILIAR": "tabela_auxiliar(1).csv"
    }
    
    colunas_padrao = ['classe', 'padrao', 'vb', 'gdac_unit', 'gdac_80', 'gdac_100', 'alim', 'ativo_80', 'ativo_100', 'gdac_50', 'apo_50']
    dfs_finais = []
    
    for nivel, path in arquivos.items():
        if os.path.exists(path):
            try:
                # Seus arquivos usam vírgula (,) e possuem uma linha de título no topo
                df_raw = pd.read_csv(path, sep=',', encoding='utf-8-sig', skiprows=1)
                
                # Se ler errado (apenas 1 coluna), tenta ponto e vírgula
                if df_raw.shape[1] < 10:
                    df_raw = pd.read_csv(path, sep=';', encoding='utf-8-sig', skiprows=1)

                # Parte 2025 (Colunas 0 a 10)
                df_25 = df_raw.iloc[:, 0:11].copy()
                df_25.columns = colunas_padrao
                df_25['vigencia'] = "2025"
                df_25['nivel_data'] = nivel
                
                # Parte 2026 (Colunas 12 a 22)
                df_26 = df_raw.iloc[:, 12:23].copy()
                df_26.columns = colunas_padrao
                df_26['vigencia'] = "2026"
                df_26['nivel_data'] = nivel
                
                for df in [df_25, df_26]:
                    for col in ['vb', 'gdac_80', 'gdac_100', 'alim']:
                        df[col] = df[col].apply(limpar_valor)
                    dfs_finais.append(df)
            except Exception as e:
                print(f"Erro no arquivo {path}: {e}")
                
    return pd.concat(dfs_finais, ignore_index=True) if dfs_finais else None

# Inicialização global da variável para evitar NameError
df_pl = carregar_dados_pl()

# --- INTERFACE ---



st.title("🔍 Calculadora Salarial MINC/IPHAN")
st.subheader("Simulador de valores com base PL nº 5.874/2025")

if df_pl is None:
    st.error("Arquivos CSV não encontrados ou erro na leitura. Verifique se os nomes dos arquivos no GitHub estão corretos.")
    st.stop()

# Sidebar
st.sidebar.header("Configuração")
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])
ano_base = st.sidebar.radio("Ano de Referência", ["2025", "2026"])

# Filtro
df_filtrado = df_pl[df_pl['nivel_data'] == nivel_sel]
classes = sorted(df_filtrado['classe'].unique(), reverse=True)
classe_sel = st.sidebar.selectbox("Classe", classes)

padroes = sorted(df_filtrado[df_filtrado['classe'] == classe_sel]['padrao'].unique())
padrao_sel = st.sidebar.selectbox("Padrão", padroes)

pontos_gdac = st.sidebar.select_slider("Pontos GDAC", options=[80, 100], value=100)

valor_funcao = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=100.0)
tem_pre = st.sidebar.checkbox("Auxílio Pré-Escolar (+ R$ 321,00)")

# --- CÁLCULO ---

try:
    dados = df_filtrado[(df_filtrado['classe'] == classe_sel) & 
                        (df_filtrado['padrao'] == padrao_sel) & 
                        (df_filtrado['vigencia'] == ano_base)].iloc[0]
    
    vb = dados['vb']
    gdac = dados['gdac_80'] if pontos_gdac == 80 else dados['gdac_100']
    alim = dados['alim']
    pre = 321.0 if tem_pre else 0.0
    
    bruto = vb + gdac + alim + valor_funcao + pre
    imp_bruto, aliq, _ = calcular_irpf_bruto(bruto)
    reducao = aplicar_reducao_art3a(bruto, imp_bruto) if ano_base == "2026" else 0.0
    ir_final = max(0.0, imp_bruto - reducao)
    liquido = bruto - ir_final

    # Resultados
    m1, m2, m3 = st.columns(3)
    m1.metric("Bruto Mensal", f"R$ {formatar_br(bruto)}")
    m2.metric("IRPF Retido", f"R$ {formatar_br(ir_final)}", 
              delta=f"-R$ {formatar_br(reducao)}" if reducao > 0 else None, delta_color="inverse")
    m3.metric("Líquido Estimado", f"R$ {formatar_br(liquido)}")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Vencimento Básico:** R$ {formatar_br(vb)}")
        st.write(f"**GDAC ({pontos_gdac} pts):** R$ {formatar_br(gdac)}")
        st.write(f"**Auxílio Alimentação:** R$ {formatar_br(alim)}")
    with c2:
        st.write(f"**Alíquota IRPF:** {aliq}%")
        if ano_base == "2026":
            st.write(f"**Redução Lei 15.270:** R$ {formatar_br(reducao)}")

except Exception as e:
    st.info("Aguardando seleção de dados na barra lateral.")

# Rodapé
st.markdown("---")
st.markdown("<div style='text-align: center; color: #666; font-size: 0.85em;'>Elaboração: GT de Elaboração de Emendas e Comando de Acompanhamento da Negociação</div>", unsafe_allow_html=True)
