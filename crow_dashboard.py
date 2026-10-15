"""Entry point for the Crooked Crow Pickling Co. sales dashboard demo.

Everything on screen is invented: a fictional pickle and ferments maker whose data
lives in data/crooked_crow.duckdb (rebuild it with make_data.py). The app answers why
the numbers moved -- price, volume and mix bridges, account movement, quiet
accounts -- and every bar chart and table drills into what was clicked.
"""

from pathlib import Path

import streamlit as st

import sales_lib as lib

st.set_page_config(page_title="Crooked Crow Sales", page_icon=str(Path(__file__).parent / "assets" / "crow-icon.png"), layout="wide")

ASSETS = Path(__file__).parent / "assets"

TIGHTEN_TOP = """
<style>
  .block-container { padding-top: 3rem; padding-bottom: 1rem; }
  .block-container h3 { margin-bottom: 0.25rem; }
  .block-container h5 { margin-top: 0.6rem; margin-bottom: 0.1rem; }
  .block-container h6 { margin-top: 0.2rem; margin-bottom: 0.1rem; }
  .bb-title {
    display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap;
    padding: 0.55rem 1rem; margin-bottom: 0.6rem; border-radius: 0.6rem;
    background: linear-gradient(100deg, #052a33 0%, #0e7c86 55%, #6fd6a3 100%);
    border: 0;
  }
  .bb-title .company { font-size: 1.35rem; font-weight: 700; color: #ffffff; }
  .bb-title .dash { font-size: 1.05rem; color: #ffd98a; }
  .st-key-sales_header {
    position: sticky; top: 3.75rem; z-index: 99;
    background: #f5f8f6; border-bottom: 1px solid #bccfc8; padding-bottom: 0.4rem;
  }
</style>
"""

TITLE_BAR = """
<div class="bb-title">
  <span class="company">Crooked Crow Pickling Co.</span>
  <span class="dash">Sales Performance Dashboard Demo</span>
</div>
"""

PAGES = [
    st.Page(path, title=title, default=index == 0)
    for index, (title, path) in enumerate(lib.PAGE_FILES.items())
]


def show_logo() -> None:
    """Put the Crooked Crow logo above the navigation.

    Skips it when the image files are missing so the app still starts, which
    is what happens if the assets folder is not copied along.

    Returns:
        None.
    """
    logo = ASSETS / "crow-lockup.png"
    barn = ASSETS / "crow-icon.png"
    if logo.exists() and barn.exists():
        st.logo(str(logo), icon_image=str(barn), size="large")


def show_title_bar() -> None:
    """Draw the company and dashboard name above every page.

    Returns:
        None.
    """
    st.markdown(TITLE_BAR, unsafe_allow_html=True)


def main() -> None:
    """Render the navigation bar and run the selected page.

    Navigation sits across the top rather than in the sidebar, which leaves the
    full width for charts that are already reading long customer and item names.
    `position` arrived in Streamlit 1.46; if the installed Streamlit is older
    than pyproject.toml asks for, fall back to the sidebar rather than failing
    to start, since only the nav bar moves.
    """
    st.markdown(TIGHTEN_TOP, unsafe_allow_html=True)
    show_logo()
    show_title_bar()
    try:
        navigation = st.navigation(PAGES, position="top")
    except TypeError:
        navigation = st.navigation(PAGES)
    lib.remember_page(navigation)
    navigation.run()


main()
