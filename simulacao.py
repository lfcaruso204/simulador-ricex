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
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #31333F; }
    .main .block-container { padding-left: 2rem; padding-right: 2rem; padding-top: 1.5rem; }
    /* Diminui fonte dos labels e inputs na sidebar */
    [data-testid="stSidebar"] .stNumberInput label, 
    [data-testid="stSidebar"] .stSlider label { font-size: 12px !important; margin-bottom: 0px; }
    [data-testid="stSidebar"] .stNumberInput input { font-size: 12px !important; }
    div[data-testid="stSidebarUserContent"] { padding-top: 1rem; }
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
        # 3. PROCESSAMENTO DE DADOS
        df = pd.read_excel(arquivo_upload, sheet_name='analise')
        df['Custo Unit. Ext'] = pd.to_numeric(df['Custo Unit. Ext'].astype(str).str.replace(r'[^\d,.]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0.0)

        # --- SIDEBAR (PARÂMETROS) ---
        st.sidebar.header("⚙️ Parâmetros")
        cambio = st.sidebar.number_input("Câmbio (€/R$)", value=6.30)
        frete_p = st.sidebar.number_input("Frete (%)", value=3.0) / 100
        
        st.sidebar.subheader("📥 Impostos Compra")
        IPI_C = st.sidebar.number_input("IPI Compra (%)", value=6.5) / 100
        PISCOF_C = st.sidebar.number_input("PIS/COFINS Compra (%)", value=11.75) / 100
        DESP_C = st.sidebar.number_input("Despesas Compra (%)", value=2.0) / 100

        st.sidebar.subheader("📤 Impostos Venda")
        icms_v_p = st.sidebar.number_input("ICMS Venda (%)", value=8.0) / 100
        IPI_V = st.sidebar.number_input("IPI Venda (%)", value=6.5) / 100
        COMIS = st.sidebar.number_input("Comissões (%)", value=6.5) / 100
        
        st.sidebar.markdown("---")
        st.sidebar.write("**Margem Alvo (%)**")
        
        # Campo de Digitação
        margem_digitada = st.sidebar.number_input(
            "Digitar Margem", 
            value=20.0, 
            step=0.1, 
            format="%.1f",
            label_visibility="collapsed"
        )
        
        # Slider sincronizado com o campo de digitação
        margem_alvo_slider = st.sidebar.slider(
            "Ajustar via Slider", 
            min_value=0.0, 
            max_value=60.0, 
            value=float(margem_digitada),
            step=0.1,
            help="Arraste para ajuste fino"
        ) / 100
        
        preco_teto = st.sidebar.number_input("Preço Teto por Caixa (R$)", value=5000.0)
        ajustar_auto = st.sidebar.button("🔄 Ajustar Margens ao Teto")
        
        # 4. CÁLCULOS DE NEGÓCIO (CAIXA E GARRAFA)
        df['Custo Caixa (x6)'] = df['Custo Unit. Ext'] * 6
        df['FCA'] = df['Custo Caixa (x6)'] * cambio
        df['Frete'] = df['FCA'] * frete_p
        
        # Base para impostos de entrada (FCA + Frete)
        base_entrada = df['FCA'] + df['Frete']
        df['IPI Compra'] = base_entrada * IPI_C
        df['PISCOFINS Compra'] = base_entrada * PISCOF_C
        df['Despesas Compra'] = base_entrada * DESP_C

        # Nova Definição de Nota Entrada: FCA+Frete + Impostos Compra
        df['Nota Entrada'] = base_entrada + df['IPI Compra'] + df['PISCOFINS Compra'] + df['Despesas Compra']

        if ajustar_auto:
            df['Margem Aplicada'] = (1 - (df['Nota Entrada'] / preco_teto) - icms_v_p - IPI_V - COMIS)
        else:
            df['Margem Aplicada'] = margem_alvo_slider
            
        divisor = 1 - (icms_v_p + IPI_V + COMIS + df['Margem Aplicada'])
        df['Venda por Caixa'] = df['Nota Entrada'] / divisor
        
        # Impostos sobre a Venda
        df['ICMS Venda'] = df['Venda por Caixa'] * icms_v_p
        df['IPI Venda'] = df['Venda por Caixa'] * IPI_V
        df['Comissao'] = df['Venda por Caixa'] * COMIS
        
        df['Custo CMV Unit'] = df['Nota Entrada'] + df['ICMS Venda'] + df['IPI Venda'] + df['Comissao']
        df['Lucro R$'] = df['Venda por Caixa'] - df['Custo CMV Unit']
        df['Excesso R$'] = df['Venda por Caixa'] - preco_teto


        # 5. TABELA EXPANDIDA COM TOTAIS (FORMATO PT-BR)
        
        df['Venda por Garrafa'] = df['Venda por Caixa'] / 6

        cols_tab = [
            'NomeProduto', 
            'Custo Unit. Ext', 
            'Custo Caixa (x6)', 
            'FCA',
            'Frete',
            'IPI Compra',
            'PISCOFINS Compra',
            'Despesas Compra',            
            'Nota Entrada',
            'ICMS Venda',
            'IPI Venda',
            'Comissao',
            'Custo CMV Unit', 
            'Venda por Caixa', 
            'Lucro R$',
            'Venda por Garrafa']
        
        df_tab = df[cols_tab].copy()
        totais = df_tab.select_dtypes(include=[np.number]).sum()
        linha_total = pd.DataFrame([['TOTAL DO LOTE'] + totais.tolist()], columns=cols_tab)
        df_final = pd.concat([df_tab, linha_total], ignore_index=True)

        def fmt_br(prefix): return lambda x: f"{prefix} {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
         
        st.markdown("---")
        st.subheader("📄 Detalhes por Produto")
        
        visao = st.radio(
            "Escolha a visualização:",
            ["🌐 Visão Geral", "🚢 Importação", "💰 Venda"],
            horizontal=True,
            label_visibility="collapsed"
        )

        # Definição das colunas por visão
        if visao == "🌐 Visão Geral":
            cols_tab = ['NomeProduto', 'Custo Unit. Ext', 'Custo Caixa (x6)','FCA', 'Frete', 'IPI Compra', 'PISCOFINS Compra', 'Despesas Compra', 'Nota Entrada', 'ICMS Venda', 'IPI Venda', 'Comissao', 'Custo CMV Unit', 'Venda por Caixa', 'Lucro R$', 'Venda por Garrafa']
        elif visao == "🚢 Importação":
            cols_tab = ['NomeProduto', 'Custo Unit. Ext', 'Custo Caixa (x6)','FCA', 'Frete', 'IPI Compra', 'PISCOFINS Compra', 'Despesas Compra', 'Nota Entrada']
        else: # 💰 Venda:
            cols_tab = ['NomeProduto', 'ICMS Venda', 'IPI Venda', 'Comissao', 'Custo CMV Unit', 'Venda por Caixa', 'Lucro R$', 'Venda por Garrafa']
        
        # Criar DataFrame filtrado
        df_tab = df[cols_tab].copy()
        
        # Calcular Totais
        totais = df_tab.select_dtypes(include=[np.number]).sum()
        linha_total = pd.DataFrame([['TOTAL'] + totais.tolist()], columns=cols_tab)
        df_final = pd.concat([df_tab, linha_total], ignore_index=True)

        # Dicionário de Formatação (Centralizado)
        format_dict = {
            'Custo Unit. Ext': fmt_br('€'), 'Custo Caixa (x6)': fmt_br('€'),'FCA': fmt_br('R$'), 'Frete': fmt_br('R$'),
            'IPI Compra': fmt_br('R$'), 'PISCOFINS Compra': fmt_br('R$'), 'Despesas Compra': fmt_br('R$'),
            'Nota Entrada': fmt_br('R$'), 'ICMS Venda': fmt_br('R$'), 'IPI Venda': fmt_br('R$'),
            'Comissao': fmt_br('R$'), 'Custo CMV Unit': fmt_br('R$'), 'Venda por Caixa': fmt_br('R$'),
            'Lucro R$': fmt_br('R$'), 'Venda por Garrafa': fmt_br('R$')
        }
        
        # Filtra os formatadores apenas para as colunas visíveis
        fmt_config = {k: v for k, v in format_dict.items() if k in cols_tab}

        # Exibição da Tabela
        st.dataframe(
            df_final.style.format(fmt_config)
            .set_table_styles([
                {'selector': 'th', 'props': [('font-size', '11px'), ('text-align', 'center')]},
                {'selector': 'td', 'props': [('font-size', '11px')]}
            ])
            .apply(lambda row: ['background-color: #f0f2f6; font-weight: bold' if row['NomeProduto'] == 'TOTAL' else '' for _ in row], axis=1)
            .applymap(lambda v: f'color: {"#4169E1" if v > 0 else "#FF4B4B"}; font-weight: bold' if isinstance(v, (int, float)) else '', 
                      subset=[c for c in ['Lucro R$'] if c in cols_tab]),
            use_container_width=True, 
            height=500,
            column_config={
                "NomeProduto": st.column_config.TextColumn("Produto", pinned=True) # CONGELA A COLUNA
            }
        )
        
        
        # 6. BOTÃO DE EXPORTAÇÃO ---
        # Criamos um buffer para salvar o arquivo Excel em memória
        buffer = io.BytesIO()

        # Criamos o arquivo Excel usando o DataFrame final (que já tem a linha de TOTAL)
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Analise_Lote')
            
            # Ajuste opcional: formatar larguras de colunas no Excel (opcional)
            workbook  = writer.book
            worksheet = writer.sheets['Analise_Lote']
            header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
            
            # Aplicar o formato de cabeçalho
            for col_num, value in enumerate(df_final.columns.values):
                worksheet.write(0, col_num, value, header_format)

        # Botão de Download
        st.download_button(
            label="📥 Baixar Detalhes em Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"Analise_{lote_nome}_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )        

        # 7. MÉTRICAS E GRÁFICOS (PIZZA E FUNIL) ---
        v_tot, cmv_tot, l_tot = df['Venda por Caixa'].sum(), df['Custo CMV Unit'].sum(), df['Lucro R$'].sum()
        m1, m2, m3 = st.columns(3)
        m1.metric("Venda Total", f"R$ {v_tot:,.2f}")
        m2.metric("Custo Total (CMV)", f"R$ {cmv_tot:,.2f}")
        m3.metric("Lucro Estimado", f"R$ {l_tot:,.2f}")

        st.markdown("---")
        g1, g2 = st.columns(2)
        
        with g1:
            st.subheader("💰 Distribuição de Custos")
            dados_p = {
                'Custo FCA': df['FCA'].sum(), 
                'Entrada': df['Nota Entrada'].sum() - df['FCA'].sum(),
                'Impostos Compra': df['IPI Compra'].sum() + df['PISCOFINS Compra'].sum(),
                'Impostos Venda': df['ICMS Venda'].sum() + df['IPI Venda'].sum(),      # Agora aparece no gráfico
                'Comissões': df['Comissao'].sum(),                              # Agora aparece no gráfico
                'Lucro': df['Lucro R$'].sum()
            }
            
            cores_map = {'Custo FCA': '#FFB347', 'Entrada': '#FFCC80', 'Impostos Compra': '#FFE082','Impostos Venda': '#E9E371', 'Comissões': '#FFF9C4', 'Lucro': '#4DB6AC'}
            fig_p = px.pie(names=list(dados_p.keys()), values=[max(0, x) for x in dados_p.values()], hole=0.5, 
                           color=list(dados_p.keys()), color_discrete_map=cores_map)
            st.plotly_chart(fig_p, use_container_width=True)

        with g2:
            st.subheader("📉 Fluxo Financeiro (Funil)")
            fig_f = go.Figure(go.Funnel(
                y=['FCA', 'Nota Entrada', 'Custo CMV', 'Venda Total'], 
                x=[df['FCA'].sum(), df['Nota Entrada'].sum(), cmv_tot, v_tot],
                marker={"color": ["#FFB347", "#FFCC80", "#FFE082", "#4DB6AC"]}))
            st.plotly_chart(fig_f, use_container_width=True)

        # 8. SENSIBILIDADE (PREÇO GARRAFA VS MARGEM)
        st.markdown("---")
        st.subheader("📈 Sensibilidade: Preço de Venda (Garrafa) vs. Margem")
        custo_garrafa_entrada = df['Nota Entrada'].mean() / 6
        sim_margins = np.linspace(0.01, 0.60, 50)
        sim_prices = [custo_garrafa_entrada / (1 - (icms_v_p + IPI_V + COMIS + m)) for m in sim_margins]
        margem_media_atual = df['Margem Aplicada'].mean()
        venda_garrafa_ponto = custo_garrafa_entrada / (1 - (icms_v_p + IPI_V + COMIS + margem_media_atual))

        fig_sens = go.Figure()
        fig_sens.add_trace(go.Scatter(x=sim_margins*100, y=sim_prices, name='Preço Sugerido (R$)', line=dict(color='#4DB6AC', width=3)))
        fig_sens.add_trace(go.Scatter(x=[margem_media_atual*100], name='Margem Selecionada', y=[venda_garrafa_ponto], mode='markers+text', 
                                      text=[f"R$ {venda_garrafa_ponto:,.2f}"], textposition="top center",
                                      marker=dict(color='#FFD700', size=15, line=dict(width=2))))
        fig_sens.update_layout(xaxis_title="Margem Selecionada (%)", yaxis_title="Preço Médio por Garrafa R$")
        st.plotly_chart(fig_sens, use_container_width=True)

        # 9. TOP 10 EXCESSO (ORDEM DESCRESCENTE)
        df_excesso = df[df['Venda por Caixa'] > preco_teto].sort_values('Excesso R$', ascending=True).tail(10)
        if not df_excesso.empty:
            st.markdown("---")
            st.subheader("🚨 Top 10 Produtos Acima do Teto")
            fig_ex = px.bar(df_excesso, x='Excesso R$', y='NomeProduto', orientation='h', color='Excesso R$', color_continuous_scale='Reds', text_auto='.2f')
            st.plotly_chart(fig_ex, use_container_width=True)


        
    except Exception as e: st.error(f"Erro no processamento: {e}")


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

