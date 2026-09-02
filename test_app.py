"""
Run the Streamlit app headlessly, with and without an upload, and fail loudly on
any exception. Patches st.file_uploader so the post-upload path is exercised too.
"""
import io
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

APP = Path(__file__).parent / "app.py"
SAMPLE = Path(__file__).parent / "sample_freelancer_upload.xlsx"


class FakeUpload(io.BytesIO):
    """Stands in for Streamlit's UploadedFile, which is itself a BytesIO with a name."""

    def __init__(self, path: Path):
        super().__init__(path.read_bytes())
        self.name = path.name


def report(at, label):
    if at.exception:
        print(f"FAIL {label}")
        for e in at.exception:
            print(e.value)
            print(e.stack_trace)
        raise SystemExit(1)
    print(f"OK   {label}: {len(at.dataframe)} tables, {len(at.metric)} metrics, "
          f"{len(at.tabs)} tabs, {len(at.error)} errors, {len(at.warning)} warnings")
    for w in at.warning:
        print(f"     warning: {w.value[:120]}")
    for e in at.error:
        print(f"     error:   {e.value[:120]}")


# --- 1. no upload: left pane + sidebar only ---
at = AppTest.from_file(str(APP), default_timeout=180).run()
report(at, "no upload")
print(f"     match options: {len(at.sidebar.selectbox[1].options)}")

# --- 2. with an upload: full comparison path ---
original = st.file_uploader
st.file_uploader = lambda *a, **k: FakeUpload(SAMPLE)
try:
    at2 = AppTest.from_file(str(APP), default_timeout=180)
    at2.run()
    # give the freelancer name so the scoreboard save button enables
    at2.text_input[0].set_value("Test Coder").run()
    report(at2, "with upload")
    for m in at2.metric:
        print(f"     {m.label}: {m.value}")
finally:
    st.file_uploader = original

print("\nAll app paths rendered without exceptions.")
