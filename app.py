import os
import streamlit as st
import pandas as pd
import time
import re
from config import TOLERANCIA_MINUTOS
from services import get_horario_padrao
from datetime import date, datetime
from services import (
    ler_registros_df,
    bater_ponto,
    verificar_login,
    obter_proximo_evento,
    atualizar_registro,
    ler_funcionarios_df,
    adicionar_funcionario,
    gerar_relatorio_organizado_df,
    gerar_arquivo_excel,
    ler_empresas,
    importar_funcionarios_em_massa,
    excluir_funcionario,
    init_db
)

st.set_page_config(
    page_title="Ponto Omega",
    page_icon="assets/logo.png",
    layout="wide"
)

if "DATABASE_URL" not in os.environ:
    db_url = st.secrets.get("DATABASE_URL")
    if db_url:
        os.environ["DATABASE_URL"] = db_url

def carregar_css_customizado():
    st.markdown("""
        <style>
            div[data-testid="stTextInput"] { max-width: 450px; margin: auto; }
            div[data-testid="stButton"] { max-width: 450px; margin: auto; }
            div[data-testid="stVerticalBlock"] div[data-testid="stContainer"][style*="border: 1px solid"] {
                padding-top: 1em !important; padding-bottom: 1em !important; margin-bottom: 10px !important;
            }
            div[data-testid="stAlert"][kind="info"] { background-color: #262730; border-radius: 10px; }
            button[data-testid="stTab"][aria-selected="true"] { color: #FFFFFF; }
            div[data-testid="stTabs"] button[aria-selected="true"]::after { background-color: #FFFFFF; }
            div[data-testid="stFormSubmitButton"] button {
                background-color: #F27421; color: #FFFFFF; border: none;
            }
            div[data-testid="stFormSubmitButton"] button:hover {
                background-color: #d8661c; color: #FFFFFF; border: none;
            }
        </style>
    """, unsafe_allow_html=True)

carregar_css_customizado()

@st.cache_resource(show_spinner=False)
def _init_db_once():
    init_db()
    return True

def _ensure_db_ready():
    try:
        _init_db_once()
    except Exception:
        st.error("Nao foi possivel conectar ao banco. Verifique DATABASE_URL e o acesso ao banco.")
        st.stop()

_ensure_db_ready()

@st.cache_data(ttl=30, show_spinner=False)
def _cached_registros_df():
    return ler_registros_df()

@st.cache_data(ttl=30, show_spinner=False)
def _cached_funcionarios_df():
    return ler_funcionarios_df()

@st.cache_data(ttl=30, show_spinner=False)
def _cached_empresas_df():
    return ler_empresas()

def _clear_cached_data():
    _cached_registros_df.clear()
    _cached_funcionarios_df.clear()
    _cached_empresas_df.clear()

if 'user_info' not in st.session_state:
    st.session_state.user_info = None
if 'edit_id' not in st.session_state:
    st.session_state.edit_id = None
if 'status_message' not in st.session_state:
    st.session_state.status_message = None


def tela_de_login():
    with st.container():
        _, col2, _ = st.columns([1, 2, 1])
        with col2:
            st.image("assets/logo.png", width=350)
            st.text("")
            cpf = st.text_input("CPF", label_visibility="collapsed", placeholder="Seu CPF (usuário)")
            senha = st.text_input("Sua Senha", type="password", label_visibility="collapsed", placeholder="Sua Senha (Código Forte)")
            if st.button("Entrar", type="primary", use_container_width=True):
                if cpf and senha:
                    user_info, erro = verificar_login(cpf, senha)
                    if erro:
                        st.error(erro)
                    else:
                        st.session_state.user_info = user_info
                        st.rerun()
                else:
                    st.warning("Por favor, preencha todos os campos.")

