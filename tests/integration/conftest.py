import pytest
import shutil
from pathlib import Path

@pytest.fixture(scope="session", autouse=True)
def clean_output_directories():
    """
    テストセッション開始時に、出力先ディレクトリ（logs, artifacts）を空にする
    """
    base_dir = Path(__file__).parent
    # クリーンアップ対象のディレクトリ名リスト
    targets = ["logs", "artifacts"]

    for target_name in targets:
        target_dir = base_dir / target_name

        if target_dir.exists():
            # フォルダごと削除
            shutil.rmtree(target_dir)
        
        # 空のフォルダを再作成
        target_dir.mkdir(exist_ok=True)
        print(f"\n[Setup] Cleared directory: {target_dir}")