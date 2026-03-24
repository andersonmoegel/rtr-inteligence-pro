import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import re
import plotly.express as px
from fuzzywuzzy import fuzz
import os

# ==========================================
# 1. CONFIGURAÇÕES E ESTILO (UI/UX)
# ==========================================
st.set_page_config(page_title="RTR Intelligence", layout="wide", page_icon="⚖️")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .main-header { 
        background: linear-gradient(90deg, #005792, #00A8E8); 
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; 
        font-size: 42px; font-weight: 800; text-align: center; margin-bottom: 30px;
    }
    
    /* Estilização dos Uploaders */
    [data-testid="stFileUploader"] {
        background-color: #111827;
        border: 2px dashed #00A8E8;
        border-radius: 15px;
        padding: 10px;
    }

    /* Cards de Métrica */
    [data-testid="stMetric"] { 
        background-color: #1f2937 !important; 
        padding: 20px !important; 
        border-radius: 15px !important; 
        border-left: 5px solid #00A8E8 !important; 
    }

    /* Card de Expansão Detalhada */
    .expansion-card {
        background-color: rgba(0, 87, 146, 0.08);
        border: 1px solid #005792;
        border-radius: 12px;
        padding: 25px;
        margin-bottom: 15px;
    }

    /* Botão Verde de Sucesso */
    div.stButton > button:first-child[key^="btn_"] {
        background-color: #10B981 !important;
        color: white !important;
        border: none !important;
        height: 45px;
        font-weight: 600;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. GESTÃO DE CATEGORIAS, SESSÃO E DADOS
# ==========================================
if 'categorias' not in st.session_state:
    st.session_state.categorias = ["Bancário", "Impostos", "Operacional", "RH", "Financeiro", "Vendas", "Outros"]

if 'df_trabalho' not in st.session_state:
    st.session_state.df_trabalho = None

# --- Funções de Apoio ---
def formatar_moeda_br(valor):
    if pd.isna(valor): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def sugerir_colunas(df):
    sug = {"data": 0, "valor": 1, "desc": 0}
    for i, col in enumerate(df.columns):
        c = str(col).upper()
        amostra = " ".join(df[col].dropna().head(5).astype(str))
        if any(x in c for x in ['DATA', 'DATE', 'LANCTO']) or re.search(r'\d{2}/\d{2}', amostra): sug["data"] = i
        elif any(x in c for x in ['VALOR', 'MONTANTE', 'SALDO']) or "," in amostra: sug["valor"] = i
    col_rest = [i for i in range(len(df.columns)) if i not in [sug["data"], sug["valor"]]]
    if col_rest: sug["desc"] = max(col_rest, key=lambda x: df.iloc[:, x].astype(str).str.len().mean())
    return sug

def normalizar_moeda(v):
    try:
        if pd.isna(v) or v == "": return 0.0
        if isinstance(v, (int, float)): return round(float(v), 2)
        s = str(v).replace("R$", "").strip()
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        elif "," in s: s = s.replace(",", ".")
        return round(float(re.sub(r"[^0-9.\-]", "", s)), 2)
    except: return 0.0

def categorizar_ia(t):
    regras = {r"TAR|TARIFA": "Bancário", r"IOF|IRRF|DARF": "Impostos", r"PIX|TED|PAG": "Operacional", r"SALAR|FOLHA": "RH"}
    for p, c in regras.items():
        if re.search(p, str(t).upper()): return c
    return "Outros"

# --- Funções de Banco de Dados (Histórico) ---

def salvar_no_historico(df):
    """Salva apenas os itens validados no arquivo de histórico CSV (nosso BD)."""
    file_path = "historico_conciliacao.csv"
    df_validado = df[df['Validar'] == True].copy()
    
    if df_validado.empty:
        return False
        
    df_validado['Data_Processamento'] = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    # Converte dicionários na coluna 'detalhes' para string para evitar erros no CSV
    df_validado['detalhes'] = df_validado['detalhes'].astype(str)
    
    try:
        df_antigo = pd.read_csv(file_path, sep=';', encoding='utf-8-sig')
        df_final = pd.concat([df_antigo, df_validado], ignore_index=True)
        df_final.to_csv(file_path, index=False, sep=';', encoding='utf-8-sig')
    except FileNotFoundError:
        df_validado.to_csv(file_path, index=False, sep=';', encoding='utf-8-sig')
    return True

def carregar_historico():
    """Lê o arquivo de histórico."""
    try:
        return pd.read_csv("historico_conciliacao.csv", sep=';', encoding='utf-8-sig')
    except FileNotFoundError:
        return pd.DataFrame()

# ==========================================
# 3. INTERFACE LATERAL (CONFIGURAÇÕES)
# ==========================================
with st.sidebar:
    st.header("⚙️ Configurações CoE")
    
    with st.expander("🏷️ Gestor de Categorias", expanded=False):
        nova_cat = st.text_input("Nova Categoria")
        if st.button("Adicionar") and nova_cat:
            if nova_cat not in st.session_state.categorias:
                st.session_state.categorias.append(nova_cat)
                st.rerun()
        st.write("Categorias Atuais:", st.session_state.categorias)

    if st.button("⬅️ Voltar", use_container_width=True):
        st.session_state.df_trabalho = None
        st.rerun()
        
    # Os botões de salvar/exportar aparecerão aqui apenas se houver dados ativos
    if st.session_state.df_trabalho is not None:
        st.markdown("---")
        st.subheader("💾 Ações do Processo")
        
        if st.button("Gravar Validados no Histórico", type="primary", use_container_width=True):
            sucesso = salvar_no_historico(st.session_state.df_trabalho)
            if sucesso:
                st.success("Registros gravados no Banco de Dados!")
            else:
                st.warning("Nenhum item validado para salvar.")
                
        csv = st.session_state.df_trabalho.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
        st.download_button("📂 Exportar Excel (CSV) Atual", csv, "rtr_conciliacao_completa.csv", use_container_width=True)

# ==========================================
# 4. TELA PRINCIPAL (ABAS)
# ==========================================
st.markdown('<p1 class="main-header">⚖️ RTR Intelligence Pro</p>', unsafe_allow_html=True)

tab_processo, tab_historico = st.tabs(["🔄 Conciliação Ativa", "📚 Histórico de Auditoria"])

# ------------------------------------------
# ABA 1: PROCESSO ATUAL (UPLOAD & DASHBOARD)
# ------------------------------------------
with tab_processo:
    if st.session_state.df_trabalho is None:
        st.subheader("📬 Carregamento de Documentos")
        col_u1, col_u2 = st.columns(2)
        
        with col_u1:
            st.markdown("### 📊 Razão ERP")
            f_r = st.file_uploader("Arraste o relatório do SAP/ERP aqui", type=["csv", "xlsx"], key="u_erp")
        
        with col_u2:
            st.markdown("### 🏦 Extrato Bancário")
            f_e = st.file_uploader("Arraste o extrato bancário (OFX/CSV) aqui", type=["csv", "xlsx"], key="u_bank")

        if f_r and f_e:
            df_r = pd.read_excel(f_r) if f_r.name.endswith('xlsx') else pd.read_csv(f_r, sep=None, engine='python')
            df_e = pd.read_excel(f_e) if f_e.name.endswith('xlsx') else pd.read_csv(f_e, sep=None, engine='python')
            s_r, s_e = sugerir_colunas(df_r), sugerir_colunas(df_e)

            with st.container():
                st.markdown("---")
                st.markdown("#### 🛠️ Validação Automática de Colunas")
                c_map1, c_map2 = st.columns(2)
                with c_map1:
                    r_dt = st.selectbox("Data Razão", df_r.columns, index=s_r["data"])
                    r_vl = st.selectbox("Valor Razão", df_r.columns, index=s_r["valor"])
                    r_ds = st.selectbox("Descrição Razão", df_r.columns, index=s_r["desc"])
                with c_map2:
                    e_dt = st.selectbox("Data Extrato", df_e.columns, index=s_e["data"])
                    e_vl = st.selectbox("Valor Extrato", df_e.columns, index=s_e["valor"])
                    e_ds = st.selectbox("Descrição Extrato", df_e.columns, index=s_e["desc"])

                if st.button("🚀 INICIAR CONCILIAÇÃO IA", type="primary", use_container_width=True):
                    res = []
                    df_r['_v'], df_e['_v'] = df_r[r_vl].apply(normalizar_moeda), df_e[e_vl].apply(normalizar_moeda)
                    df_r['_d'] = pd.to_datetime(df_r[r_dt], dayfirst=True, errors='coerce')
                    df_e['_d'] = pd.to_datetime(df_e[e_dt], dayfirst=True, errors='coerce')
                    
                    for idx, row in df_r.iterrows():
                        cands = df_e[(df_e['_v'] == row['_v']) & (df_e['_d'].between(row['_d']-timedelta(days=3), row['_d']+timedelta(days=3)))]
                        if not cands.empty:
                            match_e = cands.iloc[0]
                            score = fuzz.token_sort_ratio(str(row[r_ds]), str(match_e[e_ds]))
                            status = "✅ Sugestão IA" if score > 75 else "💡 Revisar Match"
                            d_banco = match_e[e_dt].strftime('%d/%m/%Y') if hasattr(match_e[e_dt], 'strftime') else str(match_e[e_dt])
                            det = {"Razão": row[r_ds], "Extrato": match_e[e_ds], "Data_E": d_banco, "Valor_E": match_e['_v']}
                        else:
                            status, score, det = "❓ Pendente", 0, {"Razão": row[r_ds], "Extrato": "N/A", "Data_E": "-", "Valor_E": 0.0}
                        
                        res.append({
                            "Validar": False, "Data": row['_d'], "Descrição": row[r_ds], 
                            "Valor": row['_v'], "Status": status, "Confiança": score,
                            "Categoria": categorizar_ia(row[r_ds]), "detalhes": det
                        })
                    st.session_state.df_trabalho = pd.DataFrame(res)
                    st.rerun()

    else:
        df = st.session_state.df_trabalho
        
        # --- MÉTRICAS ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Volume Total", formatar_moeda_br(df['Valor'].abs().sum()))
        m2.metric("Confirmado", formatar_moeda_br(df[df['Validar']]['Valor'].abs().sum()))
        m3.metric("Matches Localizados", len(df[df['Confiança'] > 0]))
        m4.metric("Aguardando", len(df[~df['Validar']]))

        # --- GRÁFICOS ---
        st.markdown("---")
        g1, g2 = st.columns([2, 1])
        df_plot = df.copy()
        df_plot['Situacao'] = df_plot['Validar'].map({True: 'Validado', False: 'Pendente'})
        
        with g1:
            st.plotly_chart(px.bar(df_plot, x="Categoria", y="Valor", color="Situacao", title="Status por Categoria", barmode="group", template="plotly_dark", color_discrete_map={'Validado': '#10B981', 'Pendente': '#EF4444'}), use_container_width=True)
        with g2:
            st.plotly_chart(px.pie(df_plot, names="Status", hole=0.5, title="Composição de Match", template="plotly_dark"), use_container_width=True)

        # --- REVISÃO DETALHADA COM CATEGORIZAÇÃO ---
        st.markdown("---")
        st.subheader("🔍 Painel de Conferência e Auditoria")

        for i, row in df.iterrows():
            d_br = row['Data'].strftime('%d/%m/%Y') if hasattr(row['Data'], 'strftime') else "S/D"
            icon = "🟢" if row['Validar'] else ("🟡" if "IA" in row['Status'] else "🔴")
            header = f"{icon} {d_br} | {str(row['Descrição'])[:50]}... | {formatar_moeda_br(row['Valor'])}"
            
            with st.expander(header):
                st.markdown(f"""
                    <div class="expansion-card">
                        <div style="display: flex; justify-content: space-between;">
                            <div style="width: 45%;">
                                <h4 style="color: #00A8E8; border-bottom: 1px solid #005792;">📊 Razão ERP</h4>
                                <p><b>Data:</b> {d_br}</p>
                                <p><b>Histórico ERP:</b> {row['detalhes']['Razão']}</p>
                                <p><b>Valor ERP:</b> {formatar_moeda_br(row['Valor'])}</p>
                            </div>
                            <div style="width: 1px; background: #3e4e63; height: 160px; margin: 0 15px;"></div>
                            <div style="width: 45%;">
                                <h4 style="color: #10B981; border-bottom: 1px solid #10B981;">🏦 Extrato Bancário</h4>
                                <p><b>Data no Banco:</b> {row['detalhes']['Data_E']}</p>
                                <p><b>Histórico Banco:</b> {row['detalhes']['Extrato']}</p>
                                <p><b>Valor Banco:</b> {formatar_moeda_br(row['detalhes']['Valor_E'])}</p>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                # --- ÁREA DE EDIÇÃO ---
                c_edit1, c_edit2 = st.columns(2)
                with c_edit1:
                    idx_cat = st.session_state.categorias.index(row['Categoria']) if row['Categoria'] in st.session_state.categorias else 0
                    nova_categoria = st.selectbox(f"Alterar Categoria #{i}", st.session_state.categorias, index=idx_cat)
                    st.session_state.df_trabalho.at[i, 'Categoria'] = nova_categoria
                
                with c_edit2:
                    st.write("") 
                    st.write("") 
                    if not row['Validar']:
                        if st.button(f"Confirmar Lançamento #{i}", key=f"btn_{i}", use_container_width=True):
                            st.session_state.df_trabalho.at[i, 'Validar'] = True
                            st.session_state.df_trabalho.at[i, 'Status'] = "✅ Validado"
                            st.rerun()
                    else:
                        st.success("✅ Conciliado com sucesso.")

# ------------------------------------------
# ABA 2: HISTÓRICO DE AUDITORIA (ANÁLISE E BI)
# ------------------------------------------
with tab_historico:
    st.subheader("📚 Inteligência de Dados e Memória de Conciliações")
    df_hist = carregar_historico()
    
    if not df_hist.empty:
        # Preparação de Dados para o Histórico
        df_hist['Data'] = pd.to_datetime(df_hist['Data'], errors='coerce')
        
        # --- FILTROS SUPERIORES ---
        with st.container():
            c_f1, c_f2, c_f3 = st.columns([1, 1, 2])
            with c_f1:
                data_inicio = st.date_input("Início", df_hist['Data'].min())
            with c_f2:
                data_fim = st.date_input("Fim", df_hist['Data'].max())
            with c_f3:
                busca = st.text_input("🔍 Busca Global (Histórico/Descrição)", placeholder="Ex: Nome da Empresa, Nota Fiscal...")

            filtro_cat = st.multiselect("🏷️ Filtrar por Categorias", options=sorted(df_hist['Categoria'].unique().tolist()))

        # Aplicar Filtros
        mask = (df_hist['Data'].dt.date >= data_inicio) & (df_hist['Data'].dt.date <= data_fim)
        df_filtrado = df_hist.loc[mask].copy()
        
        if filtro_cat:
            df_filtrado = df_filtrado[df_filtrado['Categoria'].isin(filtro_cat)]
        if busca:
            df_filtrado = df_filtrado[df_filtrado['Descrição'].str.contains(busca, case=False, na=False)]

        # --- MÉTRICAS DO HISTÓRICO ---
        h_m1, h_m2, h_m3, h_m4 = st.columns(4)
        total_v = df_filtrado['Valor'].abs().sum()
        qtd_transacoes = len(df_filtrado)
        ticket_medio = total_v / qtd_transacoes if qtd_transacoes > 0 else 0
        
        h_m1.metric("Total Auditado", formatar_moeda_br(total_v))
        h_m2.metric("Transações", qtd_transacoes)
        h_m3.metric("Ticket Médio", formatar_moeda_br(ticket_medio))
        h_m4.metric("Categorias Ativas", df_filtrado['Categoria'].nunique())

        st.markdown("---")

        # --- DASHBOARD DE TENDÊNCIAS ---
        g_h1, g_h2 = st.columns([2, 1])

        with g_h1:
            # Agrupamento por dia para o gráfico de linha
            df_timeline = df_filtrado.groupby(df_filtrado['Data'].dt.date)['Valor'].sum().reset_index()
            fig_line = px.line(df_timeline, x='Data', y='Valor', 
                               title="📅 Evolução Financeira no Período",
                               template="plotly_dark",
                               line_shape="spline", 
                               render_mode="svg")
            fig_line.update_traces(line_color='#00A8E8', fill='tozeroy')
            st.plotly_chart(fig_line, use_container_width=True)

        with g_h2:
            # Treemap para ver representatividade
            fig_tree = px.treemap(df_filtrado, path=['Categoria'], values='Valor',
                                  title="📂 Peso por Categoria",
                                  template="plotly_dark",
                                  color_discrete_sequence=px.colors.qualitative.Safe)
            st.plotly_chart(fig_tree, use_container_width=True)

        # --- TABELA DE DADOS ---
        st.markdown("#### 📄 Detalhamento dos Registros")
        
        # Formatação para exibição na tabela
        df_display = df_filtrado.copy()
        df_display['Data'] = df_display['Data'].dt.strftime('%d/%m/%Y')
        
        # Oculta colunas técnicas
        colunas_show = ['Data', 'Descrição', 'Valor', 'Categoria', 'Status', 'Data_Processamento']
        st.dataframe(
            df_display[colunas_show].sort_values(by='Data', ascending=False), 
            use_container_width=True, 
            hide_index=True
        )
        
        # Botão para baixar apenas o que está filtrado
        csv_filter = df_filtrado.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
        st.download_button("📥 Baixar Relatório Filtrado (CSV)", csv_filter, "rtr_relatorio_auditoria.csv", "text/csv")

    else:
        st.warning("⚠️ O banco de dados histórico está vazio. Valide e salve conciliações na aba principal primeiro.")

# Rodapé customizado
st.caption("RTR Intelligence Pro v7.1 | Diretios reservados à Anderson Moegel desde 2026 | Desenvolvido com ❤️ para revolucionar a conciliação financeira.")