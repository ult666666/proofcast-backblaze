"""Streamlit user interface for ProofCast."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from proofcast.config import Settings
from proofcast.pipeline import GenerationRequest, generate_bundle, local_path_from_asset


st.set_page_config(page_title="ProofCast", page_icon="◉", layout="wide")

st.title("ProofCast")
st.caption(
    "Turn a short lesson into a narrated WAV file and a cover image, "
    "with a manifest that records how both were made."
)

settings = Settings.from_env()
try:
    settings.validate()
except ValueError as exc:
    st.error(f"Configuration error: {exc}")
    st.stop()

if settings.b2_enabled:
    st.info("Backblaze B2 is on: each run uploads the narration, the cover and the manifest.")
else:
    st.caption("Local mode: files are saved on this computer and nothing is uploaded.")

with st.form("generation"):
    title = st.text_input("Title", value="Three ways to spot a phishing message", max_chars=90)
    script = st.text_area(
        "Script",
        value=(
            "Pause before opening unexpected links. Check the sender address, not only the display "
            "name. When a message creates urgency, verify the request through a second channel."
        ),
        height=180,
        max_chars=settings.max_script_chars,
    )
    left, right = st.columns(2)
    with left:
        voice = st.text_input(
            "Voice",
            value="Samantha",
            help="An Apple Speech voice on macOS. eSpeak NG on Linux always uses en-us.",
        )
    with right:
        rate = st.slider("Speaking rate (words per minute)", 120, 240, 175)
    consent = st.checkbox(
        "The script contains nothing sensitive, and I understand it is stored in the manifest."
    )
    submitted = st.form_submit_button("Generate", type="primary")

if submitted:
    if not consent:
        st.warning("Confirm that the script contains nothing sensitive before generating.")
        st.stop()
    try:
        with st.spinner("Generating the narration and the cover, then checking both files..."):
            generated = generate_bundle(
                GenerationRequest(title=title, script=script, voice=voice, rate=rate),
                settings,
            )
    except Exception as exc:  # Streamlit should surface a useful, non-secret error.
        st.error(f"Generation failed: {exc}")
        st.stop()

    if generated.verified:
        st.success("Verified: the manifest is intact and both files match it.")
    else:
        st.error("Verification failed. Read the report below before using these files.")
    st.caption(
        "This shows the files match the manifest. "
        "It does not show who made them or that the recorded prompt produced them."
    )
    with st.expander("Verification report"):
        st.json(generated.verification.to_dict())
    st.caption("Manifest hash (SHA-256)")
    st.code(generated.canonical_hash, language=None)
    media_columns = st.columns(2)
    for asset in generated.assets:
        local_path = local_path_from_asset(asset)
        source: str | bytes
        if local_path and local_path.exists():
            source = local_path.read_bytes()
        else:
            source = asset.url
        location = local_path.name if local_path else asset.url
        if asset.media_type.startswith("audio/"):
            with media_columns[0]:
                st.subheader("Narration")
                st.audio(source, format=asset.media_type)
                st.caption(location)
        elif asset.media_type.startswith("image/"):
            with media_columns[1]:
                st.subheader("Cover")
                st.image(source, width="stretch")
                st.caption(location)

    with st.expander("Providers and manifest"):
        st.write(list(generated.providers_and_models))
        st.download_button(
            "Download manifest",
            data=Path(generated.manifest_path).read_bytes(),
            file_name=generated.manifest_path.name,
            mime="application/json",
        )

st.divider()
st.caption("ProofCast · [Source](https://github.com/ult666666/proofcast-backblaze) · MIT license")
