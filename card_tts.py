import io
import os
from dotenv import load_dotenv
from google import genai
from gtts import gTTS

# .env 로드
load_dotenv()

# ---------------------------------------------------------
# 0. Gemini 클라이언트 설정 및 키 체크
# ---------------------------------------------------------
api_key = os.getenv("GEMINI_API_KEY")

print("=" * 40)
if api_key:
    print(f"[DEBUG] API 키가 정상적으로 로드되었습니다: {api_key[:8]}***")
else:
    print("[DEBUG] ❌ GEMINI_API_KEY를 찾을 수 없습니다! .env 파일을 확인해주세요.")
print("=" * 40)

client = genai.Client(api_key=api_key) if api_key else None


def analyze_intent_mock(speech_text: str) -> str:
    print(f"[팀원 모듈] 입력된 발화: '{speech_text}'")
    return "제안"


def generate_sentence_from_cards(
    selected_cards: list[str], intent: str, speech_text: str = None
) -> str:
    if not client:
        print("[DEBUG] client가 None이므로 Fallback 문장을 반환합니다.")
        return " ".join(selected_cards) + " 입니다."

    cards_str = ", ".join(f"'{card}'" for card in selected_cards)
    context_str = f'상대방 발화: "{speech_text}"\n' if speech_text else ""

    prompt = f"""
당신은 언어 및 의사소통 보조(AAC) AI 시스템입니다.
사용자가 선택한 단어 카드들과 대화 상대방의 의도(intent)를 고려하여, 상대방에게 전달할 자연스럽고 매끄러운 한 문장을 완성해 주세요.

[조건]
1. 입력받은 단어 카드의 의미를 반드시 모두 포함해야 합니다.
2. 상대방의 의도({intent})에 알맞은 자연스러운 어조(존댓말)로 완성하세요.
3. 부연 설명이나 인삿말 없이, 오직 최종 생성된 문장 하나만 반환하세요.

[상황]
{context_str}상대방의 의도: {intent}
선택된 단어 카드: [{cards_str}]

생성된 문장:
"""

    try:
        print("[DEBUG] Gemini API 호출 시도 중...")
        response = client.models.generate_content(
            model="models/gemini-2.5-flash-lite", contents=prompt
        )
        print("[DEBUG] Gemini API 호출 성공!")
        return response.text.strip()
    except Exception as e:
        print(f"\n[ERROR 발생] ❌ 상세 에러 원인: {type(e).__name__}: {e}\n")
        return " ".join(selected_cards) + " 입니다."


def save_tts_audio(text: str, output_filename: str = "output.mp3"):
    tts = gTTS(text=text, lang="ko", slow=False)
    tts.save(output_filename)
    print(f"[gTTS] '{output_filename}' 파일로 음성이 저장되었습니다.")


if __name__ == "__main__":
    partner_speech = "오늘 수업 끝나고 같이 카페 갈래?"
    intent = analyze_intent_mock(partner_speech)
    user_selected_cards = ["좋아", "오늘", "카페"]

    generated_sentence = generate_sentence_from_cards(
        selected_cards=user_selected_cards,
        intent=intent,
        speech_text=partner_speech,
    )
    print(f"-> 최종 생성된 문장: \"{generated_sentence}\"\n")

    save_tts_audio(generated_sentence, "output.mp3")