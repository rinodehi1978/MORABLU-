"""Claude APIによるAI回答生成サービス"""

import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
あなたは中国輸入物販ビジネスのカスタマーサポート担当です。
丁寧で親切な日本語で、お客様のお問い合わせに回答してください。

回答の優先順位:
1. 注文情報（SP API Ordersから取得済み）を正確な事実として参照する
2. 商品情報（SP APIから取得済み）を正確な事実として参照する
3. 同じ商品の過去対応履歴があれば、スタッフの過去回答を最も重視する（実績ある回答）
4. 社内Q&Aテンプレートが該当すれば、そのテンプレートの文面・トーンをベースにする
5. 同カテゴリの過去対応履歴があれば参考にする
6. いずれもなければ、既存テンプレートのトーンに合わせて回答を作成する

【最重要】事実確認ルール（絶対厳守）:
- 提供されたデータに含まれる情報のみを事実として扱うこと
- 注文ステータスが「未確認」の場合、「発送済み」「未発送」「キャンセル済み」等の断定は絶対にしない
- 追跡番号、配送日時、配送業者を知らない場合は、具体的な値を書かない
- 「倉庫に確認しました」「発送状況を確認しました」等、実際に確認していない行為を書かない
- 推測・憶測・仮定で事実のように書くことは厳禁
- 不明な情報は「○○」プレースホルダーか「確認中」と明示する
- 嘘や誤情報は信用を大きく損なうため、分からないことは正直に「確認します」と答える

【不確実な事案の対応ルール】:
- 断言できない内容は絶対に断言しない。「担当部署に確認のうえ、改めてご連絡いたします」等の表現を使う
- 在庫状況、入荷予定、具体的な日付が不明な場合は「確認いたしまして、改めてご回答させていただきます」
- 返品・返金の可否が即座に判断できない場合は「詳細を確認のうえ、ご対応方法をご連絡いたします」
- 技術的な仕様が商品情報に含まれていない場合は「メーカーに確認し、改めてご連絡いたします」
- お客様を待たせる場合は「お時間をいただき恐れ入りますが」と一言添える
- 要点: 正直に「確認します」と伝えて後日回答する方が、誤った情報を伝えるよりはるかに良い

回答ルール:
- 商品のサイズ・仕様・特徴について聞かれた場合、商品情報にある事実のみ回答する。推測で回答しない
- テンプレートにある定型文（出荷元の説明、FBAの説明等）はそのまま活用する
- テンプレート内の空欄（日付、追跡番号等）は「○○」のままプレースホルダーとして残す
- 敬語を使い、簡潔で分かりやすい文章にする
- 問題解決に向けた具体的な提案をする
- 不明点があれば確認を促す
- 返金・返品については柔軟に対応する姿勢を見せる
- 配送遅延には謝罪と現状の説明をする
- スタッフ向けメモが付いている場合、その内容も考慮に入れる（ただしメモ自体は顧客向け回答に含めない）
- 過去対応履歴のスタッフ回答はそのまま使わず、今回のケースに適応させる
"""


async def generate_draft(
    customer_message: str,
    subject: str | None = None,
    order_id: str | None = None,
    asin: str | None = None,
    product_title: str | None = None,
    question_category: str | None = None,
    product_info: str | None = None,
    order_status_info: str | None = None,
    qa_templates: list[dict] | None = None,
    past_product_responses: list[dict] | None = None,
    past_category_responses: list[dict] | None = None,
) -> str:
    """顧客メッセージに対するAI回答案を生成する。"""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # --- ユーザープロンプト組み立て ---
    user_content = ""
    if order_id:
        user_content += f"注文番号: {order_id}\n"
    if asin:
        user_content += f"ASIN: {asin}\n"
    if product_title:
        user_content += f"商品名: {product_title}\n"
    if question_category:
        user_content += f"質問カテゴリ（AI分類）: {question_category}\n"
    if subject:
        user_content += f"件名: {subject}\n"
    user_content += f"\nお客様のメッセージ:\n{customer_message}"

    # ⓪ 注文情報（SP API Ordersから取得した実データ）
    if order_status_info:
        user_content += "\n\n===== 注文情報（SP API Ordersより取得） ====="
        user_content += f"\n{order_status_info}"
    else:
        user_content += "\n\n===== 注文情報 ====="
        user_content += "\n注文ステータス: 【未確認】"
        user_content += "\n※注文の状態が確認できていません。発送済み・未発送などの断定はしないでください。"

    # ① 商品情報（SP APIから取得した公式データ）
    if product_info:
        user_content += "\n\n===== 該当商品の情報（Amazon商品ページより） ====="
        user_content += f"\n{product_info}"

    # ② 同一商品の過去対応履歴
    if past_product_responses:
        user_content += "\n\n===== この商品の過去対応履歴（スタッフ実績） ====="
        for i, r in enumerate(past_product_responses, 1):
            user_content += f"\n\n--- 事例{i} ---"
            user_content += f"\n顧客の質問: {r['customer_question']}"
            if r.get("question_category"):
                user_content += f"\nカテゴリ: {r['question_category']}"
            user_content += f"\nスタッフの回答:\n{r['staff_answer']}"

    # ③ Q&Aテンプレート
    if qa_templates:
        user_content += "\n\n===== 社内Q&Aテンプレート ====="
        for t in qa_templates:
            user_content += f"\n\n【カテゴリ】{t['category']}"
            if t.get("subcategory"):
                user_content += f"\n【種類】{t['subcategory']}"
            user_content += f"\n【回答テンプレート】\n{t['answer_template']}"
            if t.get("staff_notes"):
                user_content += f"\n【スタッフ向けメモ】{t['staff_notes']}"

    # ④ 同カテゴリの過去対応履歴
    if past_category_responses:
        user_content += "\n\n===== 同カテゴリの過去対応履歴（参考） ====="
        for i, r in enumerate(past_category_responses, 1):
            user_content += f"\n\n--- 参考事例{i} ---"
            if r.get("product_title"):
                user_content += f"\n商品: {r['product_title']}"
            user_content += f"\n顧客の質問: {r['customer_question']}"
            user_content += f"\nスタッフの回答:\n{r['staff_answer']}"

    user_content += "\n\n上記を踏まえて、お客様への回答案を作成してください。"

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text
    except Exception:
        logger.exception("AI response generation failed")
        raise
