import os, platform, shutil, subprocess
def detect_hardware():
    result={"os":platform.platform(),"python":platform.python_version(),"cpu":platform.processor() or platform.machine(),"cpu_count":os.cpu_count(),"ram_gb":None,"gpu":None,"vram":None,"ollama_binary":shutil.which("ollama")}
    try:
        import ctypes
        class M(ctypes.Structure): _fields_=[("length",ctypes.c_ulong),("memory_load",ctypes.c_ulong),("total",ctypes.c_ulonglong),("avail",ctypes.c_ulonglong),("page",ctypes.c_ulonglong),("avail_page",ctypes.c_ulonglong),("virt",ctypes.c_ulonglong),("avail_virt",ctypes.c_ulonglong),("avail_ext",ctypes.c_ulonglong)]
        m=M(); m.length=ctypes.sizeof(M); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); result["ram_gb"]=round(m.total/1024**3,1)
    except Exception: pass
    if shutil.which("nvidia-smi"):
        try: result["gpu"]=subprocess.check_output(["nvidia-smi","--query-gpu=name,memory.total","--format=csv,noheader"],text=True,timeout=5).strip()
        except Exception: result["gpu"]="nvidia-smi detected, query failed"
    result["recommendation"]="Use a small quantized local model first; do not auto-download. Match model size to available RAM/VRAM."
    return result

