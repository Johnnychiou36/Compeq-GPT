import os
import fitz
import docx
import base64
import pandas as pd
from PIL import Image
from io import BytesIO
import streamlit as st
from openai import OpenAI

# === API 初始化 ===
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# === 頁面設定 ===
st.set_page_config(page_title="Compeq GPT Chat", layout="wide")
st.title("Compeq GPT(你的好助手)")

# === 聊天紀錄保存 ===
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# === 檔案處理 ===
def extract_file_content(file):
    file_type = file.type
    if file_type.startswith("image/"):
        image = Image.open(file)
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        img_bytes = buffered.getvalue()
        return {"type": "image", "bytes": img_bytes, "preview": image}
    elif file_type == "application/pdf":
        text = ""
        doc = fitz.open(stream=file.read(), filetype="pdf")
        for page in doc:
            text += page.get_text()
        return {"type": "text", "text": text.strip()[:1500]}  # 限制 PDF 長度
    elif file_type == "text/plain":
        return {"type": "text", "text": file.read().decode("utf-8")[:1500]}  # 限制 TXT 長度
    elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(file)
        text = "\n".join([para.text for para in doc.paragraphs])
        return {"type": "text", "text": text.strip()[:1500]}  # 限制 Word 長度
    elif file_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        df = pd.read_excel(file)
        return {"type": "text", "text": df.to_string(index=False)[:1500]}  # 限制 Excel 長度
    return {"type": "unsupported"}

# === 限制文字長度用函數 ===
def truncate(text, max_len=1000):
    return text if len(text) <= max_len else text[:max_len] + "..."

# === 上傳檔案 ===
uploaded_file = st.file_uploader("上傳圖片 / PDF / Word / TXT / Excel", type=["png", "jpg", "jpeg", "pdf", "txt", "docx", "xlsx"])

# === 對話框輸入區 ===
if prompt := st.chat_input("輸入問題，並按 Enter 發送..."):
    file_content = extract_file_content(uploaded_file) if uploaded_file else None

    with st.chat_message("user"):
        st.markdown(prompt)
        if file_content and "preview" in file_content:
            st.image(file_content["preview"], caption="上傳圖片")

    # 建立 GPT messages 上下文
    messages = []

    for item in st.session_state.chat_history[-2:]:  # 保留最近 2 輪對話
        messages.append({"role": "user", "content": truncate(item["提問"])})
        messages.append({"role": "assistant", "content": truncate(item["回覆"])})

    if file_content and file_content["type"] == "image":
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": truncate(prompt)},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(file_content["bytes"]).decode()}}
            ]
        })
    elif file_content and file_content["type"] == "text":
        messages.append({"role": "user", "content": truncate(f"{prompt}\n\n以下是檔案內容：\n{file_content['text']}", 1500)})
    else:
        messages.append({"role": "user", "content": truncate(prompt)})

    # GPT 回應
    try:
        with st.spinner("思考中..."):
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=1500
            )
            reply = completion.choices[0].message.content
    except Exception as e:
        reply = f"❗ 發生錯誤：{str(e)}"
    
    with st.chat_message("assistant"):
        st.markdown(reply)

    st.session_state.chat_history.append({"提問": prompt, "回覆": reply})

# === 歷史下載工具 ===
def create_word_doc(content):
    doc = docx.Document()
    doc.add_heading('GPT 回覆內容', level=1)
    doc.add_paragraph(content)
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def create_txt_file(content):
    return BytesIO(content.encode("utf-8"))

def create_json_file(content):
    json_str = '{"response": "%s"}' % content.replace('"', '\\"').replace("\n", "\\n")
    return BytesIO(json_str.encode("utf-8"))

def create_excel_file(history):
    df = pd.DataFrame(history)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='ChatHistory')
    output.seek(0)
    return output

# === 側邊欄下載與歷史 ===
if st.sidebar.button("下載聊天紀錄") and st.session_state.chat_history:
    reply_all = "\n\n".join([f"你：{x['提問']}\nGPT：{x['回覆']}" for x in st.session_state.chat_history])
    st.sidebar.download_button("TXT 檔", create_txt_file(reply_all), file_name="response.txt")
    st.sidebar.download_button("JSON 檔", create_json_file(reply_all), file_name="response.json")
    st.sidebar.download_button("Word 檔", create_word_doc(reply_all), file_name="response.docx")
    st.sidebar.download_button("Excel 檔", create_excel_file(st.session_state.chat_history), file_name="chat_history.xlsx")

if st.sidebar.checkbox("顯示歷史紀錄"):
    for item in st.session_state.chat_history:
        with st.chat_message("user"):
            st.markdown(item['提問'])
        with st.chat_message("assistant"):
            st.markdown(item['回覆'])
