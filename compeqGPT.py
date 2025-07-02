import os
import json
import base64
import fitz
import docx
import pandas as pd
from PIL import Image
from io import BytesIO
import streamlit as st
from openai import OpenAI
from streamlit_js_eval import streamlit_js_eval

# === API 初始化 ===
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# === 頁面設定 ===
st.set_page_config(page_title="Compeq GPT Chat", layout="wide")
st.title("Compeq GPT（你的好助手）")

# === 僅在初始化時載入 localStorage ===
if "conversations" not in st.session_state:
    raw_json = streamlit_js_eval(
        js_expressions="localStorage.getItem('compeq_chat')",
        key="load-local"
    )
    if isinstance(raw_json, str) and raw_json.strip() not in ("", "null", "undefined"):
        try:
            st.session_state.conversations = json.loads(raw_json)
        except:
            st.session_state.conversations = {"預設對話": []}
    else:
        st.session_state.conversations = {"預設對話": []}

# === 保底 active_session ===
if "active_session" not in st.session_state:
    session_keys = list(st.session_state.conversations.keys())
    st.session_state.active_session = session_keys[0] if session_keys else "預設對話"

# === 儲存函數 ===
def persist_to_local():
    import uuid
    js_code = f'localStorage.setItem("compeq_chat", JSON.stringify({json.dumps(st.session_state.conversations)}));'
    streamlit_js_eval(js_expressions=js_code, key=f"save-local-{uuid.uuid4()}")

# === 側邊欄 ===
st.sidebar.header("💬 對話管理")

session_names = list(st.session_state.conversations.keys())
selected = st.sidebar.selectbox("選擇對話", session_names, index=session_names.index(st.session_state.active_session))
st.session_state.active_session = selected
persist_to_local()

with st.sidebar.expander("重新命名對話"):
    rename_input = st.text_input("輸入新名稱", key="rename_input")
    if st.button("✏️ 確認重新命名"):
        if rename_input and rename_input not in st.session_state.conversations:
            st.session_state.conversations[rename_input] = st.session_state.conversations.pop(st.session_state.active_session)
            st.session_state.active_session = rename_input
            persist_to_local()
            st.rerun()

with st.sidebar.expander("新增對話"):
    new_session = st.text_input("輸入對話名稱", key="new_session")
    if st.button("➕ 建立新對話"):
        if new_session and new_session not in st.session_state.conversations:
            st.session_state.conversations[new_session] = []
            st.session_state.active_session = new_session
            persist_to_local()
            st.rerun()

if st.sidebar.button("🗑️ 刪除當前對話"):
    del st.session_state.conversations[st.session_state.active_session]
    if not st.session_state.conversations:
        st.session_state.conversations = {"預設對話": []}
    st.session_state.active_session = list(st.session_state.conversations.keys())[0]
    persist_to_local()
    st.rerun()

# === 上傳檔案 ===
def extract_file_content(file):
    file_type = file.type
    if file_type.startswith("image/"):
        image = Image.open(file)
        buf = BytesIO(); image.save(buf, format="PNG")
        return {"type": "image", "bytes": buf.getvalue(), "preview": image}
    elif file_type == "application/pdf":
        text = "".join(page.get_text() for page in fitz.open(stream=file.read(), filetype="pdf"))
        return {"type": "text", "text": text[:1500]}
    elif file_type == "text/plain":
        return {"type": "text", "text": file.read().decode("utf-8")[:1500]}
    elif file_type.endswith("wordprocessingml.document"):
        text = "\n".join([p.text for p in docx.Document(file).paragraphs])
        return {"type": "text", "text": text[:1500]}
    elif file_type.endswith("spreadsheetml.sheet"):
        df = pd.read_excel(file)
        return {"type": "text", "text": df.to_string(index=False)[:1500]}
    return {"type": "unsupported"}

uploaded_file = st.file_uploader("上傳圖片 / PDF / Word / TXT / Excel", type=["png", "jpg", "jpeg", "pdf", "txt", "docx", "xlsx"])

# === 提問輸入 ===
def truncate(t, max_len=1000): return t if len(t) <= max_len else t[:max_len] + "..."

if prompt := st.chat_input("輸入問題，並按 Enter 發送..."):
    content = extract_file_content(uploaded_file) if uploaded_file else None

    with st.chat_message("user"): st.markdown(prompt)
    if content and "preview" in content: st.image(content["preview"], caption="上傳圖片")

    messages = []
    for item in st.session_state.conversations[st.session_state.active_session][-2:]:
        messages.append({"role": "user", "content": truncate(item["提問"])})
        messages.append({"role": "assistant", "content": truncate(item["回覆"])})

    if content and content["type"] == "image":
        messages.append({
            "role": "user", "content": [
                {"type": "text", "text": truncate(prompt)},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(content["bytes"]).decode()}}
            ]
        })
    elif content and content["type"] == "text":
        messages.append({"role": "user", "content": truncate(f"{prompt}\n\n以下是檔案內容：\n{content['text']}", 1500)})
    else:
        messages.append({"role": "user", "content": truncate(prompt)})

    try:
        with st.spinner("思考中..."):
            response = client.chat.completions.create(model="gpt-4o", messages=messages, max_tokens=1500)
            reply = response.choices[0].message.content
    except Exception as e:
        reply = f"❗ 發生錯誤：{e}"

    with st.chat_message("assistant"): st.markdown(reply)
    st.session_state.conversations[st.session_state.active_session].append({"提問": prompt, "回覆": reply})
    persist_to_local()

# === 顯示對話歷史 ===
for item in st.session_state.conversations[st.session_state.active_session]:
    with st.chat_message("user"): st.markdown(item["提問"])
    with st.chat_message("assistant"): st.markdown(item["回覆"])

# === 下載工具 ===
def create_txt(content): return BytesIO(content.encode("utf-8"))
def create_json(content): return BytesIO(json.dumps({"response": content}, ensure_ascii=False).encode("utf-8"))
def create_word(content):
    doc = docx.Document(); doc.add_heading("GPT 回覆內容", 1); doc.add_paragraph(content)
    buf = BytesIO(); doc.save(buf); buf.seek(0); return buf
def create_excel(history):
    df = pd.DataFrame(history); buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer: df.to_excel(writer, index=False)
    buf.seek(0); return buf

if st.sidebar.button("📅 下載當前聊天紀錄"):
    session = st.session_state.conversations[st.session_state.active_session]
    merged = "\n\n".join([f"你：{x['提問']}\nGPT：{x['回覆']}" for x in session])
    st.sidebar.download_button("TXT 檔", create_txt(merged), file_name="response.txt")
    st.sidebar.download_button("JSON 檔", create_json(merged), file_name="response.json")
    st.sidebar.download_button("Word 檔", create_word(merged), file_name="response.docx")
    st.sidebar.download_button("Excel 檔", create_excel(session), file_name="chat_history.xlsx")
    
