import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import date
import os
import numpy as np

# 1. SETUP DA PÁGINA
st.set_page_config(page_title="Ricex - Gestão de Lotes", layout="wide")

# CSS para diminuir o tamanho das métricas
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 22px !important; }
    [data-testid="stMetricLabel"] { font-size: 14px !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. ESTRUTURA DE CENTRALIZAÇÃO
m_esq, col_central, m_dir = st.columns([1, 4, 1])

with col_central:
    c_logo, c_tit = st.columns([1, 4])
    with c_logo:
        if os.path.exists('Ricex.png'):
            st.image('Ricex.png', width=100)
    with c_tit:
        st.title("Gestão de Lotes de Importação - Ricex")
        
    cid1, cid2 = st.columns(2)
    lote_nome = cid1.text_input("📦 Identificação do Lote", "Lote_Analise_Ricex")
    data_analise = cid2.date_input("📅 Data da Análise", date.today())
    
    st.markdown("---")
    st.subheader("📂 Carregar Dados do Lote")
    arquivo_upload = st.file_uploader("Arraste o arquivo Excel aqui (Aba: 'analise')", type=["xlsx"])

# 3. PROCESSAMENTO
if arquivo_upload is not None:
    try:
        df = pd.read_excel(arquivo_upload, sheet_name='analise')
        df['Custo Unit. Ext'] = pd.to_numeric(df['Custo Unit. Ext'].astype(str).str.replace(r'[^\d,.]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0.0)

        # SIDEBAR (Parâmetros)
        st.sidebar.header("⚙️ Parâmetros")
        cambio = st.sidebar.number_input("Câmbio (€/R$)", value=6.30)
        frete_p = st.sidebar.number_input("Frete (%)", value=3.0) / 100
        icms_v_p = st.sidebar.number_input("ICMS Venda (%)", value=8.0) / 100
        margem_alvo = st.sidebar.slider("Margem Alvo (%)", 0, 100, 30) / 100
        ajustar_auto = st.sidebar.button("🔄 Ajustar Margens ao Teto")
        preco_teto = st.sidebar.number_input("Preço Teto Alerta (R$)", value=1000.0)

        # Constantes e Cálculos
        IPI_V, COMIS, IMP_C, DESP_C = 0.065, 0.065, 0.1825, 0.02
        df['FCA R$'] = df['Custo Unit. Ext'] * cambio
        df['Nota Entrada'] = df['FCA R$'] * (1 + frete_p) * (1 + IMP_C + DESP_C)
        
        # Margem Aplicada
        df['Margem Aplicada'] = (1 - (df['Nota Entrada'] / preco_teto) - icms_v_p - IPI_V - COMIS) if ajustar_auto else margem_alvo
        
        divisor = 1 - (icms_v_p + IPI_V + COMIS + df['Margem Aplicada'])
        df['Venda Unitária'] = df['Nota Entrada'] / divisor
        df['R$ ICMS'] = df['Venda Unitária'] * icms_v_p
        df['R$ IPI'] = df['Venda Unitária'] * IPI_V
        df['R$ Comissao'] = df['Venda Unitária'] * COMIS
        df['Custo CMV Unit'] = df['Nota Entrada'] + df['R$ ICMS'] + df['R$ IPI'] + df['R$ Comissao']
        df['Lucro R$'] = df['Venda Unitária'] - df['Custo CMV Unit']
        df['Excesso R$'] = df['Venda Unitária'] - preco_teto

        # 4. RESUMO CONSOLIDADO
        with col_central:
            st.subheader("📊 Resumo Consolidado do Lote")
            v_tot, cmv_tot, l_tot = df['Venda Unitária'].sum(), df['Custo CMV Unit'].sum(), df['Lucro R$'].sum()
            met1, met2, met3 = st.columns(3)
            met1.metric("Venda Bruta Total", f"R$ {v_tot:,.2f}")
            met2.metric("Custo CMV Total", f"R$ {cmv_tot:,.2f}")
            met3.metric("Margem Líquida Total", f"R$ {l_tot:,.2f}")
            st.markdown("---")

        # 5. GRÁFICOS PRINCIPAIS
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("💰 Distribuição Geral (R$)")
            dados_p = {'Custo FOB': df['FCA R$'].sum(), 'Entrada/Logist': df['Nota Entrada'].sum() - df['FCA R$'].sum(), 'Tributos Venda': df['R$ ICMS'].sum() + df['R$ IPI'].sum(), 'Comissões': df['R$ Comissao'].sum(), 'Lucro': l_tot}
            st.plotly_chart(px.pie(names=list(dados_p.keys()), values=list(dados_p.values()), hole=0.5), use_container_width=True)
        with g2:
            st.subheader("📉 Etapas do Fluxo (Funil)")
            st.plotly_chart(go.Figure(go.Funnel(y=['Custo Ext', 'Nota Entrada', 'Custo CMV', 'Venda Bruta'], x=[df['FCA R$'].sum(), df['Nota Entrada'].sum(), cmv_tot, v_tot], textinfo="value+percent initial")), use_container_width=True)

        # 6. ANÁLISE DE SENSIBILIDADE
        st.markdown("---")
        st.subheader("📈 Sensibilidade: Preço Médio por Garrafa vs. Margem")
        sim_margins = np.linspace(0.0, 0.50, 25)
        custo_medio_entrada = df['Nota Entrada'].mean()
        sim_prices = [custo_medio_entrada / (1 - (icms_v_p + IPI_V + COMIS + m)) for m in sim_margins]
        fig_sens = px.line(x=sim_margins*100, y=sim_prices, labels={'x':'Margem Desejada (%)', 'y':'Preço Médio (R$)'}, markers=True)
        fig_sens.add_hline(y=preco_teto, line_dash="dash", line_color="red", annotation_text="Teto")
        st.plotly_chart(fig_sens, use_container_width=True)

        # 7. TOP 10 EXCESSO
        df_acima = df[df['Venda Unitária'] > preco_teto].sort_values(by='Excesso R$', ascending=True).tail(10)
        if not df_acima.empty and not ajustar_auto:
            st.markdown("---")
            st.subheader("🚨 Top 10 Produtos com Maior Excesso (Unitário)")
            fig_t = px.bar(df_acima, x='Excesso R$', y='NomeProduto', orientation='h', color='Excesso R$', color_continuous_scale='Reds', text_auto='.2f')
            fig_t.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_t, use_container_width=True)

        # 8. TABELA E EXPORTAÇÃO
        with col_central:
            st.markdown("---")
            with st.expander("📄 Detalhes por Produto"):
                m_cols = ['FCA R$', 'Nota Entrada', 'Custo CMV Unit', 'Venda Unitária', 'Lucro R$']
                st.dataframe(df[['NomeProduto'] + m_cols].style.format({c: "R$ {:.2f}" for c in m_cols}), use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Relatorio')
            st.download_button(label="📥 Baixar Excel do Lote", data=output.getvalue(), file_name=f"Ricex_{lote_nome}.xlsx")

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")

else:
    with col_central:
        st.info("💡 Aguardando upload do arquivo Excel para iniciar a análise.")


#%%


# 1. Entrar na pasta do projeto
# cd "C:\Users\lcaruso\Desktop\Luca\Projeto Ricex"

# 2. Instalar a biblioteca que faltava (se ainda não fez)
# pip install xlsxwriter streamlit pandas plotly openpyxl
# ou
# py -m pip install plotly xlsxwriter openpyxl

# 3. Rodar o sistema para abrir no seu navegador
# py -m streamlit run testing.py

