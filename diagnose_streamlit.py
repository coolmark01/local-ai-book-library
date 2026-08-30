"""
Streamlit CUDA 診斷頁面 (diagnose_streamlit.py)
================================================
用途：在 Streamlit 環境中直接檢查 CUDA 狀態。

使用方式：
    streamlit run diagnose_streamlit.py

這個頁面會顯示：
- Streamlit 內部的 Python 路徑
- PyTorch 版本與 CUDA 支援
- 已安裝的 torch 套件
- 環境變數
- 修復建議
"""

import streamlit as st
import sys
import os
import subprocess

st.set_page_config(page_title="CUDA 診斷工具", page_icon="🔍", layout="wide")

st.title("🔍 CUDA 環境診斷工具")
st.caption("此頁面在 Streamlit 環境中運行，顯示 Streamlit 實際使用的 Python 環境狀態")

st.divider()

# --- 1. Python 環境 ---
st.subheader("1️⃣ Python 環境")
col1, col2 = st.columns(2)
col1.metric("Python 執行檔", os.path.basename(sys.executable))
col2.metric("Python 版本", sys.version.split()[0])

st.code(f"完整路徑: {sys.executable}", language="bash")
st.code(f"工作目錄: {os.getcwd()}", language="bash")

# 檢查虛擬環境
venv = os.environ.get("VIRTUAL_ENV")
if venv:
    st.success(f"✅ 虛擬環境: {venv}")
else:
    st.error("❌ 未在虛擬環境中運行（使用系統全域 Python）")

st.divider()

# --- 2. PyTorch 狀態 ---
st.subheader("2️⃣ PyTorch 狀態")

try:
    import torch
    st.metric("PyTorch 版本", torch.__version__)
    st.code(f"PyTorch 路徑: {torch.__file__}", language="bash")

    cuda_available = torch.cuda.is_available()
    if cuda_available:
        st.success(f"✅ CUDA 可用: True")
        st.metric("CUDA 版本", torch.version.cuda if hasattr(torch.version, 'cuda') else "N/A")
        st.metric("GPU 裝置數", str(torch.cuda.device_count()))
        if torch.cuda.device_count() > 0:
            st.metric("GPU 名稱", torch.cuda.get_device_name(0))
    else:
        st.error("❌ CUDA 不可用: False")
        if "cpu" in torch.__version__.lower():
            st.warning("⚠️ 你安裝的是 PyTorch CPU 版本！")
            st.info("請卸載 CPU 版並安裝 CUDA 版：")
            st.code("pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124", language="bash")

    # 列出所有 CUDA 裝置
    if cuda_available:
        for i in range(torch.cuda.device_count()):
            st.write(f"  GPU {i}: {torch.cuda.get_device_name(i)}")

except ImportError:
    st.error("❌ PyTorch 未安裝！")
    st.info("請執行：pip install torch")

st.divider()

# --- 3. 已安裝的 torch 套件 ---
st.subheader("3️⃣ 已安裝的 torch 相關套件")

try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list"],
        capture_output=True, text=True, timeout=30
    )
    torch_packages = []
    for line in result.stdout.split("\n"):
        if any(kw in line.lower() for kw in ["torch", "cuda", "cupy"]):
            torch_packages.append(line.strip())
    
    if torch_packages:
        for pkg in torch_packages:
            st.code(pkg, language="text")
    else:
        st.info("未找到 torch 相關套件")
except Exception as e:
    st.error(f"檢查套件時出錯: {e}")

st.divider()

# --- 4. 環境變數 ---
st.subheader("4️⃣ 相關環境變數")

env_vars = ["CUDA_VISIBLE_DEVICES", "CUDA_HOME", "CUDA_PATH", "PATH"]
for var in env_vars:
    val = os.environ.get(var, "(未設定)")
    if val != "(未設定)" and len(val) > 100:
        val = val[:100] + "..."
    st.text(f"{var}: {val}")

st.divider()

# --- 5. 修復建議 ---
st.subheader("5️⃣ 修復建議")

try:
    import torch
    if "cpu" in torch.__version__.lower() and not torch.cuda.is_available():
        st.error("問題確認：Streamlit 使用的是 CPU 版 PyTorch")
        
        st.info("請在終端機中執行以下步驟修復：")
        
        st.markdown("**Step 1：確認在正確的虛擬環境中**")
        st.code("確認 PowerShell 左側顯示 (venv)", language="text")
        
        st.markdown("**Step 2：卸載 CPU 版 PyTorch**")
        st.code("pip uninstall torch torchvision torchaudio -y", language="powershell")
        
        st.markdown("**Step 3：安裝 CUDA 版 PyTorch**")
        st.info("根據你的 CUDA 版本（nvidia-smi 查看），選擇對應的指令：")
        
        st.code("CUDA 12.4: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124", language="powershell")
        st.code("CUDA 11.8: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118", language="powershell")
        st.code("CUDA 13.0: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130", language="powershell")
        
        st.markdown("**Step 4：驗證安裝**")
        st.code('python -c "import torch; print(torch.cuda.is_available())"', language="powershell")
        st.info("預期輸出：True")
        
        st.markdown("**Step 5：重新啟動 Streamlit**")
        st.code("streamlit run app.py", language="powershell")
        
    elif torch.cuda.is_available():
        st.success("✅ 環境設定正確！CUDA 可正常運作。")
        st.info("你可以將 config.py 中的 EMBEDDING_DEVICE 設為 "cuda"")

except ImportError:
    st.error("PyTorch 未安裝，請先執行 pip install torch")
