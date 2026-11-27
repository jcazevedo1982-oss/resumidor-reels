import os
import tempfile
from openai import OpenAI
import streamlit as st

st.set_page_config(page_title="Resumidor de Reels", page_icon="🎬")
st.title("🎬 Resumidor de Vídeos / Reels")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

uploaded_file = st.file_uploader(
    "Carrega o vídeo (.mp4, .mov, .m4a, .mp3)", type=["mp4", "mov", "m4a", "mp3"]
)

if uploaded_file is not None:
  st.video(uploaded_file)

  if st.button("Transcrever e Resumir", type="primary"):
    with st.spinner("A processar o áudio e a gerar o resumo..."):
      suffix = os.path.splitext(uploaded_file.name)[1]
      with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

      try:
        with open(tmp_path, "rb") as audio_file:
          transcript = client.audio.transcriptions.create(
              model="whisper-1", file=audio_file, language="pt"
          )

        texto_transcrito = transcript.text

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Resume a transcrição deste vídeo em tópicos claros e"
                        " objetivos em português."
                    ),
                },
                {"role": "user", "content": texto_transcrito},
            ],
        )
        resumo = response.choices[0].message.content

        st.subheader("📝 Resumo")
        st.markdown(resumo)

        with st.expander("Ver transcrição completa"):
          st.write(texto_transcrito)

      except Exception as e:
        st.error(f"Erro ao processar o vídeo: {e}")

      finally:
        if os.path.exists(tmp_path):
          os.remove(tmp_path)