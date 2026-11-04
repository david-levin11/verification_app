"""Administrator-owned archive locations. Browser state never supplies paths."""
from pathlib import Path
import streamlit as st

REPOSITORY_ROOT=Path(__file__).resolve().parents[1]


def configured_paths():
    try:
        settings=dict(st.secrets.get('local',{}))
    except (FileNotFoundError,KeyError):
        settings={}
    def path(name,default):
        value=settings.get(name)
        if value is None or value=='':return str(default)
        if not isinstance(value,str):raise ValueError(f'local.{name} must be a filesystem path string')
        result=Path(value).expanduser()
        return str(result if result.is_absolute() else REPOSITORY_ROOT/result)
    archive=path('archive_root',REPOSITORY_ROOT/'model')
    return {'archive_root':archive,
            'refs_root':path('refs_root',Path(archive).parent/'derived'/'refs'),
            'metadata_path':path('metadata_path',REPOSITORY_ROOT/'metadata'/'ak_station_metadata.parquet')}
