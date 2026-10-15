"""Entry point for a dashboard. Copy, rename, fill in.

Say here, in a few sentences, what question this app answers and which relation
it reads. A reader who opens this file should not have to guess why the pages
are in the order they are in.
"""

from pathlib import Path

import streamlit as st

import dashboard_lib as lib

st.set_page_config(page_title="My Dashboard", layout="wide")

ASSETS = Path(__file__).parent / "assets"

PAGES = [
    st.Page("pages/overview.py", title="Overview", default=True),
    st.Page("pages/detail.py", title="Detail"),
]


def show_logo() -> None:
    """Put the logo above the navigation.

    Skips it when the image files are missing so the app still starts, which is
    what happens if the assets are left out of snowflake.yml's artifacts.

    Args:
        None.

    Returns:
        None.
    """
    logo = ASSETS / "lockup.png"
    icon = ASSETS / "icon.png"
    if logo.exists() and icon.exists():
        st.logo(str(logo), icon_image=str(icon), size="large")


def main() -> None:
    """Render the navigation bar and run the selected page.

    Navigation sits across the top rather than in the sidebar, matching the
    other dashboards. `position` arrived in Streamlit 1.46; if Snowflake
    resolves an older build than pyproject.toml asks for, fall back to the
    sidebar rather than failing to start, since only the nav bar moves.

    Args:
        None.

    Returns:
        None.
    """
    st.markdown(lib.PAGE_STYLE, unsafe_allow_html=True)
    show_logo()
    try:
        navigation = st.navigation(PAGES, position="top")
    except TypeError:
        navigation = st.navigation(PAGES)
    lib.remember_page(navigation)
    navigation.run()


main()
