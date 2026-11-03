"""Page-local widget values that survive Streamlit's multipage widget cleanup."""
import streamlit as st

def local_path_defaults(page):
    """Optional machine-specific paths; normal page/session edits take precedence."""
    try:
        paths=dict(st.secrets.get('local',{}))
    except (FileNotFoundError,KeyError):
        return {}
    keys={
        'map': {'archive_root':'map_ui_archive_root','metadata_path':'map_metadata_path','refs_root':'map_refs_root'},
        'aggregate': {'archive_root':'aggregate_ui_archive_root','refs_root':'aggregate_refs_root'},
        'storm': {'archive_root':'storm_Local Archive Root','metadata_path':'storm_metadata','refs_root':'storm_refs_root'},
        'compare': {'archive_root':'compare_archive_root','metadata_path':'compare_metadata','refs_root':'compare_refs_root'},
    }
    return {key:paths[name] for name,key in keys.get(page,{}).items()
            if isinstance(paths.get(name),str) and paths[name].strip()}


_WIDGETS = {'text_input', 'selectbox', 'radio', 'checkbox', 'number_input',
            'date_input', 'multiselect', 'slider'}


def remember_widget(page, key):
    values = dict(st.session_state.get(f'_page_settings_{page}', {}))
    values[key] = st.session_state[key]
    st.session_state[f'_page_settings_{page}'] = values


def set_page_value(page, key, value):
    """Use from callbacks, before the destination widget is rendered."""
    st.session_state[key] = value
    remember_widget(page, key)


class PageControls:
    """Wrap only input widgets; results and button state remain outside settings."""
    def __init__(self, page, container=None):
        self.page = page
        self.container = st if container is None else container
        self.defaults = local_path_defaults(page)

    @property
    def sidebar(self):
        return PageControls(self.page, st.sidebar)

    def columns(self, *args, **kwargs):
        return [PageControls(self.page, col) for col in self.container.columns(*args, **kwargs)]

    def __getattr__(self, name):
        method = getattr(self.container, name)
        if name not in _WIDGETS:
            return method

        def widget(label, *args, **kwargs):
            key = kwargs.pop('key', f'{self.page}_{label}')
            if not key.startswith(f'{self.page}_'):
                key = f'{self.page}_{key}'
            values = st.session_state.get(f'_page_settings_{self.page}', {})
            if name=='text_input' and key not in st.session_state and key not in values and key in self.defaults:
                if args:args=(self.defaults[key],)+args[1:]
                else:kwargs['value']=self.defaults[key]
            if key not in st.session_state and key in values:
                st.session_state[key] = values[key]
            # Dependent model/element/filter options may have changed. Discard
            # invalid saved values before constructing the dependent widget.
            if name in {'selectbox', 'radio', 'multiselect'}:
                options = list(args[0] if args else kwargs['options'])
                if key in st.session_state:
                    value = st.session_state[key]
                    valid = (all(v in options for v in value) if name == 'multiselect'
                             else value in options)
                    if not valid:
                        del st.session_state[key]
            kwargs.update(key=key, on_change=remember_widget, args=(self.page, key))
            value = method(label, *args, **kwargs)
            remember_widget(self.page, key)
            return value
        return widget

