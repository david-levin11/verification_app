"""Private feedback storage and the submission workflow."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
import os
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parents[1] / 'web_app'
sys.path.insert(0, str(ROOT))
from feedback_queue import list_feedback, resolve_feedback, save_feedback


def test_queue_handles_concurrent_submissions_and_resolution(tmp_path):
    path = tmp_path / 'private' / 'feedback.sqlite3'
    assert list(list_feedback(path)) == [] and not path.exists()
    with ThreadPoolExecutor(max_workers=4) as workers:
        ids = list(workers.map(
            lambda i: save_feedback(path, kind='Bug report', page='Home',
                                    title=f'Report {i}', details='Observed a problem.'),
            range(12),
        ))
    assert len(set(ids)) == 12
    assert len(list(list_feedback(path))) == 12
    if os.name == 'posix':
        assert path.stat().st_mode & 0o077 == 0
    resolve_feedback(path, ids[0])
    assert len(list(list_feedback(path))) == 11
    assert [report['id'] for report in list_feedback(path, 'resolved')] == [ids[0]]
    with pytest.raises(ValueError, match='not found'):
        resolve_feedback(path, 'unknown')


def test_reporters_preview_and_opt_in_to_page_settings(tmp_path, monkeypatch):
    database = tmp_path / 'queue.sqlite3'
    monkeypatch.setenv('VERIFICATION_FEEDBACK_DB', str(database))
    metadata = tmp_path / 'stations.csv'
    pd.DataFrame(dict(station_id=['A'], latitude=[60], longitude=[-150])).to_csv(metadata, index=False)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20)
    app.secrets['local'] = dict(metadata_path=str(metadata), archive_root=str(tmp_path / 'archive'))
    app.run()
    assert not app.exception
    assert app.text_input(key='feedback_home_title')
    app.switch_page('pages/1_Map_Explorer.py').run()
    prefix = 'feedback_map_explorer'
    app.date_input(key='map_ui_start_date').set_value(date(2026, 11, 1)).run()
    next(button for button in app.button if button.label == 'Submit feedback').click().run()
    assert not database.exists()
    assert any('Enter a summary' in item.value for item in app.error)

    app.text_input(key=f'{prefix}_title').set_value('Missing station')
    app.text_area(key=f'{prefix}_details').set_value('A station selected yesterday is absent.')
    next(button for button in app.button if button.label == 'Submit feedback').click().run()
    assert not app.exception
    reports = list(list_feedback(database))
    assert len(reports) == 1 and reports[0]['context'] is None
    assert app.text_input(key=f'{prefix}_title').value == ''
    assert any(reports[0]['id'] in item.value for item in app.success)

    app.selectbox(key=f'{prefix}_kind').set_value('Improvement')
    app.text_input(key=f'{prefix}_title').set_value('Add station filters')
    app.text_area(key=f'{prefix}_details').set_value('Please add a station type filter.')
    app.checkbox(key=f'{prefix}_include_context').set_value(True)
    next(button for button in app.button if button.label == 'Submit feedback').click().run()
    assert not app.exception
    report = next(item for item in list_feedback(database) if item['kind'] == 'Improvement')
    assert report['page'] == 'Map Explorer'
    assert report['context']['start_date'] == '2026-11-01'
    assert report['context']['model'] == app.selectbox(key='map_ui_model').value
    assert 'archive_root' not in report['context']
    assert 'metadata_path' not in report['context']


def test_submission_failure_preserves_text_for_retry(tmp_path, monkeypatch):
    invalid_parent = tmp_path / 'not-a-directory'
    invalid_parent.touch()
    monkeypatch.setenv('VERIFICATION_FEEDBACK_DB', str(invalid_parent / 'queue.sqlite3'))
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    app.text_input(key='feedback_home_title').set_value('Example')
    app.text_area(key='feedback_home_details').set_value('Keep these details when saving fails.')
    next(button for button in app.button if button.label == 'Submit feedback').click().run()
    assert not app.exception
    assert any('Could not save' in item.value for item in app.error)
    assert app.text_input(key='feedback_home_title').value == 'Example'
    assert app.text_area(key='feedback_home_details').value == 'Keep these details when saving fails.'
