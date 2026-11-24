import os
import re
import tempfile
from pathlib import Path

import streamlit as st
import instaloader
import whisper
import google.generativeai as genai
from docx import Document
from io import BytesIO


st.set_page_config(
    page_title="Instagram Reel Summarizer",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 Resumidor de Reels do Instagram")
st.write(
    "Insere um link público de um Reel ou carrega diretamente o vídeo. "
    "A aplicação transcreve o áudio, cria um resumo e permite exportar para Word."
)

api_key = st.sidebar.text_input(
    "Chave API do Gemini",
    type="password",
    help="Obtém uma chave em https://aistudio.google.com/",
)

st.subheader("1. Escolhe como fornecer o Reel")
source_mode = st.radio(
    "Origem do vídeo",
    ["Link do Instagram", "Carregar ficheiro de vídeo"],
    horizontal=True,
)

reel_url = ""
uploaded_video = None

if source_mode == "Link do Instagram":
    reel_url = st.text_input(
        "URL do Reel do Instagram",
        placeholder="https://www.instagram.com/reel/...",
    )
    st.caption(
        "Nota: o Instagram altera frequentemente os seus mecanismos de acesso. "
        "Se a leitura do link falhar, experimenta carregar o ficheiro de vídeo."
    )
else:
    uploaded_video = st.file_uploader(
        "Seleciona o vídeo do Reel",
        type=["mp4", "mov", "m4v", "webm"],
        help="Formatos aceites: MP4, MOV, M4V e WEBM.",
    )


@st.cache_resource
def load_whisper_model():
    """Carrega o modelo Whisper uma única vez por sessão do servidor."""
    return whisper.load_model("base")


def extract_shortcode(url: str):
    """Extrai o shortcode de URLs comuns de publicações e Reels."""
    match = re.search(
        r"(?:instagram\.com/)?(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)",
        url,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def download_reel_video(url: str, destination: Path) -> Path:
    """
    Tenta descarregar um Reel público através do Instaloader.
    Este método depende dos endpoints e das regras de acesso do Instagram.
    """
    shortcode = extract_shortcode(url.strip())
    if not shortcode:
        raise ValueError(
            "Não reconheci o link. Usa o URL completo de um Reel público "
            "(por exemplo, instagram.com/reel/...)."
        )

    loader = instaloader.Instaloader(
        dirname_pattern=str(destination / "{target}"),
        filename_pattern="{shortcode}",
        download_pictures=False,
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )

    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        loader.download_post(post, target="reel")
    except Exception as exc:
        raise RuntimeError(
            "O Instagram não permitiu obter os metadados/vídeo deste Reel. "
            "Isto pode acontecer mesmo com links públicos devido a alterações "
            "ou bloqueios do Instagram. Experimenta a opção «Carregar ficheiro "
            "de vídeo». Detalhe técnico: " + str(exc)
        ) from exc

    video_files = list(destination.rglob("*.mp4"))
    if not video_files:
        raise FileNotFoundError(
            "O Instagram não disponibilizou um ficheiro MP4 para este Reel."
        )
    return video_files[0]


def create_word_docx(summary_text: str, transcription_text: str) -> BytesIO:
    """Gera o documento Word com resumo e transcrição."""
    doc = Document()
    doc.add_heading("Resumo do Reel do Instagram", level=0)

    doc.add_heading("Resumo Estruturado", level=1)
    for paragraph in summary_text.splitlines():
        if paragraph.strip():
            doc.add_paragraph(paragraph)

    doc.add_heading("Transcrição Completa", level=1)
    doc.add_paragraph(transcription_text)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def generate_summary(transcription: str, key: str) -> str:
    """Gera o resumo através do Gemini."""
    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-3.8-flash")
    prompt = (
        "Analisa a transcrição seguinte, em português. "
        "Produz um resumo claro e fiel, organizado em: "
        "1) Ideia principal; 2) Pontos-chave; 3) Conclusões ou recomendações. "
        "Não inventes informação que não esteja na transcrição.\n\n"
        f"TRANSCRIÇÃO:\n{transcription}"
    )
    response = model.generate_content(prompt)
    if not response or not getattr(response, "text", None):
        raise RuntimeError(
            "O Gemini não devolveu texto. Verifica a chave API e os limites da conta."
        )
    return response.text


if st.button("Processar Reel", type="primary", use_container_width=True):
    if not api_key:
        st.error("Introduz a tua chave API do Gemini na barra lateral.")
    elif source_mode == "Link do Instagram" and not reel_url.strip():
        st.warning("Introduz o link do Reel.")
    elif source_mode == "Carregar ficheiro de vídeo" and uploaded_video is None:
        st.warning("Seleciona primeiro um ficheiro de vídeo.")
    else:
        try:
            with tempfile.TemporaryDirectory(prefix="reel_summarizer_") as temp_dir:
                temp_path = Path(temp_dir)

                # 1. Obter o vídeo, por URL ou por carregamento manual.
                with st.spinner("1/4 A obter o vídeo..."):
                    if source_mode == "Link do Instagram":
                        video_path = download_reel_video(reel_url, temp_path)
                    else:
                        suffix = Path(uploaded_video.name).suffix.lower() or ".mp4"
                        video_path = temp_path / f"reel{suffix}"
                        video_path.write_bytes(uploaded_video.getvalue())

                # 2. Transcrever o áudio.
                with st.spinner("2/4 A transcrever o áudio com Whisper..."):
                    model = load_whisper_model()
                    result = model.transcribe(str(video_path))
                    transcription = (result.get("text") or "").strip()

                if not transcription:
                    raise RuntimeError(
                        "Não foi detetado áudio/transcrição no vídeo. "
                        "Confirma se o vídeo tem som."
                    )

                # 3. Gerar resumo.
                with st.spinner("3/4 A gerar o resumo com Gemini..."):
                    summary = generate_summary(transcription, api_key)

                # 4. Apresentar e exportar.
                st.success("Processamento concluído!")
                st.subheader("📝 Resumo Gerado")
                st.markdown(summary)

                with st.expander("Ver transcrição completa"):
                    st.write(transcription)

                doc_file = create_word_docx(summary, transcription)
                st.download_button(
                    label="📄 Transferir ficheiro Word (.docx)",
                    data=doc_file,
                    file_name="Resumo_Reel.docx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    use_container_width=True,
                )

        except Exception as exc:
            st.error(f"Não foi possível concluir o processamento: {exc}")
            st.info(
                "Se estás a usar um link do Instagram, tenta carregar o vídeo "
                "diretamente. A extração automática por URL depende do acesso "
                "que o Instagram permite naquele momento."
            )
