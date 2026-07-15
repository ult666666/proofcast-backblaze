"""Streamlit user interface for ProofCast."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from proofcast.config import Settings
from proofcast.pipeline import GenerationRequest, generate_bundle, local_path_from_asset


st.set_page_config(page_title="ProofCast", page_icon="◉", layout="wide")

st.title("ProofCast")
st.caption("Turn a short lesson into local AI narration with verifiable media provenance.")

settings = Settings.from_env()
try:
    settings.validate()
except ValueError as exc:
    st.error(f"Configuration error: {exc}")
    st.stop()

storage_label = "Backblaze B2 enabled" if settings.b2_enabled else "Local demo mode — no cloud writes"
st.info(storage_label)

with st.form("generation"):
    title = st.text_input("Brief title", value="Three ways to spot a phishing message", max_chars=90)
    script = st.text_area(
        "Narration script",
        value=(
            "Pause before opening unexpected links. Check the sender address, not only the display "
            "name. When a message creates urgency, verify the request through a second channel."
        ),
        height=180,
        max_chars=settings.max_script_chars,
    )
    left, right = st.columns(2)
    with left:
        voice = st.text_input("Local voice", value="Samantha")
    with right:
        rate = st.slider("Speaking rate", 120, 240, 175)
    consent = st.checkbox(
        "This script is non-sensitive and I understand its prompt appears in the provenance manifest."
    )
    submitted = st.form_submit_button("Generate proof-backed brief", type="primary")

if submitted:
    if not consent:
        st.warning("Confirm the non-sensitive content notice before generating.")
        st.stop()
    try:
        with st.spinner("Generating two local media assets and verifying the manifest..."):
            generated = generate_bundle(
                GenerationRequest(title=title, script=script, voice=voice, rate=rate),
                settings,
            )
    except Exception as exc:  # Streamlit should surface a useful, non-secret error.
        st.error(f"Generation failed: {exc}")
        st.stop()

    st.success(f"Verified provenance: {generated.verified}")
    st.code(generated.canonical_hash, language=None)
    media_columns = st.columns(2)
    for asset in generated.assets:
        local_path = local_path_from_asset(asset)
        source: str | bytes
        if local_path and local_path.exists():
            source = local_path.read_bytes()
        else:
            source = asset.url
        if asset.media_type.startswith("audio/"):
            with media_columns[0]:
                st.subheader("Narration")
                st.audio(source, format=asset.media_type)
                st.caption(asset.url)
        elif asset.media_type.startswith("image/"):
            with media_columns[1]:
                st.subheader("Accessible cover")
                st.image(source, use_container_width=True)
                st.caption(asset.url)

    with st.expander("Providers, models, and manifest"):
        st.write(list(generated.providers_and_models))
        st.download_button(
            "Download canonical manifest",
            data=Path(generated.manifest_path).read_bytes(),
            file_name=generated.manifest_path.name,
            mime="application/json",
        )

st.divider()
st.caption(
    "Zero-provider-cost design: Apple Speech or eSpeak NG runs locally; cloud writes stay off unless "
    "B2_ENABLED=1 is explicitly configured. Script length is capped to control storage and runtime."
)

