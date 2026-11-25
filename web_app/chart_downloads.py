"""Display an analysis figure and offer a PNG of the same figure."""

from io import BytesIO
import re

import matplotlib.pyplot as plt
import streamlit as st


def render_chart(fig, name, width="stretch"):
    try:
        with BytesIO() as image:
            fig.savefig(image, format='png', dpi=160, bbox_inches='tight')
            png = image.getvalue()
        st.image(png, width=width)
        filename = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        st.download_button(f'Download {name} (PNG)', png, file_name=f'{filename}.png',
                           mime='image/png', on_click='ignore')
    finally:
        plt.close(fig)