def tela_funcionario():
    st.title(f"Bem-vindo, {st.session_state.user_info['nome']}!")
    tab1, tab2 = st.tabs(["Registrar Ponto", "Meus Registros"])

    with tab1:
        st.header("Registro de Ponto")
        proximo_evento = obter_proximo_evento(st.session_state.user_info['cpf'])

        if 'botao_bloqueado' not in st.session_state:
            st.session_state.botao_bloqueado = False

        if proximo_evento == "Jornada Finalizada":
            st.info("Sua jornada de hoje já foi completamente registrada. Bom descanso!")
        else:
            botao_registrar = st.button(
                f"Confirmar {proximo_evento}",
                type="primary",
                use_container_width=True,
                disabled=st.session_state.botao_bloqueado
            )

            if botao_registrar:
                st.session_state.botao_bloqueado = True

                mensagem, tipo = bater_ponto(
                    st.session_state.user_info['cpf'],
                    st.session_state.user_info['nome']
                )

                if tipo == "success":
                    st.success(mensagem)
                    _clear_cached_data()
                    time.sleep(1)
                    st.rerun()  
                else:
                    st.error(mensagem)
                    st.session_state.botao_bloqueado = False


    with tab2:
        st.header("Histórico dos Meus Pontos")
        df_todos_registros = _cached_registros_df()
        meus_registros_df = df_todos_registros[df_todos_registros['Código Forte'] == st.session_state.user_info['codigo']]

        if meus_registros_df.empty:
            st.info("Você ainda não possui registros de ponto.")
        else:
            df_visualizacao = meus_registros_df.sort_values(by=["Data", "Hora"], ascending=False)
            for _, row in df_visualizacao.iterrows():
                with st.container(border=True):
                    data_br = datetime.strptime(row['Data'], '%Y-%m-%d').strftime('%d/%m/%Y')

                    diff = int(row['Diferença (min)']) if pd.notnull(row['Diferença (min)']) else 0
                    cor_diff = "green" if diff == 0 else "red" if diff > 0 else "lightgray"

                  
                    filial_raw = row.get('Filial')
                    try:
                        filial = int(filial_raw)
                    except Exception:
                        m = re.search(r'\d+', str(filial_raw))
                        filial = int(m.group()) if m else None

                    data_evento = datetime.strptime(row['Data'], '%Y-%m-%d').date()
                    hora_reg = datetime.strptime(row['Hora'], '%H:%M:%S').time()
                    dt_reg = datetime.combine(data_evento, hora_reg)

                    hora_prevista = get_horario_padrao(filial, row['Descrição'])
                    dt_prevista = datetime.combine(data_evento, hora_prevista)

                    raw = round((dt_reg - dt_prevista).total_seconds() / 60)

                    if diff == 0:
                        if raw < 0:
                            texto_diff = f"Em ponto ({abs(raw)} min adiantado)"
                        elif raw > 0:
                            texto_diff = f"Em ponto ({raw} min atrasado)"
                        else:
                            texto_diff = "Em ponto"
                    else:
                        texto_diff = f"{'+' if diff > 0 else ''}{diff} min ({'atrasado' if diff > 0 else 'adiantado'})"

                    col1, col2, col3, col4 = st.columns([3, 2, 2, 4])
                    col1.text(f"Evento: {row['Descrição']}")
                    col2.text(f"Data: {data_br}")
                    col3.text(f"Hora: {row['Hora']}")
                    col4.markdown(
                        f"Status: **<font color='{cor_diff}'>{texto_diff}</font>**",
                        unsafe_allow_html=True
                    )
                    if row.get('Observação'):
                        st.markdown(f"**Obs:** *{row['Observação']}*")

