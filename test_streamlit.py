# test_streamlit.py
import streamlit as st
import torch

st.title("GPU 狀態測試")
st.write("PyTorch 版本:", torch.__version__)
st.write("CUDA 是否可用:", torch.cuda.is_available())
if torch.cuda.is_available():
    st.write("目前使用的 GPU:", torch.cuda.get_device_name(0))
else:
    st.error("依然無法使用 GPU！")