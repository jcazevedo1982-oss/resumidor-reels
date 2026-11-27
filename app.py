import os
import tempfile
from groq import Groq
import streamlit as st

st.set_page_config(page_title="Resumidor de Reels", page_icon="🎬")
st.title("🎬 Resumidor de Vídeos / Reels")

client = Groq(api_key=st.secrets["GROQ_API_KEY"])


def obter_modelo_chat():
  preferidos = [
      "llama-3.1-8b-instant",
      "openai/gpt-oss-120b",
      "openai/gpt-oss-20b",
      "qwen/qwen3-32b",
  ]
  try:
    disponiveis = {m.id for m in client.models.list().data}
    for modelo in preferidos:
      if modelo in disponiveis:
        return modelo
  except Exception:
    pass
  return "llama-3.1-8b-instant"


uploaded_file = st.file_uploader(
    "Carrega o vídeo (.mp4, .mov, .m4a, .mp3)", type=["mp4", "mov", "m4a", "mp3"]
)

if uploaded_file is not None:
  st.video(uploaded_file)

  if st.button("Transcrever e Resumir", type="primary"):
    with st.spinner("A transcrever e a gerar o resumo com Groq..."):
      suffix = os.path.splitext(uploaded_file.name)[1]
      with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

      try:
        # 1. Transcrição do áudio
        with open(tmp_path, "rb") as audio_file:
          transcription = client.audio.transcriptions.create(
              file=(uploaded_file.name, audio_file.read()),
              model="whisper-large-v3-turbo",
              language="pt",
              response_format="text",
          )

        texto_transcrito = transcription

        # 2. Resumo do conteúdo com modelo ativo
        modelo_ativo = obter_modelo_chat()
        chat_completion = client.chat.completions.create(
            model=modelo_ativo,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Resume a transcrição deste vídeo em tópicos claros,"
                        " estruturados e objetivos em português."
                    ),
                },
                {"role": "user", "content": texto_transcrito},
            ],
        )
        resumo = chat_completion.choices[0].message.content

        # 3. Apresentação dos resultados
        st.subheader("📝 Resumo")
        st.markdown(resumo)

        with st.expander("Ver transcrição completa"):
          st.write(texto_transcrito)

      except Exception as e:
        st.error(f"Erro ao processar o vídeo: {e}")

      finally:
        if os.path.exists(tmp_path):
          os.remove(tmp_path)