def tela_admin():
    st.title("Painel do Administrador")

    if st.session_state.status_message:
        msg, tipo = st.session_state.status_message
        if tipo == "success":
            st.success(msg)
        elif tipo == "warning":
            st.warning(msg)
        else:
            st.error(msg)
        st.session_state.status_message = None

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Relatório de Pontos", "Cadastrar Funcionário", "Visualizar Funcionários", "Importar Funcionários"]
    )

    with tab1:
        st.header("Filtros do Relatório")

        funcionarios_df = _cached_funcionarios_df()
        empresas_df = _cached_empresas_df()

        col1_filtros, col2_filtros, col3_filtros, col4_filtros = st.columns(4)

        with col1_filtros:
            opcoes_empresas = {0: "Todas as Empresas"}
            opcoes_empresas.update(dict(zip(empresas_df['id'], empresas_df['nome_empresa'])))
            empresa_selecionada_id = st.selectbox(
                "Filtrar por empresa:",
                options=list(opcoes_empresas.keys()),
                format_func=lambda x: opcoes_empresas[x]
            )

        with col2_filtros:
            if empresa_selecionada_id != 0:
                funcionarios_da_empresa = funcionarios_df[funcionarios_df['empresa_id'] == empresa_selecionada_id]
            else:
                funcionarios_da_empresa = (
                    funcionarios_df[funcionarios_df['role'] == 'employee']
                    if 'role' in funcionarios_df.columns else funcionarios_df
                )

            filiais = sorted(funcionarios_da_empresa['filial'].dropna().unique())
            filial_selecionada = st.selectbox("Filtrar por filial:", options=["Todas as Filiais"] + filiais)

        with col3_filtros:
            if filial_selecionada != "Todas as Filiais":
                funcionarios_da_filial = funcionarios_da_empresa[funcionarios_da_empresa['filial'] == filial_selecionada]
            else:
                funcionarios_da_filial = funcionarios_da_empresa

            setores = sorted(funcionarios_da_filial['tipo'].dropna().unique())
            setor_selecionado = st.selectbox("Filtrar por setor:", options=["Todos os Setores"] + setores)

        col5_filtros, = st.columns(1)

        with col5_filtros:

            base_func = funcionarios_da_filial
            if setor_selecionado != "Todos os Setores":
                base_func = base_func[base_func['tipo'] == setor_selecionado]

            if not base_func.empty:
                base_func = base_func.sort_values('nome')
                opcoes_func = ["Todos os Funcionários"] + [
                    f"{row['nome']} ({row['codigo']})" for _, row in base_func.iterrows()
                ]
            else:
                opcoes_func = ["Todos os Funcionários"]

            funcionario_selecionado = st.selectbox("Filtrar por funcionário:", options=opcoes_func)


        with col4_filtros:
            data_inicio = st.date_input("Data Início", value=date.today().replace(day=1), format="DD/MM/YYYY")
            data_fim = st.date_input("Data Fim", value=date.today(), format="DD/MM/YYYY")

        st.divider()
        st.header("Relatório de Pontos")

        df_registros = _cached_registros_df()
        df_filtrado = df_registros.copy()

        if empresa_selecionada_id != 0:
            df_filtrado = df_filtrado[df_filtrado['Empresa'] == opcoes_empresas[empresa_selecionada_id]]
        if filial_selecionada != "Todas as Filiais":
            df_filtrado = df_filtrado[df_filtrado['Filial'] == filial_selecionada]
        if setor_selecionado != "Todos os Setores":
            df_filtrado = df_filtrado[df_filtrado['Setor'] == setor_selecionado]

        if funcionario_selecionado != "Todos os Funcionários":
            import re as _re
            m = _re.search(r"\((.*?)\)$", funcionario_selecionado)
            cod_forte_escolhido = m.group(1) if m else None
            if cod_forte_escolhido:
                df_filtrado = df_filtrado[df_filtrado['Código Forte'] == cod_forte_escolhido]


        if not df_filtrado.empty:
            df_filtrado['Data_dt'] = pd.to_datetime(df_filtrado['Data'], format='%Y-%m-%d', errors='coerce').dt.date
            df_filtrado = df_filtrado.dropna(subset=['Data_dt'])
            df_filtrado = df_filtrado[(df_filtrado['Data_dt'] >= data_inicio) & (df_filtrado['Data_dt'] <= data_fim)]

        if df_filtrado.empty:
            st.info("Nenhum registro encontrado para os filtros selecionados.")
        else:
            st.subheader("Visualização dos Eventos")
            df_visualizacao = df_filtrado.sort_values(by=["Data_dt", "Hora"], ascending=False)

            for index, row in df_visualizacao.iterrows():
                registro_id = row['ID']
                with st.container(border=True):
                    data_br = row['Data_dt'].strftime('%d/%m/%Y')

                    filial_raw = row['Filial']
                    try:
                        filial = int(filial_raw)
                    except Exception:
                        m = re.search(r'\d+', str(filial_raw))
                        filial = int(m.group()) if m else None

                    data_evento = datetime.strptime(row['Data'], '%Y-%m-%d').date()
                    hora_reg = datetime.strptime(row['Hora'], '%H:%M:%S').time()
                    dt_reg = datetime.combine(data_evento, hora_reg)

                    horario_padrao = get_horario_padrao(filial, row['Descrição'])
                    dt_pad = datetime.combine(data_evento, horario_padrao)

                    raw = round((dt_reg - dt_pad).total_seconds() / 60)

                    if abs(raw) <= TOLERANCIA_MINUTOS:
                       texto_diff = "Em ponto"
                       cor_diff = "green"
                    elif raw > 0:
                       atraso_liquido = raw - TOLERANCIA_MINUTOS
                       texto_diff = f"Atrasado ({atraso_liquido} min)"
                       cor_diff = "red"
                    else:
                       adiantado_liquido = abs(raw) - TOLERANCIA_MINUTOS
                       texto_diff = f"Adiantado ({adiantado_liquido} min)"
                       cor_diff = "orange"


    

                    col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 3, 1])
                    col1.text(f"Nome: {row['Nome']}")
                    col2.text(f"Empresa: {row['Empresa']}")
                    col3.text(f"Evento: {row['Descrição']}")
                    col4.text(f"Data: {data_br}")
                    col5.markdown(
                        f"Hora: {row['Hora']} | Status: <font color='{cor_diff}'>**{texto_diff}**</font>",
                        unsafe_allow_html=True
                    )

                    if col6.button("Editar", key=f"edit_{registro_id}_{index}"):
                        st.session_state.edit_id = registro_id
                        st.rerun()

                    if st.session_state.edit_id == registro_id:
                        edit_col1, edit_col2 = st.columns(2)
                        with edit_col1:
                            novo_horario = st.text_input("Nova Hora (HH:MM:SS):", value=row['Hora'], key=f"hora_{registro_id}")
                        with edit_col2:
                            nova_obs = st.text_area("Observação:", value=row.get('Observação', ''), key=f"obs_{registro_id}")
                        col_save, col_cancel, _ = st.columns([1, 1, 5])
                        if col_save.button("Salvar", key=f"save_{registro_id}", type="primary"):
                            horario_mudou = novo_horario.strip() != row['Hora'].strip()
                            obs_mudou = nova_obs.strip() != str(row.get('Observação', '')).strip()
                            if horario_mudou or obs_mudou:
                                horario_para_atualizar = novo_horario.strip() if horario_mudou else None
                                obs_para_atualizar = nova_obs.strip() if obs_mudou else None
                                msg, tipo = atualizar_registro(registro_id, novo_horario=horario_para_atualizar, nova_observacao=obs_para_atualizar)
                                if tipo == "success":
                                    _clear_cached_data()
                                st.session_state.status_message = (msg, tipo)
                            st.session_state.edit_id = None
                            st.rerun()
                        if col_cancel.button("Cancelar", key=f"cancel_{registro_id}"):
                            st.session_state.edit_id = None
                            st.rerun()
                    elif row.get('Observação'):
                        st.markdown(f"**Obs:** *{row['Observação']}*")

            st.divider()
            st.subheader("Exportar Relatório Completo")

            if empresa_selecionada_id != 0:
                empresa_info = empresas_df[empresas_df['id'] == empresa_selecionada_id].iloc[0]
                nome_empresa_relatorio = empresa_info['nome_empresa']
                cnpj_relatorio = empresa_info['cnpj']
            else:
                nome_empresa_relatorio = "Todas as Empresas"
                cnpj_relatorio = None

            df_organizado = gerar_relatorio_organizado_df(df_filtrado)
            df_bruto = df_filtrado.sort_values(by=["Data_dt", "Hora"]).copy()
            df_bruto['Data'] = pd.to_datetime(df_bruto['Data']).dt.strftime('%d/%m/%Y')

            try:
                excel_buffer = gerar_arquivo_excel(
                    df_organizado,
                    df_bruto.drop(columns=['Data_dt']),
                    nome_empresa_relatorio,
                    cnpj_relatorio,
                    data_inicio,
                    data_fim
                )
            except ModuleNotFoundError:
                st.error("Geracao de Excel indisponivel: pacote openpyxl nao instalado.")
            except Exception as e:
                st.error(f"Erro ao gerar Excel: {e}")
            else:
                st.download_button(
                    label="Baixar Relatório Filtrado em Excel",
                    data=excel_buffer,
                    file_name="relatorio_ponto_filtrado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

    with tab2:
        st.header("Cadastrar Novo Funcionário")
        with st.form("add_employee_form", clear_on_submit=True):
            cpf = st.text_input("CPF do Funcionário (será o usuário)")
            novo_codigo = st.text_input("Código Forte (será a senha)")
            novo_nome = st.text_input("Nome Completo")
            nome_empresa = st.text_input("Nome da Empresa")
            cnpj = st.text_input("CNPJ da Empresa")
            filial = st.text_input("Filial (ex: Matriz, Filial 02)")
            cod_tipo = st.text_input("Código do Setor")
            tipo = st.text_input("Nome do Setor")
            submitted = st.form_submit_button("Adicionar Funcionário")
            if submitted:
                msg, tipo = adicionar_funcionario(
                    novo_codigo.strip(), novo_nome.strip(), nome_empresa.strip(),
                    cnpj.strip(), cpf.strip(), cod_tipo.strip(), tipo.strip(), filial.strip()
                )
                if tipo == "success":
                    _clear_cached_data()
                st.session_state.status_message = (msg, tipo)
                st.rerun()

    with tab3:
        st.header("Funcionários Cadastrados no Sistema")
        todos_funcionarios_df = _cached_funcionarios_df()
        df_exibicao = todos_funcionarios_df[todos_funcionarios_df['role'] == 'employee']
        if df_exibicao.empty:
            st.info("Nenhum funcionário cadastrado no sistema.")
        else:
            df_final = df_exibicao[['cpf', 'codigo', 'nome', 'nome_empresa', 'filial', 'tipo']].rename(columns={
                'cpf': 'CPF (Usuário)', 'codigo': 'CodForte (Senha)', 'nome': 'Nome',
                'nome_empresa': 'Empresa', 'filial': 'Filial', 'tipo': 'Setor'
            })

            df_final_com_acao = df_final.copy()
            df_final_com_acao['Ação'] = False

            edited_df = st.data_editor(
                df_final_com_acao,
                column_config={"Ação": st.column_config.CheckboxColumn("Excluir?", default=False)},
                hide_index=True, use_container_width=True,
                disabled=['CPF (Usuário)', 'CodForte (Senha)', 'Nome', 'Empresa', 'Filial', 'Setor']
            )
            funcionario_para_excluir = edited_df[edited_df["Ação"]]
            if not funcionario_para_excluir.empty:
                nome_para_excluir = funcionario_para_excluir.iloc[0]['Nome']
                cpf_para_excluir = funcionario_para_excluir.iloc[0]['CPF (Usuário)']
                st.warning(f"Você tem certeza que deseja excluir **{nome_para_excluir}** (CPF: {cpf_para_excluir})?")
                col1, col2, _ = st.columns([1, 1, 4])
                with col1:
                    if st.button("Sim, excluir", type="primary", use_container_width=True):
                        msg, tipo = excluir_funcionario(cpf_para_excluir)
                        if tipo == "success":
                            _clear_cached_data()
                        st.session_state.status_message = (msg, tipo)
                        st.rerun()
                with col2:
                    if st.button("Cancelar", use_container_width=True):
                        st.rerun()

    with tab4:
        st.header("Importar Funcionários em Lote via CSV")
        st.info("O arquivo CSV precisa ter as colunas: `Arquivo`, `Empresa`, `CNPJ`, `CodTipo`, `Tipo`, `CodForte`, `Nome` e `CPF`. O CPF será o usuário e o Código Forte a senha.")
        arquivo_csv = st.file_uploader("Selecione o arquivo CSV", type=["csv"])
        if st.button("Iniciar Importação", type="primary", use_container_width=True):
            if arquivo_csv:
                with st.spinner("Processando..."):
                    try:
                        df_para_importar = pd.read_csv(arquivo_csv, sep=';', encoding='latin-1', dtype=str)
                        df_para_importar.columns = [col.strip().upper() for col in df_para_importar.columns]
                        sucesso, ignorados, erros = importar_funcionarios_em_massa(df_para_importar)
                        if sucesso:
                            _clear_cached_data()
                        st.success(f"{sucesso} funcionários importados!")
                        if ignorados:
                            st.warning(f"{ignorados} ignorados (CPF já existe).")
                        if erros:
                            st.error("Ocorreram erros:")
                            for erro in erros:
                                st.code(erro)
                    except Exception as e:
                        st.error(f"Erro ao ler o arquivo: {e}")
            else:
                st.warning("Por favor, selecione um arquivo CSV.")

if st.session_state.user_info:
    st.sidebar.image("assets/logo.png", use_container_width=True)
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()
    if st.session_state.user_info.get("role") == "admin":
        tela_admin()
    else:
        tela_funcionario()
else:
    tela_de_login()
