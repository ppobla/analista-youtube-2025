import streamlit as st
from supabase import create_client, Client
from gotrue.errors import AuthApiError
import requests
from PIL import Image
import io
import urllib.parse
import os
import toml
import json
import re
import base64
from datetime import datetime
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
from googleapiclient.discovery import build

# Importações da IA (Agno/Phi)
from phi.agent import Agent
from phi.model.deepseek import DeepSeekChat
from phi.tools.duckduckgo import DuckDuckGo
# --- INICIALIZAÇÃO DE VARIÁVEIS GLOBAIS (Evita o NameError) ---
DEEPSEEK_API_KEY = None
SUPABASE_URL = None
SUPABASE_KEY = None
YOUTUBE_API_KEY = None



# --- 1. FUNÇÃO PARA CARREGAR CHAVES (HÍBRIDA) ---
def carregar_chaves_seguras():
    """Tenta carregar chaves do Streamlit Cloud ou pede na tela se não achar"""
    chaves = {
        "DEEPSEEK_API_KEY": st.secrets.get("DEEPSEEK_API_KEY"),
        "SUPABASE_URL": st.secrets.get("SUPABASE_URL"),
        "SUPABASE_KEY": st.secrets.get("SUPABASE_KEY"),
        "YOUTUBE_API_KEY": st.secrets.get("YOUTUBE_API_KEY")
    }
    
    # Se estiver rodando local e tiver arquivo .env ou secrets.toml, tenta carregar
    if not all(chaves.values()):
        try:
            import dotenv
            dotenv.load_dotenv()
            for k in chaves:
                if not chaves[k]: chaves[k] = os.getenv(k)
        except:
            pass

    # Verifica se ainda falta algo
    if not all(chaves.values()):
        return None # Retorna None para indicar que precisa configurar
    return chaves

