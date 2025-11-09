import json
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

from src.fairness import regenerate_fairness

def test_regenerate_fairness_with_predictions(tmp_path: Path):
    # Arrange: create predictions.csv with a small demo attribute
    results_dir = tmp_path / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / 'predictions.csv'

    # two groups with slightly different scores
    df = pd.DataFrame({
        'y_true': [0,1,0,1,0,1,0,1],
        'y_prob': [0.1,0.7,0.2,0.8,0.3,0.85,0.4,0.9],
        'sex':    ['male','male','male','male','female','female','female','female']
    })
    df.to_csv(csv_path, index=False)

    fairness_dir = results_dir / 'fairness'

    # Act
    summary = regenerate_fairness(predictions_csv=csv_path, output_dir=fairness_dir)

    # Assert: summary file exists and has expected fields
    summary_fp = fairness_dir / 'fairness_summary.json'
    assert summary_fp.exists(), 'fairness_summary.json should be created'
    data = json.loads(summary_fp.read_text(encoding='utf-8'))
    assert 'status' in data
    assert data['status'] == 'ok'
    assert 'delta_auc' in data
    assert 'delta_ece' in data
    # sanity: aggregates non-empty and include our attribute
    assert any(a.get('attribute') == 'sex' for a in data.get('aggregates', []))


def test_regenerate_fairness_missing_inputs(tmp_path: Path):
    # Arrange: no predictions.csv present
    results_dir = tmp_path / 'results'
    fairness_dir = results_dir / 'fairness'

    # Act (should not raise)
    summary = regenerate_fairness(predictions_csv=results_dir / 'predictions.csv', output_dir=fairness_dir)

    # Assert
    summary_fp = fairness_dir / 'fairness_summary.json'
    assert summary_fp.exists(), 'fairness_summary.json should be created even when inputs missing'
    data = json.loads(summary_fp.read_text(encoding='utf-8'))
    assert 'status' in data
    assert data['status'] in ('missing_predictions', 'missing_columns')
    assert 'delta_auc' in data
    assert 'delta_ece' in data
