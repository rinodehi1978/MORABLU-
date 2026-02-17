"""Q&AテンプレートCSVをDBに取り込むスクリプト

使い方:
    python -m app.import_qa data/カスタマー対応Q＆A*.csv

販路の自動判別:
    CSVに販路列がないため、カテゴリ・種類・回答文のテキストから自動判別する。
"""

import csv
import sys
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models.qa_template import QaTemplate

# 販路判別ルール（上から順に評価、最初にマッチしたものを採用）
PLATFORM_RULES = [
    # (検索キーワード群, 判別する販路)
    (["FBA注文の場合", "アマゾン カスタマーサービス", "アマゾンカスタマーサービス",
      "アマゾンヘルプ", "FBA注文"], "amazon"),
    (["メルショ", "メルカリ"], "mercari"),
    (["クロスマ連携楽天RMS", "楽天RMS"], "rakuten"),
    (["ヤフオク・ヤフショ・楽天"], "yahoo_auction"),  # 複合だがヤフオク系統
    (["マルチチャネル注文", "マルチチャネル配送", "Amazon以外の販路"], "multi_channel"),
]


def detect_platform(category: str, subcategory: str, answer: str) -> str:
    """カテゴリ・種類・回答文から販路を自動判別する"""
    combined = f"{category} {subcategory} {answer}"

    for keywords, platform in PLATFORM_RULES:
        for kw in keywords:
            if kw in combined:
                return platform

    return "common"


def import_qa_csv(csv_path: str):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # 既存データをクリアして再投入
    existing = db.query(QaTemplate).count()
    if existing > 0:
        db.query(QaTemplate).delete()
        db.commit()
        print(f"Cleared {existing} existing templates.")

    records: list[QaTemplate] = []
    current_category = ""

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        for row_num, row in enumerate(reader, 1):
            # ヘッダー行（3行目）をスキップ
            if row_num <= 3:
                continue

            # 5列未満の行はスキップ
            if len(row) < 4:
                continue

            # 列: [空, 問い合わせ内容, 種類, 回答, 対応・留意点]
            inquiry = row[1].strip() if len(row) > 1 else ""
            subcategory = row[2].strip() if len(row) > 2 else ""
            answer = row[3].strip() if len(row) > 3 else ""
            notes = row[4].strip() if len(row) > 4 else ""

            # カテゴリが空の場合は前の行のカテゴリを引き継ぐ
            if inquiry:
                current_category = inquiry
            elif not current_category:
                continue

            # 回答が空の行はスキップ
            if not answer:
                continue

            # 販路を自動判別
            platform = detect_platform(current_category, subcategory, answer)

            records.append(
                QaTemplate(
                    category=current_category,
                    subcategory=subcategory or None,
                    platform=platform,
                    answer_template=answer,
                    staff_notes=notes or None,
                )
            )

    db.add_all(records)
    db.commit()
    print(f"Imported {len(records)} Q&A templates.")

    # サマリー表示
    platform_counts: dict[str, int] = {}
    for r in records:
        platform_counts[r.platform] = platform_counts.get(r.platform, 0) + 1
    print("\n--- 販路別件数 ---")
    for plat, count in sorted(platform_counts.items()):
        print(f"  {plat}: {count}件")

    print("\n--- カテゴリ別件数 ---")
    categories: dict[str, int] = {}
    for r in records:
        categories[r.category] = categories.get(r.category, 0) + 1
    for cat, count in categories.items():
        label = cat[:40] + "..." if len(cat) > 40 else cat
        print(f"  {label}: {count}件")

    db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # デフォルトパスを探す
        data_dir = Path("data")
        csv_files = list(data_dir.glob("カスタマー対応Q*A*.csv"))
        if not csv_files:
            print("Usage: python -m app.import_qa <csv_path>")
            sys.exit(1)
        csv_path = str(csv_files[0])
    else:
        csv_path = sys.argv[1]

    print(f"Importing: {csv_path}")
    import_qa_csv(csv_path)
