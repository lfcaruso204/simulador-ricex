import streamlit as st
import pandas as pd
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
import io
import os
import numpy as np

# 1. SETUP E ESTILO
st.set_page_config(page_title="Ricex - Gestão de Lotes", layout="wide")
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 28px !important; color: #31333F; }
    .main .block-container { padding: 2rem; }
    [data-testid="stSidebar"] .stNumberInput label { font-size: 12px !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. HEADER
c_logo, c_tit = st.columns([1, 4])
with c_logo:
    if os.path.exists('Ricex.png'): st.image('Ricex.png', width=100)
with c_tit:
    st.title("Gestão de Lotes de Importação")

cid1, cid2 = st.columns(2)
lote_nome = cid1.text_input("📦 Identificação do Lote", "Lote_Analise_Ricex")
data_analise = cid2.date_input("📅 Data da Análise", date.today())

st.markdown("---")
arquivo_upload = st.file_uploader("📂 Arraste o arquivo Excel aqui (Aba: 'analise')", type=["xlsx"])

if arquivo_upload is not None:
    try:
        # 3. PROCESSAMENTO INICIAL
        df_orig = pd.read_excel(arquivo_upload, sheet_name='analise')
        df_orig = df_orig.dropna(subset=['NomeProduto'])
        df_orig = df_orig[df_orig['NomeProduto'].astype(str).str.lower() != 'inserir sku']
        
        def clean_price(val):
            if isinstance(val, str):
                return float(val.replace('R$', '').replace('€', '').replace('.', '').replace(',', '.').strip())
            return float(val)

        # --- SIDEBAR (PARÂMETROS) ---
        st.sidebar.header("⚙️ Parâmetros")
        c1, c2 = st.sidebar.columns(2)
        cambio = c1.number_input("Câmbio (€/R$)", value=6.30)
        frete_p = c2.number_input("Frete (%)", value=3.0) / 100
        
        # VARIÁVEL INSERÍVEL: Garrafas por Caixa
        qtde = st.sidebar.number_input("Garrafas por Caixa (un)", value=6, min_value=1, step=1)
        col_custo_cx = f"Custo da Caixa x {qtde}"
        
        st.sidebar.markdown("---")
        
        st.sidebar.subheader("📥 Impostos Compra")
        ci1, ci2 = st.sidebar.columns(2)
        IPI_C = ci1.number_input("IPI (%)", value=6.5, key="ipi_c") / 100
        PISCOF_C = ci2.number_input("PIS/COF (%)", value=11.75, key="pc_c") / 100
        DESP_C = st.sidebar.number_input("Desp. (%)", value=2.0, key="desp_c") / 100
        
        st.sidebar.subheader("📤 Impostos Venda")
        cv1, cv2 = st.sidebar.columns(2)
        icms_v_p = cv1.number_input("ICMS (%)", value=8.0, key="icms_v") / 100
        IPI_V = cv2.number_input("IPI (%)", value=6.5, key="ipi_v") / 100
        COMIS = st.sidebar.number_input("Comis. (%)", value=6.5, key="comis_v") / 100
        
        st.sidebar.markdown("---")
        
        margem_alvo = st.sidebar.slider("Margem Alvo (%)", 0.0, 60.0, 20.0) / 100
        preco_teto = st.sidebar.number_input("Preço Teto por Caixa (R$)", value=5000.0)
        ajustar_auto = st.sidebar.checkbox("🔄 Ajustar Margens ao Teto")

        # Preparação do custo dinâmico
        df_orig['Custo Unit. Ext'] = df_orig['Custo Unit. Ext'].apply(clean_price).fillna(0.0)
        df_orig[col_custo_cx] = df_orig['Custo Unit. Ext'] * qtde

        # --- 4. EDITOR DE QUANTIDADES ---
        st.subheader("📦 1. Definir Quantidades do Lote")
        if 'Qtd Caixas' not in df_orig.columns: df_orig['Qtd Caixas'] = 1

        df_editor = st.data_editor(
            df_orig[['NomeProduto', 'Qtd Caixas', col_custo_cx]],
            column_config={
                "Qtd Caixas": st.column_config.NumberColumn("Qtd Caixas", min_value=0, max_value=20, step=1),
                col_custo_cx: st.column_config.NumberColumn(f"Custo (€/{qtde}un)", format="€ %.2f", disabled=True)
            },
            disabled=["NomeProduto", col_custo_cx],
            use_container_width=True, hide_index=True
        )

        # --- 5. CÁLCULOS ---
        df = df_orig.copy()
        df['Qtd Caixas'] = df_editor['Qtd Caixas']
        df['FCA'] = (df[col_custo_cx] * df['Qtd Caixas']) * cambio
        df['Frete'] = df['FCA'] * frete_p
        base_entrada = df['FCA'] + df['Frete']
        
        df['IPI Compra'] = base_entrada * IPI_C
        df['PISCOFINS Compra'] = base_entrada * PISCOF_C
        df['Despesas Compra'] = base_entrada * DESP_C
        df['Nota Entrada'] = base_entrada + df['IPI Compra'] + df['PISCOFINS Compra'] + df['Despesas Compra']

        if ajustar_auto:
            teto_total = preco_teto * df['Qtd Caixas']
            df['Margem Aplicada'] = (1 - (df['Nota Entrada'] / teto_total.replace(0, 1)) - icms_v_p - IPI_V - COMIS)
        else:
            df['Margem Aplicada'] = margem_alvo
            
        divisor = 1 - (icms_v_p + IPI_V + COMIS + df['Margem Aplicada'])
        df['Venda Total'] = df['Nota Entrada'] / divisor
        
        df['ICMS Venda'] = df['Venda Total'] * icms_v_p
        df['IPI Venda'] = df['Venda Total'] * IPI_V
        df['Comissao'] = df['Venda Total'] * COMIS
        df['Custo CMV Unit'] = df['Nota Entrada'] + df['ICMS Venda'] + df['IPI Venda'] + df['Comissao']
        df['Lucro R$'] = df['Venda Total'] - df['Custo CMV Unit']
        df['Venda por Garrafa'] = (df['Venda Total'] / (df['Qtd Caixas'] * qtde)).replace([np.inf, -np.inf], 0)

        # --- 6. TABELA EXPANDIDA ---
        st.markdown("---")
        st.subheader("📄 2. Detalhes por Produto")
        filtro_nome = st.text_input("🔍 Filtrar produto:", "")
        visao = st.radio("Escolha a visualização:", ["🌐 Visão Geral", "🚢 Importação", "💰 Venda"], horizontal=True)

        if visao == "🌐 Visão Geral":
            cols_tab = ['NomeProduto', 'Qtd Caixas', 'Custo Unit. Ext', col_custo_cx, 'FCA', 'Frete', 'IPI Compra', 'PISCOFINS Compra', 'Despesas Compra', 'Nota Entrada', 'ICMS Venda', 'IPI Venda', 'Comissao', 'Venda Total', 'Lucro R$', 'Venda por Garrafa']
        elif visao == "🚢 Importação":
            cols_tab = ['NomeProduto', 'Qtd Caixas', 'Custo Unit. Ext', col_custo_cx,'FCA', 'Frete', 'IPI Compra', 'PISCOFINS Compra', 'Despesas Compra', 'Nota Entrada']
        else:
            cols_tab = ['NomeProduto', 'Qtd Caixas', 'ICMS Venda', 'IPI Venda', 'Comissao', 'Venda Total', 'Lucro R$', 'Venda por Garrafa']

        df_tab = df[cols_tab].copy()
        if filtro_nome: df_tab = df_tab[df_tab['NomeProduto'].str.contains(filtro_nome, case=False)]

        totais = df_tab.select_dtypes(include=[np.number]).sum()
        linha_total = pd.DataFrame([['TOTAL'] + totais.tolist()], columns=cols_tab)
        df_final = pd.concat([df_tab, linha_total], ignore_index=True)

        def fmt_br(prefix): return lambda x: f"{prefix} {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        format_dict = {c: fmt_br('R$') for c in df_final.columns if c not in ['NomeProduto', 'Qtd Caixas', 'Custo Unit. Ext', col_custo_cx]}
        format_dict.update({'Custo Unit. Ext': fmt_br('€'), col_custo_cx: fmt_br('€'), 'Qtd Caixas': '{:.0f}'})

        st.dataframe(
            df_final.style.format({k: v for k, v in format_dict.items() if k in cols_tab})
            .apply(lambda row: ['background-color: #f0f2f6; font-weight: bold' if row['NomeProduto'] == 'TOTAL' else '' for _ in row], axis=1)
            .map(lambda v: f'color: {"#4169E1" if v > 0 else "#FF4B4B"}; font-weight: bold' if isinstance(v, (int, float)) else '', subset=[c for c in ['Lucro R$'] if c in cols_tab]),
            use_container_width=True, height=400
        )
        
        # Botão Exportar Tabela
        buffer_det = io.BytesIO()
        df_final.to_excel(buffer_det, index=False)
        st.download_button("📥 Exportar Detalhes para Excel", buffer_det.getvalue(), f"Detalhes_{lote_nome}.xlsx")

       # --- 7. MÉTRICAS ---
        st.markdown("---")
        
        st.subheader("📊 Resumo da Simulação")
        
        # Cálculos das somas
        v_tot = df['Venda Total'].sum()
        cmv_tot = df['Custo CMV Unit'].sum()
        l_tot = df['Lucro R$'].sum()
        f_tot = df['Frete'].sum()
        n_ent_tot = df['Nota Entrada'].sum() 
        qtd_cx_tot = df['Qtd Caixas'].sum()
        qtd_gar_tot = qtd_cx_tot * qtde # Total de garrafas baseado na variável inserível

        # Ajuste para 6 colunas
        m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
        
        m1.metric("**Total de Garrafas:**", f"{qtd_gar_tot:.0f}")
        m2.metric("**Total de Caixas:**", f"{qtd_cx_tot:.0f}")
        m3.metric("**Frete Total:**", f"R$ {f_tot:,.2f}")
        m4.metric("**Nota Entrada Total:**", f"R$ {n_ent_tot:,.2f}") # Nova métrica na ordem solicitada
        m5.metric("**Custo CMV Total:**", f"R$ {cmv_tot:,.2f}")
        m6.metric("**Venda Total Lote:**", f"R$ {v_tot:,.2f}")
        m7.metric("**Lucro Estimado:**", f"R$ {l_tot:,.2f}")
        
        st.markdown("---")


        # --- 8. GRÁFICOS ---
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("💰 Distribuição de Custos")
            dados_p = {'FCA': df['FCA'].sum(), 'Frete': f_tot, 'Imp. Compra': df['IPI Compra'].sum() + df['PISCOFINS Compra'].sum(), 
                       'Imp. Venda': df['ICMS Venda'].sum() + df['IPI Venda'].sum(), 'Comissões': df['Comissao'].sum(), 'Lucro': l_tot}
            cores_p = {'FCA': '#f69e6e', 'Frete': '#ffccac', 'Imp. Compra': '#e68a5c', 'Imp. Venda': '#d87a4d', 'Comissões': '#fbbd9b', 'Lucro': '#66c4cc'}
            fig_p = px.pie(names=list(dados_p.keys()), values=[max(0, x) for x in dados_p.values()], hole=0.5, color=list(dados_p.keys()), color_discrete_map=cores_p)
            st.plotly_chart(fig_p, use_container_width=True)

        with g2:
            st.subheader("📉 Fluxo Financeiro (Funil)")
            fig_f = go.Figure(go.Funnel(y=['FCA', 'Nota Entrada', 'Custo CMV', 'Venda Total'], x=[df['FCA'].sum(), df['Nota Entrada'].sum(), cmv_tot, v_tot],
                                       marker={"color": ["#ffccac", "#f69e6e", "#d87a4d", "#66c4cc"]}))
            st.plotly_chart(fig_f, use_container_width=True)

        g3, g4 = st.columns(2)
        with g3:
            st.subheader("📈 Sensibilidade: Preço Garrafa vs. Margem")
            # Cálculo de sensibilidade baseado na média do lote
            if df['Qtd Caixas'].sum() > 0:
                # Custo médio de entrada por garrafa (Nota Entrada Total / Qtd Total Garrafas)
                qtd_total_garrafas = df['Qtd Caixas'].sum() * 6
                custo_medio_garrafa = df['Nota Entrada'].sum() / qtd_total_garrafas
                
                # Simulação de margens de 0% a 60%
                sim_margins = np.linspace(0.01, 0.60, 50)
                # Fórmula: Preço = Custo / (1 - ImpostosVenda - Margem)
                sim_prices = [custo_medio_garrafa / (1 - (icms_v_p + IPI_V + COMIS + m)) for m in sim_margins]
                
                fig_sens = go.Figure()
                fig_sens.add_trace(go.Scatter(
                    x=sim_margins * 100, 
                    y=sim_prices, 
                    mode='lines',
                    name='Preço Sugerido',
                    line=dict(color='#4DB6AC', width=3)
                ))
                
                # Ponto da margem atual
                margem_atual_pct = margem_alvo * 100
                preco_atual = custo_medio_garrafa / (1 - (icms_v_p + IPI_V + COMIS + margem_alvo))
                
                fig_sens.add_trace(go.Scatter(
                    x=[margem_atual_pct], 
                    y=[preco_atual],
                    mode='markers+text',
                    name='Margem Atual',
                    text=[f"R$ {preco_atual:.2f}"],
                    textposition="top center",
                    marker=dict(color='orange', size=10)
                ))
                
                fig_sens.update_layout(
                    xaxis_title="Margem Alvo (%)",
                    yaxis_title="Preço de Venda/Garrafa (R$)",
                    hovermode="x unified"
                )
                st.plotly_chart(fig_sens, use_container_width=True)
            else:
                st.warning("Defina quantidades para ver a sensibilidade.")

        with g4:
            st.subheader("⚠️ Top 10: Excesso sobre o Teto")
            
            # Cálculo do excesso usando o nome correto: 'Venda Total'
            # Dividimos a Venda Total pela Qtd de Caixas para comparar o valor unitário da caixa com o teto
            df['Preço Unit. Caixa'] = (df['Venda Total'] / df['Qtd Caixas'].replace(0, 1)).fillna(0)
            df['Excesso R$'] = df['Preço Unit. Caixa'] - preco_teto
            
            # Filtra apenas quem estoura o teto e pega os 10 maiores
            df_excesso = df[df['Excesso R$'] > 0].sort_values(by='Excesso R$', ascending=False).head(10)
            
            if not df_excesso.empty:
                # FUNÇÃO PARA QUEBRAR O TEXTO
                def quebrar_texto(nome, max_chars=20):
                    if not isinstance(nome, str): return str(nome)
                    if len(nome) <= max_chars: return nome
                    palavras = nome.split()
                    linhas = []
                    linha_atual = ""
                    for p in palavras:
                        if len(linha_atual + p) <= max_chars:
                            linha_atual += p + " "
                        else:
                            linhas.append(linha_atual.strip())
                            linha_atual = p + " "
                    linhas.append(linha_atual.strip())
                    return "<br>".join(linhas)

                df_excesso['Nome Quebrado'] = df_excesso['NomeProduto'].apply(quebrar_texto)

                fig_excesso = px.bar(
                    df_excesso, 
                    x='Excesso R$', 
                    y='Nome Quebrado', 
                    orientation='h',
                    color='Excesso R$',
                    color_continuous_scale=['#ffccac', '#f69e6e', '#d87a4d'],
                    labels={'Excesso R$': 'Excesso (R$)', 'Nome Quebrado': 'Produto'}
                )
                
                fig_excesso.update_layout(
                    yaxis={'categoryorder':'total ascending'},
                    margin=dict(l=150),
                    showlegend=False
                )
                st.plotly_chart(fig_excesso, use_container_width=True)
            else:
                st.success("✅ Nenhum produto ultrapassa o preço teto!")
       
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
else:
    st.info("Aguardando arquivo Excel...")

#%%



#%%


# 1. Entrar na pasta do projeto
# cd "C:\Users\lcaruso\Desktop\Luca\Projeto Ricex"

# 2. Instalar a biblioteca que faltava (se ainda não fez)
# pip install xlsxwriter streamlit pandas plotly openpyxl
# ou
# py -m pip install plotly xlsxwriter openpyxl

# 3. Rodar o sistema para abrir no seu navegador
# py -m streamlit run simulacao.py

# outra forma:
# cd /d "C:\Users\lcaruso\Desktop\Luca\Projeto Ricex" && py -m streamlit run simulacao.py
# cd /d "C:\Users\lcaruso\Desktop\Luca\Projeto Ricex" && py -m streamlit run simulacao_test.py

#%%
