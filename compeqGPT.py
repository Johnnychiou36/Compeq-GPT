import os, json, fitz, docx, base64
import pandas as pd
from PIL import Image
from io import BytesIO
import streamlit as st
from openai import OpenAI

# 頁面設定
st.set_page_config(page_title="Compeq GPT Chat", layout="wide")
st.title("Compeq GPT（你的好助手）")

# 登入機制
if "user_id" not in st.session_state:
    with st.sidebar:
        st.header("👤 請輸入使用者名稱")
        username = st.text_input("使用者名稱", key="username_input")
        if st.button("登入"):
            if username.strip():
                st.session_state.user_id = username.strip()
                st.rerun()
    st.stop()
else:
    username = st.session_state.user_id
    st.sidebar.markdown(f"✅ 目前使用者：`{username}`")
    if st.sidebar.button("🔁 切換使用者"):
        for key in ["user_id", "conversations", "active_session"]:
            st.session_state.pop(key, None)
        st.rerun()

SESSIONS_FILE = f"chat_sessions_{username}.json"

# 初始化 GPT
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# 初始化對話
if "conversations" not in st.session_state:
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            st.session_state.conversations = json.load(f)
    else:
        st.session_state.conversations = {"預設對話": []}
if "active_session" not in st.session_state:
    st.session_state.active_session = list(st.session_state.conversations.keys())[0]

def save_sessions():
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(st.session_state.conversations, f, ensure_ascii=False, indent=2)

# 對話管理
st.sidebar.header("💬 對話管理")
session_names = list(st.session_state.conversations.keys())
selected = st.sidebar.selectbox("選擇對話", session_names, index=session_names.index(st.session_state.active_session))
st.session_state.active_session = selected

with st.sidebar.expander("重新命名對話"):
    rename_input = st.text_input("輸入新名稱", key="rename_input")
    if st.button("✏️ 確認重新命名"):
        if rename_input and rename_input not in st.session_state.conversations:
            st.session_state.conversations[rename_input] = st.session_state.conversations.pop(st.session_state.active_session)
            st.session_state.active_session = rename_input
            save_sessions()
            st.rerun()

with st.sidebar.expander("新增對話"):
    new_session_name = st.text_input("輸入對話名稱", key="new_session")
    if st.button("➕ 建立新對話"):
        if new_session_name and new_session_name not in st.session_state.conversations:
            st.session_state.conversations[new_session_name] = []
            st.session_state.active_session = new_session_name
            save_sessions()
            st.rerun()

if st.sidebar.button("🗑️ 刪除當前對話"):
    del st.session_state.conversations[st.session_state.active_session]
    if not st.session_state.conversations:
        st.session_state.conversations = {"預設對話": []}
    st.session_state.active_session = list(st.session_state.conversations.keys())[0]
    save_sessions()
    st.rerun()

# 檔案預處理
def extract_file_content(file):
    file_type = file.type
    if file_type.startswith("image/"):
        image = Image.open(file)
        buf = BytesIO()
        image.save(buf, format="PNG")
        return {"type": "image", "bytes": buf.getvalue(), "preview": image}
    elif file_type == "application/pdf":
        doc = fitz.open(stream=file.read(), filetype="pdf")
        text = "".join([page.get_text() for page in doc])
        return {"type": "text", "text": text.strip()[:1500]}
    elif file_type == "text/plain":
        return {"type": "text", "text": file.read().decode("utf-8")[:1500]}
    elif file_type.endswith("wordprocessingml.document"):
        doc = docx.Document(file)
        key_phrases = ["問題", "建議", "風險", "錯誤"]
        summary = "\n".join([p.text for p in doc.paragraphs if any(k in p.text for k in key_phrases)])
        return {"type": "text", "text": summary.strip()[:1500]}
    elif file_type.endswith("spreadsheetml.sheet"):
        df = pd.read_excel(file)
        return {"type": "text", "text": df.describe().to_string()[:1500]}
    return {"type": "unsupported"}

