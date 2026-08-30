"""
CUDA 環境診斷腳本 (diagnose_cuda.py)
=====================================
用途：找出為什麼 Streamlit 無法使用 CUDA。

使用方式：
    1. 終端機執行：python diagnose_cuda.py
    2. 或在 Streamlit 中執行：streamlit run diagnose_cuda.py

這個腳本會檢查：
- 哪個 Python 被使用（路徑、版本）
- PyTorch 版本與 CUDA 支援狀態
- 已安裝的 torch 相關套件
- 環境變數（PATH, CUDA_VISIBLE_DEVICES 等）
- 虛擬環境狀態
"""

import sys
import os
import subprocess
import platform

print("=" * 70)
print("  CUDA 環境診斷工具")
print("=" * 70)

# --- 1. Python 環境 ---
print("\n[1] Python 環境")
print("-" * 40)
print(f"  Python 執行檔路徑: {sys.executable}")
print(f"  Python 版本:       {sys.version}")
print(f"  執行檔名稱:        {os.path.basename(sys.executable)}")
print(f"  工作目錄:          {os.getcwd()}")

# 檢查是否在虛擬環境中
venv = os.environ.get("VIRTUAL_ENV")
if venv:
    print(f"  虛擬環境:          ✅ 是 ({venv})")
else:
    print(f"  虛擬環境:          ❌ 否（系統全域 Python）")

# --- 2. PyTorch 狀態 ---
print("\n[2] PyTorch 狀態")
print("-" * 40)
try:
    import torch
    print(f"  PyTorch 版本:      {torch.__version__}")
    print(f"  PyTorch 路徑:      {torch.__file__}")
    
    cuda_available = torch.cuda.is_available()
    print(f"  CUDA 是否可用:     {'✅ 是' if cuda_available else '❌ 否'}")
    
    if cuda_available:
        print(f"  CUDA 版本:         {torch.version.cuda}")
        print(f"  GPU 裝置數:        {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"    GPU {i}: {torch.cuda.get_device_name(i)}")
    else:
        # 檢查是否是 CPU 版本
        if 'cpu' in torch.__version__.lower():
            print(f"  ⚠️  你安裝的是 PyTorch CPU 版本！")
            print(f"     請卸載並重新安裝 CUDA 版本：")
            print(f"     pip uninstall torch torchvision torchaudio -y")
            print(f"     pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124")
        
        # 檢查系統是否有 NVIDIA 驅動
        try:
            result = subprocess.run(
                ["nvidia-smi"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # 提取 CUDA 版本
                for line in result.stdout.split("\n"):
                    if "CUDA Version:" in line:
                        print(f"  ℹ️  nvidia-smi 顯示 CUDA 版本: {line.strip()}")
                        break
                print(f"  ℹ️  系統有 NVIDIA 驅動，但 PyTorch 沒有連結到 CUDA。")
                print(f"     這表示你安裝的 PyTorch 是 CPU 版本。")
            else:
                print(f"  ℹ️  nvidia-smi 不可用（可能沒有 NVIDIA 驅動）")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f"  ℹ️  無法執行 nvidia-smi（可能沒有 NVIDIA 驅動）")
except ImportError:
    print("  ❌ PyTorch 未安裝！")

# --- 3. 已安裝的 torch 相關套件 ---
print("\n[3] 已安裝的 torch 相關套件")
print("-" * 40)
try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list"],
        capture_output=True, text=True, timeout=30
    )
    for line in result.stdout.split("\n"):
        if any(kw in line.lower() for kw in ["torch", "cuda", "cupy"]):
            print(f"  {line.strip()}")
except Exception as e:
    print(f"  無法檢查套件: {e}")

# --- 4. 環境變數 ---
print("\n[4] 相關環境變數")
print("-" * 40)
for key in ["CUDA_VISIBLE_DEVICES", "CUDA_HOME", "CUDA_PATH", "PATH"]:
    val = os.environ.get(key, "")
    if val:
        # 只顯示前 100 個字元
        print(f"  {key}: {val[:100]}")
    else:
        print(f"  {key}: (未設定)")

# --- 5. pip show torch ---
print("\n[5] pip show torch")
print("-" * 40)
try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", "torch"],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        for line in result.stdout.split("\n"):
            print(f"  {line.strip()}")
    else:
        print(f"  無法取得 torch 資訊")
except Exception as e:
    print(f"  錯誤: {e}")

# --- 6. 結論與建議 ---
print("\n" + "=" * 70)
print("  診斷結論")
print("=" * 70)

try:
    import torch
    if "cpu" in torch.__version__.lower() and not torch.cuda.is_available():
        print("""
  ❌ 你的 Streamlit 正在使用 CPU 版本的 PyTorch。

  解決步驟：
  1. 確認終端機在正確的虛擬環境中（左側應顯示 (venv)）
  2. 執行以下指令卸載 CPU 版 PyTorch：
     pip uninstall torch torchvision torchaudio -y
  
  3. 安裝 CUDA 版本（根據你的 CUDA 版本選擇）：
     CUDA 12.4: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
     CUDA 11.8: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
  
  4. 驗證安裝：
     python -c "import torch; print(torch.cuda.is_available())"
     應輸出 True
  
  5. 重新啟動 Streamlit：
     streamlit run app.py
""")
    elif torch.cuda.is_available():
        print("""
  ✅ 你的環境已正確設定 CUDA 加速！
  可以直接使用 EMBEDDING_DEVICE = "cuda"
""")
    else:
        print("""
  ⚠️  無法確定問題原因，請檢查：
  1. 是否執行了 pip install 在正確的虛擬環境中
  2. 確認 nvidia-smi 能正常運作
  3. 嘗試重新安裝 PyTorch
""")
except ImportError:
    print("""
  ❌ PyTorch 完全未安裝，請先執行：
  pip install torch torchvision torchaudio
""")

print("=" * 70)
