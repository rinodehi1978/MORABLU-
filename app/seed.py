"""初期データ＆テストデータ投入スクリプト

使い方:
    python -m app.seed
"""

from datetime import datetime, timedelta, timezone

from app.database import Base, SessionLocal, engine
from app.models.account import Account
from app.models.message import Message


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # --- アカウント ---
    existing = db.query(Account).count()
    if existing == 0:
        accounts = [
            Account(name="MORABLU", channel="amazon"),
            Account(name="2ndMORABLU", channel="amazon"),
            Account(name="CHA3", channel="amazon"),
        ]
        db.add_all(accounts)
        db.commit()
        print(f"Seeded {len(accounts)} accounts.")
    else:
        print(f"Accounts already exist ({existing}). Skipping.")

    # --- テストメッセージ ---
    existing_msgs = db.query(Message).count()
    if existing_msgs > 0:
        print(f"Messages already exist ({existing_msgs}). Skipping.")
        db.close()
        return

    now = datetime.now(timezone.utc)
    morablu = db.query(Account).filter(Account.name == "MORABLU").first()
    second = db.query(Account).filter(Account.name == "2ndMORABLU").first()
    cha3 = db.query(Account).filter(Account.name == "CHA3").first()

    messages = [
        Message(
            account_id=morablu.id,
            external_order_id="503-1234567-8901234",
            sender="田中太郎",
            subject="商品がまだ届きません",
            body="先週注文した商品がまだ届いていません。いつ届きますか？追跡番号を教えていただけますか？",
            direction="inbound",
            status="new",
            asin="B0EXAMPLE01",
            product_title="LEDヘッドライト H4 車検対応",
            received_at=now - timedelta(hours=2),
        ),
        Message(
            account_id=morablu.id,
            external_order_id="503-2345678-9012345",
            sender="佐藤花子",
            subject="商品に傷がありました",
            body="本日届いた商品を確認したところ、本体に目立つ傷がありました。交換または返金をお願いしたいです。写真を添付しました。",
            direction="inbound",
            status="new",
            asin="B0EXAMPLE02",
            product_title="スマホホルダー 車載用 エアコン取付型",
            received_at=now - timedelta(hours=1),
        ),
        Message(
            account_id=second.id,
            external_order_id="503-3456789-0123456",
            sender="鈴木一郎",
            subject="領収書の発行をお願いします",
            body="先日購入した商品の領収書をいただけますでしょうか。宛名は「株式会社ABC」でお願いいたします。",
            direction="inbound",
            status="new",
            asin="B0EXAMPLE03",
            product_title="ワイヤレスイヤホン Bluetooth 5.3",
            received_at=now - timedelta(minutes=45),
        ),
        Message(
            account_id=cha3.id,
            external_order_id="503-4567890-1234567",
            sender="高橋美咲",
            subject="注文をキャンセルしたい",
            body="昨日注文したのですが、間違えて2個注文してしまいました。1個キャンセルすることはできますか？",
            direction="inbound",
            status="new",
            asin="B0EXAMPLE04",
            product_title="USB-C ハブ 7in1 4K HDMI対応",
            received_at=now - timedelta(minutes=30),
        ),
        Message(
            account_id=morablu.id,
            external_order_id="503-5678901-2345678",
            sender="山田健太",
            subject="この商品は車検に通りますか？",
            body="LEDヘッドライト H4を購入検討中です。こちらの商品は車検に対応していますか？取付工賃は含まれていますか？",
            direction="inbound",
            status="new",
            asin="B0EXAMPLE01",
            product_title="LEDヘッドライト H4 車検対応",
            received_at=now - timedelta(minutes=15),
        ),
        Message(
            account_id=second.id,
            external_order_id="503-6789012-3456789",
            sender="伊藤裕子",
            subject="届け先を変更したい",
            body="注文後に引っ越しが決まりました。届け先の住所を変更できますか？新しい住所は東京都渋谷区〇〇です。",
            direction="inbound",
            status="new",
            asin="B0EXAMPLE05",
            product_title="ポータブル電源 大容量 300W",
            received_at=now - timedelta(minutes=10),
        ),
        Message(
            account_id=morablu.id,
            external_order_id="503-7890123-4567890",
            sender="中村大輔",
            subject="商品が動きません",
            body="届いた商品の電源を入れても全く反応しません。初期不良だと思います。返品・交換をお願いします。",
            direction="inbound",
            status="new",
            asin="B0EXAMPLE02",
            product_title="スマホホルダー 車載用 エアコン取付型",
            received_at=now - timedelta(minutes=5),
        ),
    ]

    db.add_all(messages)
    db.commit()
    print(f"Seeded {len(messages)} test messages.")
    db.close()


if __name__ == "__main__":
    seed()
