"""Collect detailed outputs into one download panel instead of inline tables."""
import json
import re
import pandas as pd
import streamlit as st


class DataDownloads:
    def __init__(self, page):
        self.page, self.items, self.rendered = page, [], False
        self.warned = False

    def add(self, data, name='Results', **kwargs):
        if isinstance(data,pd.DataFrame):frame=data
        elif isinstance(data,dict) and all(pd.api.types.is_scalar(v) for v in data.values()):frame=pd.DataFrame([data])
        else:frame=pd.DataFrame(data)
        self.file(f'Download {name} (CSV)', frame.to_csv(index=False),
                  re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')+'.csv', 'text/csv')

    def add_json(self, data, name='Diagnostics', **kwargs):
        self.file(f'Download {name} (JSON)', json.dumps(data, default=str, indent=2),
                  re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')+'.json', 'application/json')

    def file(self, label, data, file_name=None, mime=None, **kwargs):
        self.items.append((label, data, file_name, mime))

    def issue(self, message, fatal=False):
        self.add_json({'details':str(message)}, 'Data loading details')
        text = ('No usable data were found for this request. Check the archive coverage above, '
                'selected stations, and forecast run.' if fatal else
                'Some requested data could not be used. Results include the usable cases; '
                'data loading details are available in Downloads.')
        if fatal:st.error(text)
        elif not self.warned:
            st.warning(text)
            self.warned = True

    def render(self):
        if self.rendered or not self.items:return
        self.rendered = True
        with st.expander('Downloads — tables and diagnostics'):
            for index, (label, data, filename, mime) in enumerate(self.items):
                st.download_button(label, data, file_name=filename, mime=mime,
                    key=f'{self.page}_detail_download_{index}')

    def stop(self):
        self.render()
        st.stop()