def truncate(text, max_len=1000):
    return text if len(text) <= max_len else text[:max_len] + "..."

uploaded_file = st.file_uploader("上傳圖片 / PDF / Word / TXT / Excel", type=["png", "jpg", "jpeg", "pdf", "txt", "docx", "xlsx"])

# Chat input
if prompt := st.chat_input("輸入問題，並按 Enter 發送..."):
    file_content = extract_file_content(uploaded_file) if uploaded_file else None

    with st.chat_message("user"):
        st.markdown(prompt)
        if file_content and "preview" in file_content:
            st.image(file_content["preview"], caption="上傳圖片")

    messages = [
        {
            "role": "system",
            "content": (
                "你是 Compeq GPT，一位專業的工程助理，擅長解讀各種程式碼、技術文件、圖表與資料報表，"
                "回覆時請使用條列式與段落分明的結構，盡可能提供具體建議與實務解決方案。"
                "如果使用者的問題資訊不足，請禮貌地說明並主動引導他補充必要背景，"
                "回覆風格請清晰、專業、協助導向，不要簡單拒絕回答。"
            )
        }
    ]

    session_data = st.session_state.conversations[st.session_state.active_session]
    if len(session_data) > 4:
        summary = "歷史對話摘要：" + "；".join([x["提問"][:30] for x in session_data[:-2]])
        messages.append({"role": "system", "content": summary})

    for item in session_data[-2:]:
        messages.append({"role": "user", "content": truncate(item["提問"])})
        messages.append({"role": "assistant", "content": truncate(item["回覆"])})

    if file_content:
        if file_content["type"] == "image":
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": truncate(prompt)},
                    {"type": "image_url", "image_url": {
                        "url": "data:image/png;base64," + base64.b64encode(file_content["bytes"]).decode()}}
                ]
            })
        elif file_content["type"] == "text":
            messages.append({"role": "user", "content": truncate(f"{prompt}\n\n以下是檔案摘要：\n{file_content['text']}", 1500)})
    else:
        messages.append({"role": "user", "content": truncate(prompt)})

    try:
        with st.spinner("思考中..."):
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3,
                max_tokens=1500
            )
            reply = completion.choices[0].message.content
    except Exception as e:
        reply = f"❗ 發生錯誤：{str(e)}"

    with st.chat_message("assistant"):
        st.markdown(reply)

    session_data.append({"提問": prompt, "回覆": reply})
    save_sessions()

# 歷史紀錄
for item in st.session_state.conversations[st.session_state.active_session]:
    with st.chat_message("user"):
        st.markdown(item["提問"])
    with st.chat_message("assistant"):
        st.markdown(item["回覆"])

# 下載工具
def create_txt_file(content): return BytesIO(content.encode("utf-8"))
def create_json_file(content): return BytesIO(json.dumps({"response": content}, ensure_ascii=False).encode("utf-8"))
def create_word_doc(content):
    doc = docx.Document()
    doc.add_heading("GPT 回覆內容", level=1)
    doc.add_paragraph(content)
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
def create_excel_file(history):
    df = pd.DataFrame(history)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='ChatHistory')
    output.seek(0)
    return output

if st.sidebar.button("📥 下載當前聊天紀錄"):
    session_data = st.session_state.conversations[st.session_state.active_session]
    reply_all = "\n\n".join([f"你：{x['提問']}\nGPT：{x['回覆']}" for x in session_data])
    st.sidebar.download_button("TXT 檔", create_txt_file(reply_all), file_name="response.txt")
    st.sidebar.download_button("JSON 檔", create_json_file(reply_all), file_name="response.json")
    st.sidebar.download_button("Word 檔", create_word_doc(reply_all), file_name="response.docx")
    st.sidebar.download_button("Excel 檔", create_excel_file(session_data), file_name="response.xlsx")
