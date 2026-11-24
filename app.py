import asyncio
import os
import re
import tempfile
import streamlit as st
import edge_tts
from modern_greek_accentuation.transcription import modern_transcription
from modern_greek_accentuation.syllabify import modern_greek_syllabify
from modern_greek_accentuation.accentuation import is_accented

st.set_page_config(page_title="Greek Lyrics Phonetic Converter", page_icon="🎵", layout="centered")

default_lyrics = """Χαμένος κάπου στα στενά προς Φιλοπάππου
Εδώ που η πόλη καταφέρνει να μην βιάζεται"""

STRESS_ACCENT_MAP = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}

# Override rules for English conventions
def to_english_spelling(text: str, is_first_syl: bool = False) -> str:
    """Translates modern_transcription()'s European conventions to English."""
    s = (
        text.replace("ζ", "z")      # missed by modern_transcription
            .replace("w", "v")      # β / voiced αυ, ευ -> v
            .replace("u", "ou")     # ου -> ou
            .replace("jia", "ya")   # για -> ya
            .replace("j", "y")      # γ before front vowels -> y
            .replace("kie", "ke")   # και, κέντρο -> ke, KE-ndro
            .replace("chie", "che") # χέρια -> CHE-ria
            .replace("mp", "mb")    # μπ -> mb
            .replace("nt", "nd")    # ντ -> nd
    )
    if is_first_syl:
        s = re.sub(r"^mb", "b", s)
        s = re.sub(r"^nd", "d", s)
        s = re.sub(r"^ng", "g", s)
    return s


def apply_syllable_stress(phonetic: str, stress_style: str) -> str:
    """Applies the chosen stress formatting to a stressed syllable."""
    if stress_style == "upper":
        return phonetic.upper()
    if stress_style == "accent":
        def _accent_vowel(match):
            v = match.group(0)
            return "oú" if v == "ou" else STRESS_ACCENT_MAP.get(v, v)
        return re.sub(r"ou|[aeiou]", _accent_vowel, phonetic, count=1)
    return phonetic

# Convert individual word to English phonetic equivalent
def convert_word(word: str, stress_style: str, hyphenate: bool) -> str:
    syllables = modern_greek_syllabify(word.lower())
    converted = []

    for i, syl in enumerate(syllables):
        phonetic = to_english_spelling(modern_transcription(syl), is_first_syl=(i == 0))
        if len(syllables) > 1 and is_accented(syl):
            phonetic = apply_syllable_stress(phonetic, stress_style)
        converted.append(phonetic)

    return ("-" if hyphenate else "").join(converted)

# Convert Greek line to English phonetic equivalent
@st.cache_data(show_spinner=False)
def convert_line(line: str, stress_style: str, hyphenate: bool) -> str:
    return re.sub(
        r"[Α-Ωα-ωΆ-Ώά-ώϊϋΐΰ]+",
        lambda m: convert_word(m.group(0), stress_style, hyphenate),
        line,
    )

# Audio from edge-tts
async def _save_line_audio(text: str, voice: str, rate: str, filepath: str):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(filepath)

# Generate audio and cache
@st.cache_data(show_spinner=False)
def generate_line_audio(line: str, voice: str, rate: str) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp_path = tmp.name

    try:
        asyncio.run(_save_line_audio(line, voice, rate, tmp_path))
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# STREAMLIT UI
st.title("Greek Lyrics Phonetic Converter")

with st.sidebar:
    st.header("Phonetic Style")
    
    stress_style = st.selectbox(
        "Stress display",
        ["upper", "accent", "none"],
        on_change=lambda: st.session_state.pop("active_line", None),
    )
    hyphenate = st.checkbox(
        "Hyphenate syllables",
        value=True,
        on_change=lambda: st.session_state.pop("active_line", None),
    )

    st.divider()
    st.header("Audio Settings")
    voice_choice = st.selectbox("Greek Model Voice", ["Male", "Female"], index=0)
    voice = "el-GR-NestorasNeural" if voice_choice == "Male" else "el-GR-AthinaNeural"

    speed = st.slider("Playback speed (%)", min_value=-40, max_value=20, value=-15, step=5)
    rate_str = f"{speed:+d}%"

lyrics_input = st.text_area(
    "Paste Greek lyrics:",
    value=default_lyrics,
    height=200,
    on_change=lambda: st.session_state.pop("active_line", None),
)

if lyrics_input.strip():
    lines = lyrics_input.splitlines()

    st.subheader("Phonetic Lyrics")
    for idx, orig in enumerate(lines):
        if not orig.strip():
            st.write("")
            continue

        phonetic = convert_line(orig, stress_style, hyphenate)
        col_text, col_btn = st.columns([5, 1])

        with col_text:
            st.markdown(f"**{orig}**  \n`{phonetic}`")

        with col_btn:
            if st.button("🔊", key=f"play_{idx}", help="Pronounce this line"):
                st.session_state["active_line"] = idx

        # Show the audio player directly under the selected line
        if st.session_state.get("active_line") == idx:
            with st.spinner(""):
                try:
                    audio_bytes = generate_line_audio(orig, voice, rate_str)
                    st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                except Exception:
                    st.error("Audio generation failed. Please try the other model or try again later.")