# --- 2. SISTEMA DE LOGIN (SUPABASE AUTH) ---
def tela_login(supabase_client):
    """Renderiza a tela de login e gerencia a autenticação"""
    
    # CSS para deixar a tela bonita
    st.markdown("""
    <style>
        .box-login {
            max-width: 400px;
            margin: 0 auto;
            padding: 30px;
            border-radius: 10px;
            background-color: #f0f2f6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .titulo-login { text-align: center; color: #1e3a8a; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 class='titulo-login'>🔐 Acesso Restrito</h1>", unsafe_allow_html=True)
        st.markdown("<div class='box-login'>", unsafe_allow_html=True)
        
        email = st.text_input("E-mail", placeholder="seu@email.com")
        senha = st.text_input("Senha", type="password", placeholder="••••••••")
        
        col_entrar, col_criar = st.columns(2)
        
        with col_entrar:
            if st.button("Entrar", type="primary", use_container_width=True):
                try:
                    # A mágica do Supabase acontece aqui
                    sessao = supabase_client.auth.sign_in_with_password({"email": email, "password": senha})
                    st.session_state['user'] = sessao.user
                    st.session_state['access_token'] = sessao.session.access_token
                    st.success("Login realizado! Redirecionando...")
                    st.rerun()
                except AuthApiError as e:
                    st.error(f"Erro de login: {e.message}")
                except Exception as e:
                    st.error(f"Erro inesperado: {str(e)}")
        
        st.markdown("</div>", unsafe_allow_html=True)

# --- 3. TELA DE CONFIGURAÇÃO INICIAL (SETUP) ---
def tela_configuracao_inicial():
    st.warning("⚠️ Sistema não configurado. Insira as chaves para conectar ao servidor.")
    with st.form("setup_keys"):
        supa_url = st.text_input("Supabase URL")
        supa_key = st.text_input("Supabase Key (Anon)")
        deepseek = st.text_input("DeepSeek API Key", type="password")
        youtube = st.text_input("YouTube API Key", type="password")
        
        if st.form_submit_button("Salvar e Conectar"):
            # Salva na sessão para usar agora
            st.session_state['temp_keys'] = {
                "SUPABASE_URL": supa_url,
                "SUPABASE_KEY": supa_key,
                "DEEPSEEK_API_KEY": deepseek,
                "YOUTUBE_API_KEY": youtube
            }
            st.rerun()

# --- 4. FUNÇÃO PRINCIPAL MODIFICADA ---
def main():
    st.set_page_config(page_title="YouTube Automation CEO", page_icon="🎬", layout="wide")

    # 1. CARREGA AS CHAVES
    keys = carregar_chaves_seguras()
    if not keys and 'temp_keys' in st.session_state:
        keys = st.session_state['temp_keys']

    # 2. SE NÃO TIVER CHAVES, PARA TUDO E PEDE SETUP
    if not keys:
        tela_configuracao_inicial()
        st.stop()

    # 3. CONECTA NO SUPABASE (CRIA A VARIÁVEL 'supabase')
    # --- IMPORTANTE: Esta parte tem que vir ANTES de usar o banco ---
    try:
        supabase = create_client(keys["SUPABASE_URL"], keys["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"Erro ao conectar no banco de dados: {e}")
        st.stop()

    # 4. VERIFICA LOGIN (Usa a variável 'supabase' criada acima)
    if 'user' not in st.session_state:
        tela_login(supabase)
        st.stop()

    # 5. SIDEBAR E LOGOUT
    with st.sidebar:
        st.write(f"👤 **{st.session_state['user'].email}**")
        if st.button("Sair (Logout)"):
            supabase.auth.sign_out()
            del st.session_state['user']
            st.rerun()
        st.divider()

    # 6. DEFINE GLOBAIS
    global DEEPSEEK_API_KEY, SUPABASE_URL, SUPABASE_KEY, YOUTUBE_API_KEY
    DEEPSEEK_API_KEY = keys["DEEPSEEK_API_KEY"]
    SUPABASE_URL = keys["SUPABASE_URL"]
    SUPABASE_KEY = keys["SUPABASE_KEY"]
    YOUTUBE_API_KEY = keys["YOUTUBE_API_KEY"]

    # 7. AGORA SIM: INICIALIZA O BANCO (Passando 'supabase')
    # --- Como o 'supabase' já foi criado no passo 3, aqui não dará erro ---
    if "db" not in st.session_state:
        st.session_state.db = YouTubeAutomationDatabase(supabase)

    # 8. INICIALIZA O SISTEMA DE IA
    if "sistema" not in st.session_state:
        st.session_state.sistema = SistemaYouTubeAutomation()

    # ... O RESTO DO SEU CÓDIGO (Interface, Header, etc.) CONTINUA ABAIXO ...

# ... O RESTO DO CÓDIGO CONTINUA IGUAL ...

# Função para obter ano atual
def ano_atual():
    return datetime.now().year

# 2. SISTEMA DE BANCO DE DADOS PARA YOUTUBE AUTOMATION
class YouTubeAutomationDatabase:
    """Banco de dados na Nuvem (Supabase)"""
    
    def __init__(self, supabase_client):
        # Recebe o cliente conectado e guarda dentro da classe
        self.supabase = supabase_client

    def criar_projeto(self, nicho, descricao="Novo Projeto"):
        codigo = f"YT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        data = {
            "codigo_projeto": codigo,
            "nicho": nicho,
            "descricao": descricao,
            "data_inicio": datetime.now().isoformat()
        }
        # Agora usa self.supabase (o cliente interno)
        response = self.supabase.table("projetos").insert(data).execute()
        if response.data:
            return response.data[0]
        return None
    
    def registrar_analise_nicho(self, projeto_id, ideia_canal, dados_analise):
        data = {
            "projeto_id": projeto_id,
            "ideia_canal": ideia_canal,
            "concorrentes_analisados": dados_analise.get('concorrentes_analisados', 0),
            "rpm_medio": dados_analise.get('rpm_medio', 0.0),
            "concorrencia_nivel": dados_analise.get('concorrencia_nivel', 'MEDIA'),
            "potencial_lucratividade": dados_analise.get('potencial_lucratividade', 'MODERADO'),
            "elementos_80_20": dados_analise.get('elementos_80_20', [])
        }
        return self.supabase.table("analises_nicho").insert(data).execute()
    
    def registrar_otimizacao(self, projeto_id, dados_otimizacao):
        data = {
            "projeto_id": projeto_id,
            "titulos_virais": dados_otimizacao.get('titulos_virais', []),
            "thumbnail_desc": dados_otimizacao.get('thumbnail_desc', ''),
            "keywords": dados_otimizacao.get('keywords', []),
            "estrategia_ctr": dados_otimizacao.get('estrategia_ctr', ''),
            "ferramentas_automacao": dados_otimizacao.get('ferramentas_automacao', []),
            "plano_globalizacao": dados_otimizacao.get('plano_globalizacao', '')
        }
        return self.supabase.table("otimizacoes").insert(data).execute()
    
    def listar_projetos(self):
        # Busca projetos ordenados por data
        response = self.supabase.table("projetos").select("*").order("data_inicio", desc=True).execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
        
    def obter_historico_projeto(self, projeto_id):
        # Busca dados relacionados
        proj = self.supabase.table("projetos").select("*").eq("id", projeto_id).execute()
        analises = self.supabase.table("analises_nicho").select("*").eq("projeto_id", projeto_id).execute()
        otimizacoes = self.supabase.table("otimizacoes").select("*").eq("projeto_id", projeto_id).execute()
        
        return {
            "projeto": proj.data[0] if proj.data else {},
            "analises": analises.data,
            "otimizacoes": otimizacoes.data
        }
# 3. FUNÇÕES DE EXPORTAÇÃO PARA DOC/PDF
def criar_documento_html(conteudo, tipo_relatorio, projeto_info):
    """Cria documento HTML formatado para exportação"""
    
    ano = ano_atual()
    
    # Estilos CSS para o documento (COM A COR DO COPYWRITER ADICIONADA)
    css_estilos = """
    <style>
        body {
            font-family: 'Arial', sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 210mm;
            margin: 0 auto;
            padding: 20mm;
            background: #ffffff;
        }
        .header {
            text-align: center;
            border-bottom: 3px solid #3b82f6;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .logo {
            font-size: 24px;
            font-weight: bold;
            color: #3b82f6;
            margin-bottom: 10px;
        }
        .subtitle { color: #666; font-size: 14px; }
        .project-info {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 25px;
            border-left: 4px solid #3b82f6;
        }
        .section { margin-bottom: 30px; page-break-inside: avoid; }
        h1 { color: #1e40af; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; margin-top: 25px; }
        h2 { color: #374151; margin-top: 20px; }
        h3 { color: #4b5563; }
        
        /* BADGES DOS AGENTES */
        .agent-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 12px;
            margin-bottom: 10px;
        }
        .hunter-badge { background: #0f766e; color: white; }
        .booster-badge { background: #7c3aed; color: white; }
        .ceo-badge { background: #1e3a8a; color: white; }
        .copy-badge { background: #be185d; color: white; } /* <--- NOVA COR ROSA */
        
        ul, ol { padding-left: 25px; margin: 10px 0; }
        li { margin: 5px 0; }
        .footer {
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            color: #6b7280;
            font-size: 12px;
        }
        .timestamp { color: #9ca3af; font-size: 11px; text-align: right; }
    </style>
    """
    
    # Lógica do Badge (ATUALIZADA PARA O COPYWRITER)
    if tipo_relatorio == "hunter":
        badge_html = '<span class="agent-badge hunter-badge">🔍 ESPECIALISTA HUNTER</span>'
        titulo_agente = "Relatório de Análise de Nicho"
    elif tipo_relatorio == "booster":
        badge_html = '<span class="agent-badge booster-badge">🚀 ESPECIALISTA BOOSTER</span>'
        titulo_agente = "Relatório de Otimização e SEO"
    elif tipo_relatorio == "roteiro": # <--- NOVO BLOCO
        badge_html = '<span class="agent-badge copy-badge">✍️ ROTEIRISTA VIRAL</span>'
        titulo_agente = "Roteiro de Vídeo Completo"
    else:
        badge_html = '<span class="agent-badge ceo-badge">🎯 DECISÃO DO CEO</span>'
        titulo_agente = "Relatório Executivo de Decisão"
    
    # ... O resto da função continua igual (projeto_info, html = f"...", etc)
    
    # Informações do projeto
    projeto_html = ""
    if projeto_info:
        codigo = projeto_info.get('codigo', projeto_info.get('codigo_projeto', 'N/A'))
        nicho = projeto_info.get('nicho', 'N/A')
        projeto_html = f"""
        <div class="project-info">
            <div><strong>Projeto:</strong> {codigo}</div>
            <div><strong>Nicho:</strong> {nicho}</div>
            <div><strong>Data da Análise:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</div>
            <div><strong>Ano de Referência:</strong> {ano}</div>
        </div>
        """
    
    # Estrutura do documento HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{titulo_agente} - {projeto_info.get('codigo', 'Projeto')}</title>
        {css_estilos}
    </head>
    <body>
        <div class="header">
            <div class="logo">🎬 YouTube Automation CEO</div>
            <div class="subtitle">Sistema de Análise e Otimização de Canais</div>
        </div>
        
        {badge_html}
        <h1>{titulo_agente}</h1>
        
        {projeto_html}
        
        <div class="timestamp">
            Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        </div>
        
        <div class="content">
            {conteudo}
        </div>
        
        <div class="footer">
            <p>Documento gerado automaticamente pelo Sistema YouTube Automation CEO</p>
            <p>© {ano} - Todos os direitos reservados</p>
            <p>Confidencial - Uso interno</p>
        </div>
    </body>
    </html>
    """
    
    return html

def limpar_conteudo_para_exportacao(conteudo):
    """Limpa metadados e formata para documento"""
    if not conteudo:
        return ""
    
    # Remover content=' e metadados
    conteudo_str = str(conteudo)
    
    # Remover padrões técnicos
    padroes_remover = [
        r"content='(.*?)'",
        r"name=None.*?\)",
        r"tool_call_id=.*?\)",
        r"metrics=\{.*?\}",
        r"Message\(.*?\)",
        r"run_id='[^']*'",
        r"agent_id='[^']*'",
        r"session_id='[^']*'",
        r"model='[^']*'",
        r"defaultdict\(.*?\)",
        r"content_type='.*?'",
        r"event='.*?'",
        r"audio=None.*?videos=None",
        r"references=None",
        r"created_at=\d+",
        r"stop_after_tool_call=False",
        r"tool_name=None.*?tool_args=None",
        r"tool_call_error=None.*?extra_data=None"
    ]
    
    for padrao in padroes_remover:
        conteudo_str = re.sub(padrao, '', conteudo_str, flags=re.DOTALL)
    
    # Melhorar formatação markdown para HTML
    # Títulos
    conteudo_str = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', conteudo_str, flags=re.MULTILINE)
    conteudo_str = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', conteudo_str, flags=re.MULTILINE)
    conteudo_str = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', conteudo_str, flags=re.MULTILINE)
    
    # Negrito
    conteudo_str = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', conteudo_str)
    
    # Listas
    conteudo_str = re.sub(r'^\* (.*?)$', r'<li>\1</li>', conteudo_str, flags=re.MULTILINE)
    conteudo_str = re.sub(r'^- (.*?)$', r'<li>\1</li>', conteudo_str, flags=re.MULTILINE)
    conteudo_str = re.sub(r'^\d+\. (.*?)$', r'<li>\1</li>', conteudo_str, flags=re.MULTILINE)
    
    # Agrupar listas
    lines = conteudo_str.split('\n')
    html_lines = []
    in_list = False
    
    for line in lines:
        if '<li>' in line:
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            html_lines.append(line)
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(line)
    
    if in_list:
        html_lines.append('</ul>')
    
    conteudo_str = '\n'.join(html_lines)
    
    # Adicionar divs de seção
    conteudo_str = re.sub(r'<h2>(.*?)</h2>', 
                         r'<div class="section"><h2>\1</h2>', 
                         conteudo_str)
    
    # Limpar múltiplas quebras
    conteudo_str = re.sub(r'\n{3,}', '\n\n', conteudo_str)
    conteudo_str = re.sub(r'\s{2,}', ' ', conteudo_str)
    
    return conteudo_str

def exportar_para_html(conteudo, tipo_relatorio, projeto_info):
    """Exporta conteúdo para HTML"""
    conteudo_limpo = limpar_conteudo_para_exportacao(conteudo)
    html = criar_documento_html(conteudo_limpo, tipo_relatorio, projeto_info)
    return html

def get_binary_file_downloader_html(bin_data, file_label, file_name):
    """Cria link de download para arquivo"""
    b64 = base64.b64encode(bin_data).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="{file_name}">{file_label}</a>'
    return href

def exportar_relatorio(conteudo, tipo_relatorio, projeto_info, formato="html"):
    """Exporta relatório no formato especificado (COM LIMPEZA DE DADOS)"""
    
    # 1. LIMPEZA PROFUNDA (Igual fizemos no Main)
    if not conteudo:
        st.warning("Nenhum conteúdo para exportar")
        return None
        
    # Converte para string e remove metadados técnicos do Agente
    conteudo_limpo = str(conteudo)
    conteudo_limpo = re.sub(r"Message\(.*?\)", "", conteudo_limpo, flags=re.DOTALL)
    conteudo_limpo = re.sub(r"content='(.*?)'", r"\1", conteudo_limpo, flags=re.DOTALL)
    conteudo_limpo = re.sub(r"metrics=\{.*?\}", "", conteudo_limpo, flags=re.DOTALL)
    conteudo_limpo = conteudo_limpo.replace("\\n", "\n").replace("content_type='str'", "")
    
    # Remove linhas vazias excessivas
    conteudo_limpo = re.sub(r'\n\s*\n', '\n\n', conteudo_limpo)
    
    try:
        # Nome do arquivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if isinstance(projeto_info, dict):
            codigo = projeto_info.get('codigo', projeto_info.get('codigo_projeto', 'projeto'))
        else:
            codigo = getattr(projeto_info, 'codigo_projeto', 'projeto') # Fallback se for objeto
        
        if tipo_relatorio == "hunter":
            prefixo = "HUNTER"
        elif tipo_relatorio == "booster":
            prefixo = "BOOSTER"
        elif tipo_relatorio == "roteiro":
            prefixo = "ROTEIRO"
        elif tipo_relatorio == "full":
            prefixo = "COMPLETO"
        else:
            prefixo = "CEO"
        
        if formato == "html":
            # Gerar HTML
            html_content = criar_documento_html(conteudo_limpo, tipo_relatorio, projeto_info)
            file_name = f"{prefixo}_{codigo}_{timestamp}.html"
            
            # Criar botão de download
            b64 = base64.b64encode(html_content.encode()).decode()
            href = f'<a href="data:text/html;base64,{b64}" download="{file_name}" style="text-decoration: none;">'
            href += f'<button style="background-color: #3b82f6; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; display: flex; align-items: center; gap: 8px;">'
            href += f'📄 Download HTML</button></a>'
            
            st.markdown(href, unsafe_allow_html=True)
            
            # Visualização rápida
            with st.expander("📋 Visualizar Documento"):
                st.components.v1.html(html_content, height=600, scrolling=True)
            
            return html_content
            
        elif formato == "txt":
            # Gerar texto puro
            file_name = f"{prefixo}_{codigo}_{timestamp}.txt"
            txt_content = f"""
============================================
RELATÓRIO {prefixo} - YouTube Automation CEO
============================================

Projeto: {codigo}
Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}
Ano: {ano_atual()}

{'='*50}

{conteudo_limpo}

{'='*50}

Documento gerado automaticamente
Sistema YouTube Automation CEO
© {ano_atual()} - Confidencial
            """
            
            st.download_button(
                label="📝 Download TXT",
                data=txt_content,
                file_name=file_name,
                mime="text/plain",
                key=f"download_txt_{tipo_relatorio}_{timestamp}"
            )
            
            return txt_content
            
    except Exception as e:
        st.error(f"Erro ao exportar relatório: {e}")
        return None
    
# 4. GERENTE EXECUTIVO (CEO)
@st.cache_resource
def criar_gerente_executivo():
    ano = ano_atual()
    return Agent(
        model=DeepSeekChat(api_key=DEEPSEEK_API_KEY, temperature=0.7),
        name="CEO_YouTube_Automation",
        role="Gerente Executivo de Operações YouTube Cash Cow",
        description=f"CEO especializado em construir canais dark lucrativos e escaláveis para {ano}",
        instructions=[
            f"VOCÊ É O CEO: Tome decisões estratégicas finais baseadas nas análises dos especialistas para {ano}.",
            "VISÃO MACRO: Avalie ROI, escalabilidade e riscos de cada oportunidade.",
            "APROVAÇÃO DE NICHOS: Selecione a melhor ideia de canal baseada em dados.",
            "SÍNTESE: Integre as descobertas do Hunter e do Booster em um plano de ação coeso.",
            "DECISÃO FINAL: Defina o 'Próximo Passo Imediato' para começar a faturar.",
            "FOCO EM LUCRO: Priorize oportunidades com alto RPM, baixa concorrência e escalabilidade.",
            f"ATUALIZAÇÃO: Considere tendências atuais do YouTube em {ano}.",
            "FORMATO: Use Português claro, estruturado com bullet points e métricas.",
            "RETORNE APENAS O CONTEÚDO DA RESPOSTA, SEM METADADOS TÉCNICOS."
        ],
        tools=[DuckDuckGo()],
        show_tool_calls=False,
        markdown=True
    )

# 5. AGENTES ESPECIALISTAS
def ferramenta_youtube_search(query: str):
    """
    Usa a API oficial do YouTube para encontrar vídeos reais e suas métricas.
    Útil para validar se um nicho tem visualizações reais recentes.
    """
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        
        # Busca vídeos recentes (publicados este ano)
        search_response = youtube.search().list(
            q=query,
            part='id,snippet',
            maxResults=5,
            order='viewCount',
            type='video',
            publishedAfter=f'{ano_atual()}-01-01T00:00:00Z'
        ).execute()
        
        resultados = []
        for item in search_response.get('items', []):
            video_id = item['id']['videoId']
            # Pega contagem de views exata
            stats = youtube.videos().list(part='statistics', id=video_id).execute()
            if stats['items']:
                views = stats['items'][0]['statistics'].get('viewCount', '0')
                resultados.append({
                    "titulo": item['snippet']['title'],
                    "canal": item['snippet']['channelTitle'],
                    "views": f"{int(views):,}",
                    "publicado_em": item['snippet']['publishedAt'][:10],
                    "link": f"https://www.youtube.com/watch?v={video_id}"
                })
        return json.dumps(resultados, ensure_ascii=False)
    except Exception as e:
        return f"Erro na busca do YouTube: {str(e)}"
def criar_agente_hunter():
    ano = ano_atual()
    return Agent(
        model=DeepSeekChat(api_key=DEEPSEEK_API_KEY, temperature=0.5),
        name="Hunter_YouTube",
        role="Especialista em Pesquisa e Modelagem de Conteúdo",
        instructions=[
            f"VOCÊ É O HUNTER: Especialista em encontrar oportunidades lucrativas no YouTube para {ano}.",
            "FUNÇÃO 1 - IDENTIFICAÇÃO DE LUCRATIVIDADE:",
            "- Use lógica de ferramentas como Social Blade, Google Trends, VidiQ",
            "- Encontre canais com alto RPM (Revenue Per Mille) e baixa concorrência",
            f"- Considere tendências atuais de {ano}",
            "- Prove que a oportunidade é real e escalável com dados",
            "FUNÇÃO 2 - MÉTODO 80/20:",
            "- Analise vídeos de sucesso dos concorrentes",
            "- Identifique os 20% de elementos que geram 80% dos resultados",
            "- Ganchos (hooks), estrutura de roteiro, ritmo, formato",
            "- Modele o sucesso, não copie",
            f"PARA CADA NICHO: Apresente 3 ideias de canais válidas considerando o contexto de {ano}",
            "FORMATO: Use métricas específicas (RPM estimado, concorrência, potencial)",
            "RETORNE APENAS O CONTEÚDO DA RESPOSTA, SEM METADADOS TÉCNICOS.",
            "USE MARKDOWN PARA FORMATAÇÃO, COM CABEÇALHOS, LISTAS E ÊNFASE."
            # --- LINHA NOVA IMPORTANTE ---
            "IMPORTANTE: Sempre use a tool 'ferramenta_youtube_search' para validar se o nicho tem views REAIS recentes.", 
            # -----------------------------
            
            "FUNÇÃO 1 - IDENTIFICAÇÃO DE LUCRATIVIDADE:",
            "- Use lógica de ferramentas como Social Blade, Google Trends, VidiQ",
            "- Encontre canais com alto RPM (Revenue Per Mille) e baixa concorrência",
            f"- Considere tendências atuais de {ano}",
            "- Prove que a oportunidade é real e escalável com dados",
            "FUNÇÃO 2 - MÉTODO 80/20:",
            "- Analise vídeos de sucesso dos concorrentes",
            "- Identifique os 20% de elementos que geram 80% dos resultados",
            "- Ganchos (hooks), estrutura de roteiro, ritmo, formato",
            "- Modele o sucesso, não copie",
            f"PARA CADA NICHO: Apresente 3 ideias de canais válidas considerando o contexto de {ano}",
            "FORMATO: Use métricas específicas (RPM estimado, concorrência, potencial)",
            "RETORNE APENAS O CONTEÚDO DA RESPOSTA, SEM METADADOS TÉCNICOS.",
            "USE MARKDOWN PARA FORMATAÇÃO, COM CABEÇALHOS, LISTAS E ÊNFASE."
        ],
        # AQUI ESTÁ CERTO: Passamos a instância do DuckDuckGo e a função do YouTube
        tools=[DuckDuckGo(), ferramenta_youtube_search], 
        show_tool_calls=True, # Dica: Deixe True no início para ver se ele está usando a ferramenta
        markdown=True
    )
def criar_agente_booster():
    ano = ano_atual()
    return Agent(
        model=DeepSeekChat(api_key=DEEPSEEK_API_KEY, temperature=0.6),
        name="Booster_YouTube",
        role="Especialista em SEO, Crescimento e Automação",
        instructions=[
            f"VOCÊ É O BOOSTER: Especialista em otimizar e escalar canais YouTube para {ano}.",
            
            "FUNÇÃO 1 - SEO E CTR:",
            "- Domine palavras-chave de alto volume e baixa competição",
            "- Crie títulos 'clicáveis' (clickbait ético)",
            
            "FUNÇÃO 2 - GERAÇÃO DE THUMBNAIL (Prompt Mágico):",
            "- Escolha a MELHOR ideia visual.",
            "- GERE O PROMPT PRONTO usando EXATAMENTE este template:",
            """
            TEMPLATE OBRIGATÓRIO:
            ```text
            Crie uma thumbnail de YouTube realista e cinematográfica, alta resolução 8k. Estilo: Vibrante, alto contraste e saturação levemente aumentada (estilo MrBeast/MagnatesMedia). A imagem deve ter um ponto focal claro e expressivo. Iluminação dramática. Sem texto (ou texto mínimo se especificado).
            
            A CENA É: [DESCREVA AQUI A CENA VISUAL DETALHADA]
            ```
            """,
            
            "FUNÇÃO 3 - STACK DE FERRAMENTAS E PESQUISA (CRUCIAL):",
            f"- Liste as MELHORES ferramentas de IA de {ano} para cada etapa:",
            "  * Pesquisa de Ideias: (Cite ferramentas como Google Trends, AnswerThePublic, Perplexity, etc)",
            "  * Roteiro e Voz: (Cite ferramentas específicas)",
            "  * Edição e Visual: (Cite ferramentas de automação)",
            
            "FUNÇÃO 4 - ESCALA GLOBAL:",
            "- Planeje tradução/dublagem AI (Rask.ai, HeyGen)",
            "- Estruture 'Sistema de Geração de Ideias' para nunca faltar conteúdo",
            
            f"PARA UMA IDEIA SELECIONADA: Crie plano completo de otimização para {ano}",
            "FORMATO: Prático, detalhado e focado em ferramentas reais.",
            "RETORNE APENAS O CONTEÚDO DA RESPOSTA, SEM METADADOS TÉCNICOS.",
            "USE MARKDOWN PARA FORMATAÇÃO CLARA."
        ],
        markdown=True
    )

# --- AQUI É O LUGAR CORRETO DA FUNÇÃO DE IMAGEM ---
import requests # <--- Certifique-se que isso está importado (geralmente já vem no python)

def gerar_thumbnail_google(prompt_texto, api_key=None):
    """
    Gera thumbnail usando Pollinations.ai (Modelo FLUX)
    Funciona instantaneamente sem necessidade de API Key do Google válida para imagens.
    """
    try:
        # Melhorando o prompt para garantir alta qualidade
        prompt_melhorado = f"{prompt_texto}, youtube thumbnail, 8k, highly detailed, dramatic lighting"
        
        # Codifica o texto para URL
        prompt_encoded = urllib.parse.quote(prompt_melhorado)
        
        # URL Mágica (Gera em 1280x720 HD)
        url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1280&height=720&model=flux&nologo=true"
        
        # Faz o download da imagem gerada
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            image_data = response.content
            return Image.open(io.BytesIO(image_data))
        else:
            return f"Erro na geração: Status {response.status_code}"
            
    except Exception as e:
        return f"Erro técnico ao gerar imagem: {str(e)}"

def criar_agente_copywriter():
    ano = ano_atual()
    return Agent(
        model=DeepSeekChat(api_key=DEEPSEEK_API_KEY, temperature=0.7),
        name="Copywriter_YouTube",
        role="Roteirista Sênior de YouTube",
        instructions=[
            f"VOCÊ É O COPYWRITER: Sua missão é transformar a decisão do CEO em um ROTEIRO DE VÍDEO completo.",
            "ESTRUTURA OBRIGATÓRIA DO ROTEIRO:",
            "1. GANCHO (0-15s): Uma frase chocante ou pergunta que prenda a atenção imediatamente.",
            "2. VINHETA/INTRO (15-30s): Apresentação rápida do canal e do tema.",
            "3. CONTEÚDO (Corpo): Explique o tópico usando linguagem simples (nível 5ª série), mas com autoridade.",
            "4. RETENÇÃO: Insira 'quebras de padrão' sugeridas (ex: mudar câmera, mostrar gráfico).",
            "5. CTA (Call to Action): O momento exato de pedir o like/inscrição.",
            f"CONTEXTO: Estamos em {ano}, o público tem atenção curta. Seja dinâmico.",
            "FORMATO: Use Markdown. Separe as falas do narrador das instruções visuais (ex: [MOSTRAR GRÁFICO]).",
            "RETORNE APENAS O ROTEIRO, SEM METADADOS."
        ],
        markdown=True
    )
# 6. FUNÇÕES DE LIMPEZA E FORMATAÇÃO
def limpar_resposta_agente(resposta):
    """Remove metadados técnicos e extrai apenas o conteúdo formatado"""
    if not resposta:
        return ""
    
    resposta_str = str(resposta)
    
    if hasattr(resposta, 'content'):
        conteudo = resposta.content
        if conteudo:
            conteudo = str(conteudo)
            if conteudo.startswith("content='"):
                conteudo = conteudo[9:]
                if conteudo.endswith("'"):
                    conteudo = conteudo[:-1]
            return conteudo
        return ""
    
    if resposta_str.startswith("content='"):
        resposta_str = resposta_str[9:]
        if resposta_str.endswith("'"):
            resposta_str = resposta_str[:-1]
    
    padroes_tecnicos = [
        r"name=None.*?created_at=\d+",
        r"tool_call_id=None.*?stop_after_tool_call=False",
        r"metrics=\{.*?\}",
        r"references=None",
        r"Message\(.*?\)",
        r"tool_calls=\[.*?\]",
        r"images=None.*?videos=None",
        r"audio=None.*?response_audio=None",
        r"extra_data=None",
        r"run_id='[^']*'",
        r"agent_id='[^']*'",
        r"session_id='[^']*'",
        r"workflow_id=None",
        r"model='[^']*'",
        r"defaultdict\(.*?\)"
    ]
    
    for padrao in padroes_tecnicos:
        resposta_str = re.sub(padrao, '', resposta_str, flags=re.DOTALL)
    
    resposta_str = re.sub(r'\n\s*\n', '\n\n', resposta_str)
    resposta_str = re.sub(r'\s{2,}', ' ', resposta_str)
    
    linhas = resposta_str.split('\n')
    linhas_limpas = []
    for linha in linhas:
        linha = linha.strip()
        if linha and not any(termo in linha for termo in [
            'name=', 'tool_', 'metrics=', 'created_at=', 
            'model=', 'run_id=', 'agent_id=', 'session_id=',
            'defaultdict', 'content_type=', 'event='
        ]):
            linhas_limpas.append(linha)
    
    return '\n'.join(linhas_limpas)

def extrair_texto_principal(resposta):
    """Extrai apenas o texto principal da resposta, removendo metadados"""
    if not resposta:
        return ""
    
    resposta_str = str(resposta)
    
    if "Message(" in resposta_str or "content='" in resposta_str:
        match = re.search(r"content='(.*?)'(?=, name=|$)", resposta_str, re.DOTALL)
        if match:
            return match.group(1)
        
        match = re.search(r"content='(.*?)(?=, \w+=|$)", resposta_str, re.DOTALL)
        if match:
            return match.group(1)
    
    return resposta_str


# 7. SISTEMA DE ORQUESTRAÇÃO
class SistemaYouTubeAutomation:
    def __init__(self):
        self.ceo = criar_gerente_executivo()
        self.especialistas = {
            "hunter": criar_agente_hunter(),
            "booster": criar_agente_booster(),
            "copywriter": criar_agente_copywriter()
        }
    
    def executar_workflow(self, nicho, db, projeto_id):
        """Executa o fluxo completo de análise"""
        
        ano = ano_atual()
        resultados = {
            "nicho": nicho,
            "ano_analise": ano,
            "hunter_analysis": None,
            "booster_optimization": None,
            "ceo_verdict": None
        }
        
        # PASSO 1: Análise do Hunter
        with st.spinner("🔍 Hunter analisando oportunidades..."):
            hunter_prompt = f"""
            NICHO: {nicho}
            ANO: {ano}
            
            Como Agente Hunter, forneça uma análise estruturada em MARKDOWN com:
            
            ## 🎯 CONTEXTO DO NICHO
            Breve introdução sobre o nicho em {ano}
            
            ## 📊 3 IDEIAS DE CANAIS
            
            ### IDEIA 1: [Nome do Canal]
            - **RPM Estimado:** [valor]
            - **Concorrência:** [Baixa/Média/Alta]
            - **Potencial Mensal:** [valor]
            - **Elementos 80/20:**
              1. [Elemento 1]
              2. [Elemento 2]
            - **Justificativa:** [explicação]
            
            ### IDEIA 2: [Nome do Canal]
            [mesma estrutura]
            
            ### IDEIA 3: [Nome do Canal]
            [mesma estrutura]
            
            ## 📈 CONCLUSÃO
            Resumo das oportunidades mais promissoras.
            
            Use formatação markdown clara e evite metadados técnicos."""
            
            hunter_response = self.especialistas["hunter"].run(hunter_prompt)
            resultados["hunter_analysis"] = extrair_texto_principal(hunter_response)
        
        # Extrair a melhor ideia do Hunter para o Booster
        melhor_ideia = self._extrair_melhor_ideia(resultados["hunter_analysis"])
        
        # PASSO 2: Otimização do Booster
        with st.spinner("🚀 Booster otimizando e escalando..."):
            booster_prompt = f"""
            IDEIA DE CANAL SELECIONADA: {melhor_ideia}
            NICHO: {nicho}
            ANO: {ano}
            
            Como Agente Booster, forneça um plano de otimização em MARKDOWN com:
            
            ## 🎯 SEO E OTIMIZAÇÃO DE CTR
            
            ### 5 TÍTULOS VIRAIS
            1. [Título 1]
            2. [Título 2]
            
            ### IDEIAS DE THUMBNAIL
            • [Descrição thumbnail 1]
            • [Descrição thumbnail 2]
            
            ### PALAVRAS-CHAVE ESTRATÉGICAS
            - [Keyword 1]
            - [Keyword 2]
            
            ## 🤖 ESTRATÉGIA DE AUTOMAÇÃO
            
            ### FERRAMENTAS RECOMENDADAS ({ano})
            • Roteiro: [ferramenta]
            • Voz: [ferramenta]
            • Edição: [ferramenta]
            
            ### PLANO DE EXPANSÃO
            • Tradução para [idiomas]
            • Subnichos relacionados
            
            Use formatação markdown limpa e prática."""
            
            booster_response = self.especialistas["booster"].run(booster_prompt)
            resultados["booster_optimization"] = extrair_texto_principal(booster_response)
        
        # PASSO 3: Veredito do CEO
        with st.spinner("🎯 CEO tomando decisão final..."):
            ceo_prompt = f"""
            RELATÓRIO EXECUTIVO - DECISÃO CEO {ano}
            
            **NICHO:** {nicho}
            
            **ANÁLISE DO HUNTER:**
            {resultados['hunter_analysis'][:1000]}...
            
            **OTIMIZAÇÃO DO BOOSTER:**
            {resultados['booster_optimization'][:1000]}...
            
            Como CEO, forneça uma decisão final em MARKDOWN estruturada:
            
            ## 📊 RESUMO EXECUTIVO
            - Oportunidade principal
            - ROI Estimado
            - Timeline
            
            ## ⚠️ ANÁLISE DE RISCOS
            - Principais desafios
            - Mitigações
            
            ## 🚀 PRÓXIMO PASSO IMEDIATO
            - Ação concreta para hoje
            - Investimento inicial
            - Primeira semana
            
            ## ✅ DECISÃO FINAL
            - Aprovação (SIM/NÃO)
            - Justificativa
            
            Seja direto, profissional e focado em ação."""
            
            ceo_response = self.ceo.run(ceo_prompt)
            resultados["ceo_verdict"] = extrair_texto_principal(ceo_response)
        # --- NOVO BLOCO: COPYWRITER (Adicione daqui para baixo) ---
        with st.spinner("✍️ Copywriter escrevendo o roteiro viral..."):
            copy_prompt = f"""
            Gere um roteiro completo baseado nesta Decisão do CEO:
            {resultados['ceo_verdict']}
            
            E usando estas otimizações do Booster (Títulos/Temas):
            {resultados['booster_optimization']}
            
            O roteiro deve ter entre 3 a 5 minutos de leitura estimada.
            """
            
            copy_response = self.especialistas["copywriter"].run(copy_prompt)
            resultados["copywriter_script"] = extrair_texto_principal(copy_response)
        # ----------------------------------------------------------

        return resultados
        
    
    def _extrair_melhor_ideia(self, hunter_analysis):
        """Extrai a primeira/melhor ideia da análise do Hunter"""
        if not hunter_analysis:
            return "Canal Principal do Nicho"
        
        lines = str(hunter_analysis).split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(marker in line_lower for marker in ['ideia 1', 'primeira ideia', '1.', '### ideia 1']):
                descricao = []
                for j in range(i + 1, min(i + 10, len(lines))):
                    next_line = lines[j].strip()
                    if next_line and not any(next_marker in next_line.lower() for next_marker in ['ideia 2', '2.', '### ideia 2']):
                        descricao.append(next_line)
                    else:
                        break
                if descricao:
                    return f"{line.strip()} - {' '.join(descricao[:3])}"
                return line.strip()
        
        for line in lines:
            if line.strip() and len(line.strip()) > 10:
                return line.strip()[:100]
        
        return "Canal Principal do Nicho"

# 8. FUNÇÕES AUXILIARES
def _extrair_primeira_ideia(texto):
    """Função auxiliar para extrair primeira ideia"""
    if not texto:
        return "Ideia Principal"
    
    linhas = str(texto).split('\n')
    for linha in linhas:
        linha_lower = linha.lower()
        if any(marker in linha_lower for marker in ['ideia 1', 'primeira', '1.', '###']):
            return linha[:100].strip()
    return "Ideia Principal"

def _extrair_acao_imediata(texto):
    """Função auxiliar para extrair ação imediata"""
    if not texto:
        return "Começar produção do primeiro vídeo"
    
    linhas = str(texto).split('\n')
    for i, linha in enumerate(linhas):
        linha_lower = linha.lower()
        if 'próximo passo' in linha_lower or 'imediat' in linha_lower or 'ação' in linha_lower:
            for j in range(i, min(i + 5, len(linhas))):
                acao_linha = linhas[j].strip()
                if acao_linha and not acao_linha.startswith('#'):
                    return acao_linha
            return linha.strip()
    return "Começar produção do primeiro vídeo"

def gerar_prompt_sugestao_nicho():
    """Gera prompt dinâmico para sugestão de nicho"""
    ano = ano_atual()
    return f"""Sugira 3 nichos com alto potencial para YouTube Automation em {ano}. 
    Considere:
    1. Tendências atuais do YouTube em {ano}
    2. RPM (Revenue Per Mille) estimado
    3. Nível de concorrência atual
    
    **Retorne apenas o melhor nicho** com formato:
    
    🎯 **MELHOR NICHO PARA {ano}:**
    [Nome do Nicho]
    
    📊 **MOTIVOS:**
    • [Razão 1]
    • [Razão 2]
    
    Evite metadados técnicos na resposta."""

# 9. FUNÇÃO PRINCIPAL STREAMLIT
# 9. FUNÇÃO PRINCIPAL STREAMLIT
def main():
    st.set_page_config(
        page_title="YouTube Automation CEO",
        page_icon="🎬",
        layout="wide"
    )
    
    # CSS personalizado
    st.markdown("""
    <style>
    /* Contêineres dos agentes */
    .hunter-container {
        background: linear-gradient(135deg, #0f766e 0%, #115e59 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 1rem;
        border-left: 6px solid #10b981;
    }
    
    .booster-container {
        background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 1rem;
        border-left: 6px solid #8b5cf6;
    }
    
    .ceo-container {
        background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 1rem;
        border-left: 6px solid #f59e0b;
    }
    
    /* Estilos para markdown dentro dos contêineres */
    .hunter-container h1, .hunter-container h2, .hunter-container h3 {
        color: #a7f3d0 !important;
    }
    
    .booster-container h1, .booster-container h2, .booster-container h3 {
        color: #ddd6fe !important;
    }
    
    .ceo-container h1, .ceo-container h2, .ceo-container h3 {
        color: #fef3c7 !important;
    }
    
    /* Cards de métricas */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .ano-atual {
        color: #f59e0b;
        font-weight: bold;
        background: rgba(245, 158, 11, 0.1);
        padding: 2px 8px;
        border-radius: 4px;
    }
    
    /* Botões de exportação */
    .export-buttons {
        display: flex;
        gap: 10px;
        margin: 15px 0;
        flex-wrap: wrap;
    }
    
    .export-btn {
        background: #3b82f6;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 6px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 14px;
        transition: background 0.3s;
    }
    
    .export-btn:hover {
        background: #2563eb;
    }
    
    /* Melhorar a legibilidade geral */
    .stMarkdown {
        line-height: 1.6;
    }
    
    .stMarkdown p {
        margin-bottom: 0.8rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # --- 1. CARREGAR CHAVES ---
    keys = carregar_chaves_seguras()
    if not keys and 'temp_keys' in st.session_state:
        keys = st.session_state['temp_keys']

    # --- 2. SE NÃO TIVER CHAVES, PEDE SETUP E PARA ---
    if not keys:
        tela_configuracao_inicial()
        st.stop()

    # --- 3. CONECTAR AO SUPABASE (CRIA A VARIÁVEL 'supabase') ---
    try:
        supabase = create_client(keys["SUPABASE_URL"], keys["SUPABASE_KEY"])
    except Exception as e:
        st.error(f"Erro ao conectar no banco de dados: {e}")
        st.stop()

    # --- 4. VERIFICA LOGIN ---
    if 'user' not in st.session_state:
        tela_login(supabase)
        st.stop()

    # --- 5. SIDEBAR COM LOGOUT ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state['user'].email}**")
        if st.button("Sair (Logout)"):
            supabase.auth.sign_out()
            del st.session_state['user']
            st.rerun()
        st.divider()

    # --- 6. DEFINE VARIÁVEIS GLOBAIS PARA OS AGENTES ---
    global DEEPSEEK_API_KEY, SUPABASE_URL, SUPABASE_KEY, YOUTUBE_API_KEY
    DEEPSEEK_API_KEY = keys["DEEPSEEK_API_KEY"]
    SUPABASE_URL = keys["SUPABASE_URL"]
    SUPABASE_KEY = keys["SUPABASE_KEY"]
    YOUTUBE_API_KEY = keys["YOUTUBE_API_KEY"]
    
    # --- 7. INICIALIZAR BANCO DE DADOS (Agora funciona pois 'supabase' existe) ---
    if "db" not in st.session_state:
        st.session_state.db = YouTubeAutomationDatabase(supabase)
    
    # --- 8. INICIALIZAR SISTEMA DE IA ---
    if "sistema" not in st.session_state:
        st.session_state.sistema = SistemaYouTubeAutomation()
    # HEADER
    ano = ano_atual()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🎬 YouTube Automation CEO")
        st.markdown(f"### Sistema Completo de Análise • <span class='ano-atual'>{ano}</span>", 
                   unsafe_allow_html=True)
    
    # SIDEBAR
    with st.sidebar:
        st.header(f"📊 CONTROLE DE PROJETOS")
        
        # Inicializar variáveis de sessão
        if "projeto_atual" not in st.session_state:
            st.session_state.projeto_atual = None
            st.session_state.workflow_resultados = None
            st.session_state.historico_projeto = None
        
        if "nicho_sugerido" not in st.session_state:
            st.session_state.nicho_sugerido = None
        
        # Mostrar projeto atual
        if st.session_state.projeto_atual:
            if isinstance(st.session_state.projeto_atual, dict):
                codigo = st.session_state.projeto_atual.get('codigo', 'N/A')
                nicho = st.session_state.projeto_atual.get('nicho', 'N/A')
            else:
                codigo = st.session_state.projeto_atual.get('codigo_projeto', 'N/A')
                nicho = st.session_state.projeto_atual.get('nicho', 'N/A')
            
            st.success(f"**Projeto Ativo:**\n{codigo}")
            st.caption(f"**Nicho:** {nicho}")
        else:
            st.info("⚠️ Nenhum projeto ativo")
        
        st.divider()
        
        # Novo projeto
        st.subheader("🚀 Novo Projeto")
        
        nicho_input = st.text_input("Digite um nicho:", placeholder="Ex: Finanças Pessoais, DIY, ASMR")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🎯 Analisar Nicho", use_container_width=True):
                if nicho_input.strip():
                    novo_projeto = st.session_state.db.criar_projeto(
                        nicho=nicho_input.strip(),
                        descricao=f"Análise de nicho: {nicho_input} - {ano}"
                    )
                    st.session_state.projeto_atual = novo_projeto
                    st.session_state.workflow_resultados = None
                    st.session_state.historico_projeto = None
                    st.rerun()
                else:
                    st.warning("Digite um nicho primeiro!")
        
        with col_btn2:
            if st.button("🔍 Sugerir Nicho", use_container_width=True):
                with st.spinner(f"Buscando oportunidades para {ano}..."):
                    try:
                        prompt = gerar_prompt_sugestao_nicho()
                        nicho_sugerido = st.session_state.sistema.ceo.run(prompt)
                        nicho_sugerido_limpo = extrair_texto_principal(nicho_sugerido)
                        st.session_state.nicho_sugerido = nicho_sugerido_limpo
                    except Exception as e:
                        st.error(f"Erro ao sugerir nicho: {e}")
                        st.session_state.nicho_sugerido = f"Finanças Pessoais Digitais (alto RPM {ano})"
        
        if st.session_state.nicho_sugerido:
            st.markdown("**🎁 Nicho Sugerido:**")
            st.write(st.session_state.nicho_sugerido)
            if st.button("✅ Usar Este Nicho"):
                nicho_texto = st.session_state.nicho_sugerido.strip()
                if nicho_texto:
                    linhas = nicho_texto.split('\n')
                    nome_nicho = linhas[0].replace('🎯', '').replace('**', '').strip()
                    
                    novo_projeto = st.session_state.db.criar_projeto(
                        nicho=nome_nicho[:100],
                        descricao=f"Nicho sugerido pelo CEO - {ano}"
                    )
                    st.session_state.projeto_atual = novo_projeto
                    st.session_state.workflow_resultados = None
                    st.session_state.historico_projeto = None
                    st.session_state.nicho_sugerido = None
                    st.rerun()
        
        st.divider()
        
        # Projetos anteriores
        st.subheader("📚 Projetos Anteriores")
        projetos_df = st.session_state.db.listar_projetos()
        
        if not projetos_df.empty:
            for _, projeto in projetos_df.head(5).iterrows():
                projeto_dict = projeto.to_dict()
                btn_label = f"📁 {projeto_dict.get('codigo_projeto', 'Projeto')}"
                if st.button(btn_label, key=f"proj_{projeto_dict['id']}"):
                    st.session_state.projeto_atual = projeto_dict
                    try:
                        historico = st.session_state.db.obter_historico_projeto(projeto_dict['id'])
                        st.session_state.historico_projeto = historico
                    except Exception as e:
                        st.error(f"Erro ao carregar histórico: {e}")
                    st.rerun()
        else:
            st.caption("📭 Nenhum projeto salvo")
    
    # CONTEÚDO PRINCIPAL
    if not st.session_state.projeto_atual:
        # Tela inicial
        st.markdown("## 🎯 Bem-vindo, CEO!")
        
        col_intro1, col_intro2 = st.columns(2)
        
        with col_intro1:
            st.markdown(f"""
            ### Sua Equipe de Elite ({ano}):
            
            **🎩 CEO (Você)** 
            Decisão estratégica final
            
            **🔍 HUNTER** 
            Encontra oportunidades lucrativas
            • Identifica nichos com alto RPM
            • Aplica método 80/20
            • Valida concorrência atual
            
            **🚀 BOOSTER** 
            Otimiza e escala
            • SEO e CTR máximo
            • Automação com IA
            • Globalização do conteúdo
            
            ### 📈 Métricas Alvo:
            • RPM: $3-$15+
            • Concorrência: Baixa/Média
            • ROI: 200%+ em 90 dias
            """)
        
        with col_intro2:
            st.markdown(f"""
            ### 🚀 Como Começar:
            
            1. **Digite um nicho** na sidebar
               - Ou peça uma sugestão atualizada
            
            2. **Execute a análise completa**
               - Hunter encontra 3 oportunidades
               - Booster otimiza a melhor
               - Você decide o próximo passo
            
            3. **Comece a faturar**
               - Plano de ação imediato
               - Ferramentas recomendadas
               - Timeline realista
            
            ### 💡 Nichos Quentes {ano}:
            • Finanças Pessoais Digitais
            • Saúde Mental & Bem-estar
            • DIY & Life Hacks com IA
            • Educação Alternativa Online
            • Conteúdo ASMR/Relaxamento
            """)
        
        st.divider()
        st.info(f"💡 **Dica:** Use a barra lateral para começar seu primeiro projeto em {ano}!")
    
    else:
        # Projeto ativo
        if isinstance(st.session_state.projeto_atual, dict):
            projeto = st.session_state.projeto_atual
            codigo = projeto.get('codigo', projeto.get('codigo_projeto', 'N/A'))
            nicho = projeto.get('nicho', 'N/A')
            projeto_id = projeto.get('id')
        else:
            projeto = st.session_state.projeto_atual
            codigo = projeto.get('codigo_projeto', 'N/A')
            nicho = projeto.get('nicho', 'N/A')
            projeto_id = projeto.get('id')
        
        # Header do projeto
        st.markdown(f"""
        ## 🎬 Projeto: **{codigo}**
        ### Nicho: **{nicho}**
        ### 🗓️ Análise: **{ano}**
        """)
        
        # Botão para executar workflow
        if st.button(f"▶️ EXECUTAR ANÁLISE COMPLETA", type="primary", use_container_width=True):
            with st.spinner(f"Orquestrando equipe de elite para {ano}..."):
                try:
                    resultados = st.session_state.sistema.executar_workflow(
                        nicho=nicho,
                        db=st.session_state.db,
                        projeto_id=projeto_id
                    )
                    
                    st.session_state.workflow_resultados = resultados
                    st.success(f"✅ Análise completa executada!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Erro ao executar análise: {str(e)}")
        
        # Mostrar resultados se existirem
        if st.session_state.get('workflow_resultados'):
            resultados = st.session_state.workflow_resultados
            
            # Criar abas para cada etapa
            tab1, tab2, tab3, tab4 = st.tabs([f"🔍 HUNTER", f"🚀 BOOSTER", f"🎯 CEO", f"✍️ ROTEIRO"])
            #tab1, tab2, tab3 = st.tabs([f"🔍 HUNTER", f"🚀 BOOSTER", f"🎯 CEO"])
            
            with tab1:
                st.markdown(f"### 🔍 Análise do Hunter - {ano}")
                hunter_content = resultados.get("hunter_analysis", "")
                if hunter_content:
                    # Contêiner estilizado
                    st.markdown(f"""
                    <div class='hunter-container'>
                    {hunter_content}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # BOTÕES DE EXPORTAÇÃO PARA HUNTER
                    st.markdown("---")
                    st.markdown("### 📤 Exportar Relatório Hunter")
                    col_h1, col_h2 = st.columns(2)
                    
                    with col_h1:
                        if st.button("📄 Exportar para HTML", key="export_hunter_html"):
                            html_content = exportar_relatorio(
                                hunter_content, 
                                "hunter", 
                                projeto,
                                formato="html"
                            )
                    
                    with col_h2:
                        if st.button("📝 Exportar para TXT", key="export_hunter_txt"):
                            exportar_relatorio(
                                hunter_content, 
                                "hunter", 
                                projeto,
                                formato="txt"
                            )
                else:
                    st.warning("Nenhuma análise disponível")
            
            with tab2:
                st.markdown(f"### 🚀 Otimização do Booster - {ano}")
                booster_content = resultados.get("booster_optimization", "")
                if booster_content:
                    st.markdown(f"""
                    <div class='booster-container'>
                    {booster_content}
                    </div>
                    """, unsafe_allow_html=True)

                    # --- NOVO: GERADOR DE THUMBNAIL GOOGLE ---
                    st.markdown("---")
                    st.subheader("🎨 Estúdio de Thumbnails (Flux AI)")
                    
                    # Tenta extrair o prompt automaticamente do texto do Booster
                    prompt_sugerido = ""
                    if "A CENA É:" in booster_content:
                        partes = booster_content.split("A CENA É:")
                        if len(partes) > 1:
                            # Pega o texto depois de "A CENA É:" até o fim da linha ou bloco
                            prompt_sugerido = partes[1].split("```")[0].strip()
                            # Adiciona o estilo automaticamente
                            prompt_completo = f"Thumbnail YouTube, 8k resolution, cinematic lighting, vibrant high contrast. Scene: {prompt_sugerido}"
                    else:
                        prompt_completo = "YouTube thumbnail, high contrast, money and success theme, 8k."

                    # Campo para você editar o prompt se quiser
                    prompt_final = st.text_area("Prompt da Thumbnail:", value=prompt_completo, height=100)
                    
                    # O Botão Mágico
                    if st.button("✨ Gerar Thumbnail com IA", type="primary"):
                        # Precisamos de uma chave API do Google (AI Studio)
                        # Tenta usar a mesma do YouTube ou pede uma específica
                        api_key_google = st.session_state.get('temp_keys', {}).get('DEEPSEEK_API_KEY') 
                        # OBS: O ideal é ter uma chave GOOGLE_API_KEY separada, mas às vezes a do YouTube funciona se tiver permissão.
                        # Se não tiver, vamos pedir aqui:
                        
                        chave_google = st.text_input("Cole sua Google API Key (Gemini/AI Studio) se for diferente da configurada:", type="password")
                        if not chave_google:
                             # Tenta usar uma variável de ambiente se existir
                             chave_google = os.getenv("GOOGLE_API_KEY")

                        if chave_google:
                            with st.spinner("🎨 O Google está pintando sua thumbnail..."):
                                imagem_gerada = gerar_thumbnail_google(prompt_final, chave_google)
                                
                                if isinstance(imagem_gerada, str) and "Erro" in imagem_gerada:
                                    st.error(imagem_gerada)
                                else:
                                    # Mostra a imagem!
                                    st.image(imagem_gerada, caption="Thumbnail Gerada pelo Google Imagen 3", use_column_width=True)
                                    
                                    # Botão de Download da Imagem
                                    # (Lógica simples para baixar)
                                    # st.download_button... (requires converting PIL to bytes)
                        else:
                            st.warning("Preciso de uma Google API Key (AI Studio) para gerar imagens.")
                    # -----------------------------------------
                    
                    # BOTÕES DE EXPORTAÇÃO PARA BOOSTER
                    st.markdown("---")
                    st.markdown("### 📤 Exportar Relatório Booster")
                    col_b1, col_b2 = st.columns(2)
                    
                    with col_b1:
                        if st.button("📄 Exportar para HTML", key="export_booster_html"):
                            exportar_relatorio(
                                booster_content, 
                                "booster", 
                                projeto,
                                formato="html"
                            )
                    
                    with col_b2:
                        if st.button("📝 Exportar para TXT", key="export_booster_txt"):
                            exportar_relatorio(
                                booster_content, 
                                "booster", 
                                projeto,
                                formato="txt"
                            )
                else:
                    st.warning("Nenhuma otimização disponível")
            
            with tab3:
                st.markdown(f"### 🎯 Veredito do CEO - {ano}")
                ceo_content = resultados.get("ceo_verdict", "")
                if ceo_content:
                    st.markdown(f"""
                    <div class='ceo-container'>
                    {ceo_content}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # BOTÕES DE EXPORTAÇÃO PARA CEO
                    st.markdown("---")
                    st.markdown("### 📤 Exportar Relatório CEO")
                    col_c1, col_c2 = st.columns(2)
                    
                    with col_c1:
                        if st.button("📄 Exportar para HTML", key="export_ceo_html"):
                            exportar_relatorio(
                                ceo_content, 
                                "ceo", 
                                projeto,
                                formato="html"
                            )
                    
                    with col_c2:
                        if st.button("📝 Exportar para TXT", key="export_ceo_txt"):
                            exportar_relatorio(
                                ceo_content, 
                                "ceo", 
                                projeto,
                                formato="txt"
                            )
                else:
                    st.warning("Nenhum veredito disponível")
            with tab4:
                st.markdown(f"### ✍️ Roteiro de Vídeo - {ano}")
                script_content = resultados.get("copywriter_script", "")
                
                if script_content:
                    st.markdown(f"""
                    <div class='copy-container'>
                    {script_content}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # BOTÕES DE EXPORTAÇÃO DO ROTEIRO
                    st.markdown("---")
                    col_copy1, col_copy2 = st.columns(2)
                    
                    with col_copy1:
                        if st.button("📄 Exportar Roteiro (PDF/HTML)", key="export_copy_html"):
                            exportar_relatorio(script_content, "roteiro", projeto, formato="html")
                            
                    with col_copy2:
                        if st.button("📝 Copiar Texto Puro", key="export_copy_txt"):
                             exportar_relatorio(script_content, "roteiro", projeto, formato="txt")
                else:
                    st.warning("Roteiro ainda não gerado.")     
            
            # Plano de ação resumido
           # ---------------------------------------------------------
            # PLANO DE AÇÃO DINÂMICO (VERSÃO BLINDADA COM REGEX)
            # ---------------------------------------------------------
            st.divider()
            st.markdown("## 📋 Plano de Ação do CEO (Resumo)")
            
            # 1. LIMPEZA PROFUNDA DO TEXTO
            raw_text = str(resultados.get("ceo_verdict", ""))
            
            # Remove metadados técnicos comuns do Phidata/Agno
            texto_limpo = re.sub(r"Message\(.*?\)", "", raw_text, flags=re.DOTALL)
            texto_limpo = re.sub(r"content='(.*?)'", r"\1", texto_limpo, flags=re.DOTALL)
            texto_limpo = re.sub(r"metrics=\{.*?\}", "", texto_limpo, flags=re.DOTALL)
            texto_limpo = texto_limpo.replace("\\n", "\n").replace("content_type='str'", "")
            
            # 2. EXTRAÇÃO INTELIGENTE (Busca o que está ENTRE os títulos)
            acao_hoje = "Ver detalhes no relatório acima."
            investimento = "Variável."
            plano_semana = "Seguir cronograma."
            
            try:
                # Busca texto entre "Ação...Hoje" e "Investimento"
                match_acao = re.search(r"(?:Ação concreta para hoje|Ação Imediata|Próximo Passo)[:\s\*\-]*(.*?)(?:Investimento|Custos|##)", texto_limpo, re.IGNORECASE | re.DOTALL)
                if match_acao:
                    acao_hoje = match_acao.group(1).strip()

                # Busca texto entre "Investimento" e "Primeira Semana"
                match_invest = re.search(r"(?:Investimento inicial|Investimento)[:\s\*\-]*(.*?)(?:Primeira semana|Semana 1|##)", texto_limpo, re.IGNORECASE | re.DOTALL)
                if match_invest:
                    investimento = match_invest.group(1).strip()

                # Busca texto entre "Primeira Semana" e o próximo título grande "##"
                match_semana = re.search(r"(?:Primeira semana|Semana 1)[:\s\*\-]*(.*?)(?:##|✅)", texto_limpo, re.IGNORECASE | re.DOTALL)
                if match_semana:
                    plano_semana = match_semana.group(1).strip()
                    
            except Exception as e:
                print(f"Erro no Regex: {e}")

            # 3. EXIBIÇÃO DOS CARDS
            col_passo1, col_passo2, col_passo3 = st.columns(3)
            
            with col_passo1:
                # Limita o tamanho para não quebrar o layout se vier texto demais
                st.info(f"**🔥 Ação Imediata**\n\n{acao_hoje[:250]}")
            
            with col_passo2:
                st.warning(f"**💰 Investimento**\n\n{investimento[:200]}")
            
            with col_passo3:
                st.success(f"**🗓️ Primeira Semana**\n\n{plano_semana[:300]}")
            # ---------------------------------------------------------
            
            # Exportação completa do projeto
            st.markdown("---")
            st.markdown("### 💾 Exportação Completa do Projeto")
            
            col_full1, col_full2 = st.columns(2)
            
            with col_full1:
                if st.button("📦 Exportar Projeto Completo (HTML)", key="export_full_html"):
                    # Combinar todos os relatórios
                    full_content = f"""
                    # RELATÓRIO COMPLETO DO PROJETO
                    
                    ## 🔍 ANÁLISE DO HUNTER
                    {hunter_content}
                    
                    ---
                    
                    ## 🚀 OTIMIZAÇÃO DO BOOSTER
                    {booster_content}
                    
                    ---
                    
                    ## 🎯 DECISÃO DO CEO
                    {ceo_content}
                    """
                    
                    exportar_relatorio(
                        full_content, 
                        "full", 
                        projeto,
                        formato="html"
                    )
            
            with col_full2:
                if st.button("📋 Exportar Dados do Projeto (JSON)", key="export_full_json"):
                    try:
                        historico = st.session_state.db.obter_historico_projeto(projeto_id)
                        historico['metadata'] = {
                            'ano_analise': ano,
                            'data_exportacao': datetime.now().isoformat(),
                            'versao_sistema': '1.2'
                        }
                        
                        json_data = json.dumps(historico, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="⬇️ Baixar JSON",
                            data=json_data,
                            file_name=f"{codigo}_completo_{ano}.json",
                            mime="application/json",
                            key="download_json_full"
                        )
                    except Exception as e:
                        st.error(f"Erro ao exportar: {e}")
        
        else:
            # Instruções antes da análise
            st.info(f"""
            ### ⏳ Pronto para análise ({ano})!
            
            Clique no botão **"EXECUTAR ANÁLISE COMPLETA"** acima para:
            
            1. **Hunter** encontrar 3 oportunidades no nicho
            2. **Booster** otimizar a melhor ideia  
            3. **CEO** tomar a decisão final
            
            ⏱️ Tempo estimado: 2-3 minutos
            
            ### 📊 O que você receberá:
            • 3 ideias de canais com métricas
            • Títulos virais e thumbnails
            • Plano de SEO completo
            • Estratégia de automação
            • Decisão final do CEO
            """)
    
    # RODAPÉ
    st.divider()
    col_foot1, col_foot2, col_foot3 = st.columns(3)
    
    with col_foot1:
        st.caption(f"🎬 **YouTube Automation CEO • {ano}**")
    
    with col_foot2:
        if st.session_state.projeto_atual:
            if isinstance(st.session_state.projeto_atual, dict):
                codigo = st.session_state.projeto_atual.get('codigo', 'N/A')
            else:
                codigo = st.session_state.projeto_atual.get('codigo_projeto', 'N/A')
            st.caption(f"📁 **Projeto:** {codigo}")
        else:
            st.caption("📁 **Status:** Sem projeto ativo")
    
    with col_foot3:
        st.caption(f"🚀 **Versão 1.2 • Com Exportação • {ano}**")

if __name__ == "__main__":
    main()