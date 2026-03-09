import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000/ask"

st.set_page_config(
    page_title="Enterprise Data Copilot",
    page_icon="🤖",
    layout="wide"
)

st.title("🏦 Credit Union Enterprise Copilot")

st.markdown(
"""
Ask about:

• Snowflake tables  
• Columns  
• Lineage  
• Confluence docs  
• GitHub SQL 
• Lineage information of columns.
"""
)

if "messages" not in st.session_state:
    st.session_state.messages = []

# Show history
for msg in st.session_state.messages:

    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Input
prompt = st.chat_input("Ask question...")

if prompt:

    st.chat_message("user").write(prompt)

    st.session_state.messages.append(
        {"role": "user", "content": prompt}
    )

    try:

        response = requests.post(
            API_URL,
            json={"text": prompt}
        )

        data = response.json()

        answer = data["answer"]

        source_text = "\n\n**Sources:**\n"

        for src in data["sources"]:

            source_text += f"- {src['title']}\n"

        full_response = answer + source_text

    except Exception as e:

        full_response = str(e)

    with st.chat_message("assistant"):
        st.write(full_response)

    st.session_state.messages.append(
        {"role": "assistant", "content": full_response}
    )
