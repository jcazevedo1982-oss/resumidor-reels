import os
import re
import streamlit as st
import instaloader
import whisper
import google.generativeai as genai
from docx import Document
from io import BytesIO

# Configuração da página
st.set_page_config(
    page_title="Instagram Reel Summarizer",
    page_icon="🎬",
    layout="centered"
)

st.title("🎬 Resumidor de Reels do Instagram")
st.write("Insere o link de um Reel para transcrever, resumir e exportar para Word.")

# Entrada da chave da API e do URL do Reel
api_key = st.sidebar.text_input("Chave API do Gemini", type="password", help="Obtém gratuitamente em https://aistudio.google.com/")
reel_url = st.text_input("URL do Reel do Instagram:", placeholder="https://www.instagram.com/reel/...")

@st.cache_resource
def load_whisper_model():
    """Carrega o modelo Whisper para transcrição de áudio."""
    return whisper.load_model("base")

def extract_shortcode(url):
    """Extrai o código único do Reel a partir do URL do Instagram."""
    match = re.search(r'(?:reel|p)/([A-Za-z0-9_-]+)', url)
    return match.group(1) if match else None

def download_reel_audio(url):
    """Efetua o download do vídeo/áudio do Reel através do Instaloader."""
    shortcode = extract_shortcode(url)
    if not shortcode:
        raise ValueError("URL do Reel inválido. Certifica-te de que o link contém '/reel/' ou '/p/'.")
        
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False
    )
    
    target_dir = f"temp_{shortcode}"
    post = instaloader.Post.from_shortcode(L.context, shortcode)
    L.download_post(post, target=target_dir)
    
    for file in os.listdir(target_dir):
        if file.endswith(".mp4"):
            return os.path.join(target_dir, file), target_dir
            
    raise FileNotFoundError("Não foi possível extrair o vídeo do Reel.")

def get_active_gemini_model():
    """Lista dinamicamente os modelos ativos associados à chave de API do utilizador."""
    supported_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            # Substitui 'models/' no nome se presente
            name = m.name.replace('models/', '')
            supported_models.append(name)
            
    # Dá prioridade a modelos Flash se disponíveis
    for m_name in supported_models:
        if 'flash' in m_name:
            return m_name
            
    if supported_models:
        return supported_models[0]
        
    raise RuntimeError("Nenhum modelo Gemini com suporte a 'generateContent' foi encontrado na tua conta.")

def create_word_docx(summary_text, transcription_text):
    """Gera o documento Word (.docx)."""
    doc = Document()
    doc.add_heading('Resumo do Reel do Instagram', level=0)
    
    doc.add_heading('Resumo Estruturado', level=1)
    for p in summary_text.split('\n'):
        if p.strip():
            doc.add_paragraph(p)
            
    doc.add_heading('Transcrição Completa', level=1)
    doc.add_paragraph(transcription_text)
    
    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

if st.button("Processar Reel", type="primary"):
    if not api_key:
        st.error("Por favor, introduz a tua Chave API do Gemini na barra lateral.")
    elif not reel_url:
        st.warning("Por favor, introduz um link válido do Instagram.")
    else:
        temp_file = None
        temp_dir = None
        try:
            # 1. Download do áudio do Reel
            with st.spinner("1/4 A obter o Reel do Instagram..."):
                temp_file, temp_dir = download_reel_audio(reel_url)
            
            # 2. Transcrição do áudio com Whisper
            with st.spinner("2/4 A transcrever o áudio (Whisper)..."):
                model = load_whisper_model()
                result = model.transcribe(temp_file)
                transcription = result['text']
            
            # 3. Identificação e geração do resumo com o Gemini
            with st.spinner("3/4 A ligar à IA e a gerar resumo..."):
                genai.configure(api_key=api_key)
                model_name = get_active_gemini_model()
                
                gemini_model = genai.GenerativeModel(model_name)
                prompt = (
                    "Lê a seguinte transcrição de um Reel do Instagram e cria um resumo claro, "
                    "bem formatado e estruturado em tópicos principais:\n\n"
                    f"{transcription}"
                )
                response = gemini_model.generate_content(prompt)
                summary = response.text

            # Apresentação dos Resultados
            st.success("Processamento concluído!")
            
            st.subheader("📝 Resumo Gerado")
            st.markdown(summary)
            
            with st.expander("Ver Transcrição Completa"):
                st.write(transcription)

            # 4. Exportação para Word
            doc_file = create_word_docx(summary, transcription)
            st.download_button(
                label="📄 Transferir Ficheiro Word (.docx)",
                data=doc_file,
                file_name="Resumo_Reel.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

        except Exception as e:
            st.error(f"Ocorreu um erro ao processar: {str(e)}")
            
        finally:
            # Limpeza de ficheiros temporários
            if temp_dir and os.path.exists(temp_dir):
                for f in os.listdir(temp_dir):
                    try:
                        os.remove(os.path.join(temp_dir, f))
                    except Exception:
                        pass
                try:
                    os.rmdir(temp_dir)
                except Exception:
                    pass
